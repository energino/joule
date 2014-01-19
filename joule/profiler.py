#!/usr/bin/env python
#
# Copyright (c) 2013, Roberto Riggio
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#    * Redistributions of source code must retain the above copyright
#      notice, this list of conditions and the following disclaimer.
#    * Redistributions in binary form must reproduce the above copyright
#      notice, this list of conditions and the following disclaimer in the
#      documentation and/or other materials provided with the distribution.
#    * Neither the name of the CREATE-NET nor the
#      names of its contributors may be used to endorse or promote products
#      derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY CREATE-NET ''AS IS'' AND ANY
# EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL CREATE-NET BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""
The Joule Profiler. The profiler accepts as input a Joule descriptor defining
the probes available on the network and the stints to be executed. The output
is written in the original Joule descriptor and includes the total number of
packet TX/RX, the goodput and the throughput, the average packet loss and the
median/mean power consuption. Before starting the stints the profiler measures
the idle power consumption.
"""

import os
import json
import signal
import optparse
import logging
import sys
import time
import threading
import math
import numpy as np

from click import read_handler, write_handler
from energino import PyEnergino
from energino import DEFAULT_PORT
from energino import DEFAULT_PORT_SPEED
from energino import DEFAULT_INTERVAL
from virtualmeter import VirtualMeter

DEFAULT_JOULE = './joule.json'
LOG_FORMAT = '%(asctime)-15s %(message)s'

def bps_to_human(bps):
    """ Convert bps to humand readble string. """

    if bps >= 1000000:
        return "%f Mbps" % (float(bps) / 1000000)
    elif bps >= 100000:
        return "%f Kbps" % (float(bps) / 1000)
    else:
        return "%u bps" % bps

def tx_usecs_80211ga_udp(payload, mtu = 1468):
    """ Compute the TX time in usec for an IEEE 802.11g/a link. """

    if payload > mtu:
        return ( tx_usecs_80211ga_udp(payload / 2, mtu) +
                 tx_usecs_80211ga_udp(payload - (payload / 2), mtu) )
    else:
        # assume that transmission always succeed
        avg_cw = 15 * 9
        # payload + UDP header (12) + IP Header (20) + MAC Header (28)
        # + LLC/SNAP Header (8)
        payload = payload + 12 + 20 + 28 + 8
        # return DIFS + CW + payload + SIFS + ACK
        return int(34 +
                   avg_cw + math.ceil(float(payload * 8) / 216) * 4 +
                   16 +
                   24 )

PROFILES = { '11a' : { 'tx_usecs_udp' : tx_usecs_80211ga_udp },
             '11g' : { 'tx_usecs_udp' : tx_usecs_80211ga_udp } }

DEFAULT_PROFILE = '11g'

class Modeller(threading.Thread):
    """ Modeller class. """

    def __init__(self, backend):

        super(Modeller, self).__init__()
        logging.info("starting meter (%s)", backend.__class__.__name__)
        self.stop_event = threading.Event()
        self.daemon = True
        self.readings = []
        self.backend = backend

    def reset_readings(self):
        """ Reset readings. """
        self.readings = []

    def get_readings(self):
        """ Return a copy of the readings. """

        return self.readings[:]

    def shutdown(self):
        """ Stop modeller. """

        logging.info("stopping modeler")
        self.stop_event.set()

    def run(self):
        while not self.stop_event.isSet():
            try:
                self.readings.append(self.backend.fetch('power'))
            except ValueError as ex:
                self.readings.append(0.0)
                logging.exception(ex)

def hlog(handler):
    """ Log a call to an handler. """

    if handler[0] == "200":
        logging.debug("calling %s (%s)", handler[1], handler[0])
    else:
        logging.error("calling %s (%s)", handler[1], handler[0])
    return handler

class Probe(object):
    """ Probe class.

    Represents a connection to a remote Joule probe

    """

    def __init__(self, probe):

        self.address = probe['ip']
        self.sender_control = probe['receiver_control'] + 1
        self.receiver_control = probe['receiver_control']
        self.receiver_port = probe['receiver_port']
        self._packet_rate = 10
        self._packetsize_bytes = 64
        self._limit = 0
        self.reset()

    def reset(self):
        """ Reset probe. """

        logging.info('resetting click tx daemon (%s:%s)', self.address,
                                                          self.sender_control)

        hlog( write_handler(self.address,
                            self.sender_control,
                           'src.active false') )

        hlog( write_handler(self.address,
                            self.sender_control,
                            'src.reset') )

        hlog( write_handler(self.address,
                            self.sender_control,
                            'counter_client.reset') )

        hlog( write_handler(self.address,
                            self.sender_control,
                            'tr_client.reset') )

        logging.info('resetting click rx daemon (%s:%s)', self.address,
                                                          self.sender_control)

        hlog( write_handler(self.address,
                            self.receiver_control,
                            'counter_server.reset'))

        hlog( write_handler(self.address,
                            self.receiver_control, 'tr_server.reset'))

        self._packet_rate = 10
        self._packetsize_bytes = 64

    def status(self):
        """ Fetch probe status. """

        logging.info('fetching click daemon status (%s)', self.address)
        status = {}

        client_count = hlog(read_handler(self.address,
                                         self.sender_control,
                                        'counter_client.count'))

        status['client_count'] = int(client_count[2])

        client_interval = hlog(read_handler(self.address,
                                            self.sender_control,
                                            'tr_client.interval'))

        status['client_interval'] = float(client_interval[2])


        server_count = hlog(read_handler(self.address,
                                         self.receiver_control,
                                        'counter_server.count'))

        status['server_count'] = int(server_count[2])

        server_interval = hlog(read_handler(self.address,
                                            self.receiver_control,
                                            'tr_server.interval'))

        status['server_interval'] = float(server_interval[2])
        return status

    def configure_stint(self, stint, tps):
        """ Configure stint. """

        rate = float(stint['bitrate_mbps'] * 1000000)
        size = float(stint['packetsize_bytes'] * 8)

        duration = stint['duration_s']

        self._packet_rate = int( rate / size )
        self._packetsize_bytes = stint['packetsize_bytes']
        self._limit = self._packet_rate * duration

        bps = bps_to_human(stint['bitrate_mbps'] * 1000000)

        logging.info("will send a total of %u packets", self._limit )
        logging.info("payload length is %u bytes", self._packetsize_bytes )
        logging.info("transmission rate set to %u pkt/s", self._packet_rate )
        logging.info("trasmitting time is %us", duration )
        logging.info("target bitrate is %s", bps)

        hlog(write_handler(self.address,
                           self.sender_control,
                           'src.length %u' % self._packetsize_bytes))

        hlog(write_handler(self.address,
                           self.sender_control,
                           'src.rate %u' % self._packet_rate))

        hlog(write_handler(self.address,
                           self.sender_control,
                           'src.limit %u' % self._limit))

        hlog(write_handler(self.address,
                           self.sender_control,
                           'sha.rate %u' % tps))

    def start_stint(self):
        """ Start stint. """

        logging.info("starting probe (%s)", self.address)
        hlog(write_handler(self.address,
                           self.sender_control,
                           'src.active true'))

    def stop_stint(self):
        """ Stop stint. """

        logging.info("stopping probe (%s)", self.address)
        hlog(write_handler(self.address,
                           self.sender_control,
                           'src.active false'))

def process_readings(readings, virtual = False):
    """ Process readings. """

    median = np.median(readings)
    mean = np.mean(readings)

    ci = 1.96 * (np.std(readings) / np.sqrt(len(readings)) )

    if virtual:
        logging.info( "[virtual] median power consumption: %f, mean power "\
            "consumption: %f, confidence: %f", median, mean, ci )
    else:
        logging.info( "median power consumption: %f, mean power "\
            "consumption: %f, confidence: %f", median, mean, ci )

    return { 'ci' : ci, 'median' : median, 'mean' : mean }

def run_stint(stint, src, dst, modeller, options):
    """ Run a stint. """

    tx_usecs_udp = PROFILES[options.profile]['tx_usecs_udp']
    tps = 1000000 / tx_usecs_udp(stint['packetsize_bytes'])

    logging.info("maximum transaction speed for this medium (%s) is %d TPS",
                 options.profile, tps )

    logging.info("maximum theoretical goodput is %s",
                 bps_to_human(stint['packetsize_bytes']*8*tps) )

    # reset probes
    src.reset()
    dst.reset()

    # run stint
    src.configure_stint(stint, tps)

    modeller.reset_readings()

    src.start_stint()
    time.sleep(stint['duration_s'])
    src.stop_stint()

def process_stint(stint, src, dst, modeller, options):
    """ Process stint. """

    # compute statistics
    if options.models is None:
        stint['stats'] = process_readings(modeller.get_readings(), False)
    else:
        stint['virtual'] = process_readings(modeller.get_readings(), True)

    src_status = src.status()
    dst_status = dst.status()

    client_count = src_status['client_count']
    server_count = dst_status['server_count']
    client_interval = src_status['client_interval']
    server_interval = dst_status['server_interval']

    logging.info("client sent %u packets in %f s", client_count,
                                                   client_interval )

    logging.info("server received %u packets in %f s", server_count,
                                                       server_interval )

    tp_bps = 0

    if client_interval != 0:
        bits = client_count * stint['packetsize_bytes'] * 8
        tp_bps = float(bits) / client_interval

    gp_bps = 0
    if server_interval != 0:
        bits = server_count * stint['packetsize_bytes'] * 8
        gp_bps = float(bits) / server_interval

    losses = 0
    if client_count != 0:
        losses = float( client_count - server_count ) / client_count

    if not 'stats' in stint:
        stint['stats'] = {}

    stint['stats']['tp'] = tp_bps
    stint['stats']['gp'] = gp_bps
    stint['stats']['losses'] = losses

    logging.info("actual throughput %s", bps_to_human(tp_bps) )
    logging.info("actual goodput %s", bps_to_human(gp_bps) )
    logging.info("packet error rate %u/%u (%f)", client_count,
                                                 server_count,
                                                 losses )

def run_idle_stint(stint, modeller, options):
    """ Run the idle stint. """

    logging.info("evaluating idle power consumption")
    logging.info("idle time is %us", stint['duration_s'] )
    modeller.reset_readings()
    time.sleep(stint['duration_s'])
    readings = modeller.get_readings()

    # compute statistics
    if options.models is None:
        stint['stats'] = process_readings(readings, False)
    else:
        stint['virtual'] = process_readings(readings, True)

def sigint_handler(*_):
    """ Handle SIGINT. """

    logging.info("Received SIGINT, terminating...")
    sys.exit(0)

def main():
    """ Launcher method. """

    parser = optparse.OptionParser()

    parser.add_option('--device', '-d', dest="device", default=DEFAULT_PORT)

    parser.add_option('--bps', '-b',
                      type="int",
                      dest="bps",
                      default=DEFAULT_PORT_SPEED)

    parser.add_option('--interval', '-i',
                      type="int",
                      dest="interval",
                      default=DEFAULT_INTERVAL)

    parser.add_option('--joule', '-j',
                      dest="joule",
                      default=DEFAULT_JOULE)

    parser.add_option('--models', '-m',
                      dest="models",
                      default=None)

    parser.add_option('--profile', '-p',
                      dest="profile",
                      default=DEFAULT_PROFILE)

    parser.add_option('--verbose', '-v',
                      action="store_true",
                      dest="verbose",
                      default=False)

    parser.add_option('--log', '-l', dest="log")

    options, _ = parser.parse_args()

    with open(os.path.expanduser(options.joule)) as data_file:
        data = json.load(data_file)

    if options.models != None:
        with open(os.path.expanduser(options.models)) as data_file:
            models = json.load(data_file)

    if options.verbose:
        logging.basicConfig(level=logging.DEBUG,
                            format=LOG_FORMAT,
                            filename=options.log,
                            filemode='w')
    else:
        logging.basicConfig(level=logging.INFO,
                            format=LOG_FORMAT,
                            filename=options.log,
                            filemode='w')

    signal.signal(signal.SIGINT, sigint_handler)
    signal.signal(signal.SIGTERM, sigint_handler)

    logging.info("starting Joule Profiler")

    # initialize modeller
    if options.models is None:
        meter = PyEnergino(options.device, options.bps, options.interval)
        modeller = Modeller(meter)
    else:
        meter = VirtualMeter(models, options.interval)
        modeller = Modeller(meter)

    # starting modeller
    modeller.start()

    # initialize probe objects
    probes = { x : Probe(data['probes'][x]) for x in data['probes'] }

    # evaluate idle power consumption
    run_idle_stint(data['idle'], modeller, options)

    with open(os.path.expanduser(options.joule), 'w') as data_file:

        json.dump(data,
                  data_file,
                  sort_keys=True,
                  indent=4,
                  separators=(',', ': '))

    # idle
    time.sleep(5)

    # start with the stints
    logging.info("running stints")

    for i in range(0, len(data['stints'])):

        stint = data['stints'][i]

        src = probes[stint['src']]
        dst = probes[stint['dst']]

        logging.info('-----------------------------------------------------')
        logging.info("running profile %u/%u, %s -> %s:%u", i+1,
                                                           len(data['stints']),
                                                           src.address,
                                                           dst.address,
                                                           dst.receiver_port )

        # run stint
        run_stint(stint, src, dst, modeller, options)

        # process stint
        process_stint(stint, src, dst, modeller, options)

        with open(os.path.expanduser(options.joule), 'w') as data_file:
            json.dump(data,
                      data_file,
                      sort_keys=True,
                      indent=4,
                      separators=(',', ': '))

        # sleep in order to let the network settle down
        time.sleep(5)

    # stopping modeller
    modeller.shutdown()

if __name__ == "__main__":
    main()
