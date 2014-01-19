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
from energino import PyEnergino, DEFAULT_PORT, DEFAULT_PORT_SPEED, DEFAULT_INTERVAL
from virtualmeter import VirtualMeter

DEFAULT_JOULE = './joule.json'
LOG_FORMAT = '%(asctime)-15s %(message)s'

def bps_to_human(bps):
    if bps >= 1000000:
        return "%f Mbps" % (float(bps) / 1000000)
    elif bps >= 100000:
        return "%f Kbps" % (float(bps) / 1000)
    else:
        return "%u bps" % bps

def tx_usecs_80211ga_udp(payload, mtu = 1468):
    if payload > mtu:
        return tx_usecs_80211ga_udp(payload / 2, mtu) + tx_usecs_80211ga_udp(payload - (payload / 2), mtu)
    else:
        # assume that transmission always succeed
        avg_cw = 15 * 9
        # payload + UDP header (12) + IP Header (20) + MAC Header (28) + LLC/SNAP Header (8)
        payload = payload + 12 + 20 + 28 + 8;
        # return DIFS + CW + payload + SIFS + ACK
        return int(34 + avg_cw + math.ceil(float(payload * 8) / 216) * 4 + 16 + 24 )

PROFILES = { '11a' : { 'tx_usecs_udp' : tx_usecs_80211ga_udp },
             '11g' : { 'tx_usecs_udp' : tx_usecs_80211ga_udp } }

DEFAULT_PROFILE = '11g'

class Modeller(threading.Thread):

    def __init__(self, backend):

        super(Modeller, self).__init__()
        logging.info("starting meter (%s)" % backend.__class__.__name__)
        self.stop_event = threading.Event()
        self.daemon = True
        self.readings = []
        self.backend = backend

    def reset_readings(self):
        self.readings = []

    def get_readings(self):
        return self.readings[:]

    def shutdown(self):
        logging.info("stopping modeler")
        self.stop_event.set()

    def run(self):
        while not self.stop_event.isSet():
            try:
                self.readings.append(self.backend.fetch('power'))
            except Exception, e:
                self.readings.append(0.0)
                logging.error(e)

class Probe(object):

    def __init__(self, probe):
        self.ip = probe['ip']
        self.sender_control = probe['receiver_control'] + 1
        self.receiver_control = probe['receiver_control']
        self.receiver_port = probe['receiver_port']
        self.reset()

    def _dh(self, handler):
        if handler[0] == "200":
            logging.debug("calling %s (%s)" % (handler[1], handler[0]))
        else:
            logging.error("calling %s (%s)" % (handler[1], handler[0]))
        return handler

    def reset(self):
        logging.info('resetting click send daemon (%s:%s)' % (self.ip, self.sender_control))
        self._dh(write_handler(self.ip, self.sender_control, 'src.active false'))
        self._dh(write_handler(self.ip, self.sender_control, 'src.reset'))
        self._dh(write_handler(self.ip, self.sender_control, 'counter_client.reset'))
        self._dh(write_handler(self.ip, self.sender_control, 'tr_client.reset'))
        logging.info('resetting click recv daemon (%s:%s)' % (self.ip, self.sender_control))
        self._dh(write_handler(self.ip, self.receiver_control, 'counter_server.reset'))
        self._dh(write_handler(self.ip, self.receiver_control, 'tr_server.reset'))
        self._packet_rate = 10
        self._packets_nb = 1000
        self._packetsize_bytes = 64
        self._duration = 10

    def status(self):
        logging.info('fetching click daemon status (%s)' % self.ip)
        status = {}
        status['client_count'] = int(self._dh(read_handler(self.ip, self.sender_control, 'counter_client.count'))[2])
        status['client_interval'] = float(self._dh(read_handler(self.ip, self.sender_control, 'tr_client.interval'))[2])
        status['server_count'] = int(self._dh(read_handler(self.ip, self.receiver_control, 'counter_server.count'))[2])
        status['server_interval'] = float(self._dh(read_handler(self.ip, self.receiver_control, 'tr_server.interval'))[2])
        return status

    def configure_stint(self, stint, tps):

        self._packet_rate = int(float(stint['bitrate_mbps'] * 1000000) / float(stint['packetsize_bytes'] * 8))
        self._packetsize_bytes = stint['packetsize_bytes']
        self._duration = stint['duration_s']
        self._limit = self._packet_rate * self._duration

        logging.info("will send a total of %u packets" % self._limit )
        logging.info("payload length is %u bytes" % self._packetsize_bytes )
        logging.info("transmission rate set to %u pkt/s" % self._packet_rate )
        logging.info("trasmitting time is %us" % self._duration )
        logging.info("target bitrate is %s" % bps_to_human(stint['bitrate_mbps'] * 1000000) )

        self._dh(write_handler(self.ip, self.sender_control, 'src.length %u' % self._packetsize_bytes))
        self._dh(write_handler(self.ip, self.sender_control, 'src.rate %u' % self._packet_rate))
        self._dh(write_handler(self.ip, self.sender_control, 'src.limit %u' % self._limit))
        self._dh(write_handler(self.ip, self.sender_control, 'sha.rate %u' % tps))

    def start_stint(self):
        logging.info("starting probe (%s)" % self.ip)
        self._dh(write_handler(self.ip, self.sender_control, 'src.active true'))

    def stop_stint(self):
        logging.info("stopping probe (%s)" % self.ip)
        self._dh(write_handler(self.ip, self.sender_control, 'src.active false'))

def process_readings(readings, virtual = False):

    median = np.median(readings)
    mean = np.mean(readings)

    ci = 1.96 * (np.std(readings) / np.sqrt(len(readings)) )

    if virtual:
        logging.info("[virtual] median power consumption: %f, mean power consumption: %f, confidence: %f" % (median, mean, ci))
    else:
        logging.info("median power consumption: %f, mean power consumption: %f, confidence: %f" % (median, mean, ci))

    return { 'ci' : ci, 'median' : median, 'mean' : mean }

def run_stint(stint, src, dst, run, tot, ml, options):

    # process stint
    logging.info('-----------------------------------------------------')
    logging.info("running profile %u/%u, %s -> %s:%u" % (run, tot, src.ip, dst.ip, dst.receiver_port))

    tx_usecs_udp = PROFILES[options.profile]['tx_usecs_udp']
    tps = 1000000 / tx_usecs_udp(stint['packetsize_bytes'])

    logging.info("maximum transaction speed for this medium (%s) is %d TPS" % (options.profile, tps) )
    logging.info("maximum theoretical goodput is %s" % bps_to_human(stint['packetsize_bytes'] * 8 * tps) )

    # reset probes
    src.reset()
    dst.reset()

    # run stint
    src.configure_stint(stint, tps)

    ml.reset_readings()

    src.start_stint()
    time.sleep(stint['duration_s'])
    src.stop_stint()

    readings = ml.get_readings()

    # compute statistics
    if options.models is None:
        stint['stats'] = process_readings(readings, False)
    else:
        stint['virtual'] = process_readings(readings, True)

    src_status = src.status()
    dst_status = dst.status()

    client_count = src_status['client_count']
    server_count = dst_status['server_count']
    client_interval = src_status['client_interval']
    server_interval = dst_status['server_interval']

    logging.info("client sent %u packets in %f s" % (client_count, client_interval))
    logging.info("server received %u packets in %f s" % (server_count, server_interval))

    tp = 0
    if client_interval != 0:
        tp = float(client_count * stint['packetsize_bytes'] * 8) / client_interval
    gp = 0
    if server_interval != 0:
        gp = float(server_count * stint['packetsize_bytes'] * 8) / server_interval

    losses = 0
    if client_count != 0:
        losses = float( client_count - server_count ) / client_count

    if not 'stats' in stint:
        stint['stats'] = {}

    stint['stats']['tp'] = tp
    stint['stats']['gp'] = gp
    stint['stats']['losses'] = losses

    logging.info("actual throughput %s" % bps_to_human(tp))
    logging.info("actual goodput %s" % bps_to_human(gp))
    logging.info("packet error rate %u/%u (%f)" % (client_count, server_count, losses))

def run_idle_stint(stint, ml, options):

    logging.info("evaluating idle power consumption")
    logging.info("idle time is %us" % stint['duration_s'] )
    ml.reset_readings()
    time.sleep(stint['duration_s'])
    readings = ml.get_readings()

    # compute statistics
    if options.models is None:
        stint['stats'] = process_readings(readings, False)
    else:
        stint['virtual'] = process_readings(readings, True)

def sigint_handler(signal, frame):
    logging.info("Received SIGINT, terminating...")
    sys.exit(0)

def main():

    p = optparse.OptionParser()
    p.add_option('--device', '-d', dest="device", default=DEFAULT_PORT)
    p.add_option('--bps', '-b', type="int", dest="bps", default=DEFAULT_PORT_SPEED)
    p.add_option('--interval', '-i', type="int", dest="interval", default=DEFAULT_INTERVAL)
    p.add_option('--joule', '-j', dest="joule", default=DEFAULT_JOULE)
    p.add_option('--models', '-m', dest="models", default=None)
    p.add_option('--profile', '-p', dest="profile", default=DEFAULT_PROFILE)
    p.add_option('--verbose', '-v', action="store_true", dest="verbose", default=False)
    p.add_option('--log', '-l', dest="log")
    options, _ = p.parse_args()

    with open(os.path.expanduser(options.joule)) as data_file:
        data = json.load(data_file)

    if options.models != None:
        with open(os.path.expanduser(options.models)) as data_file:
            models = json.load(data_file)

    if options.verbose:
        logging.basicConfig(level=logging.DEBUG, format=LOG_FORMAT, filename=options.log, filemode='w')
    else:
        logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, filename=options.log, filemode='w')

    signal.signal(signal.SIGINT, sigint_handler)
    signal.signal(signal.SIGTERM, sigint_handler)

    logging.info("starting Joule Profiler")

    # initialize modeller
    if options.models is None:
        ml = Modeller(PyEnergino(options.device, options.bps, options.interval))
    else:
        ml = Modeller(VirtualMeter(models, options.interval))

    # starting modeller
    ml.start()

    # initialize probe objects
    probes = { probe : Probe(data['probes'][probe]) for probe in data['probes'] }

    # evaluate idle power consumption
    run_idle_stint(data['idle'], ml, options)

    with open(os.path.expanduser(options.joule), 'w') as data_file:
        json.dump(data, data_file, sort_keys=True, indent=4, separators=(',', ': '))

    # idle
    time.sleep(5)

    # start with the stints
    logging.info("running stints")

    for i in range(0, len(data['stints'])):

        stint = data['stints'][i]

        src = probes[stint['src']]
        dst = probes[stint['dst']]

        run_stint(stint, src, dst, i+1, len(data['stints']), ml, options)

        with open(os.path.expanduser(options.joule), 'w') as data_file:
            json.dump(data, data_file, sort_keys=True, indent=4, separators=(',', ': '))

        # sleep in order to let the network settle down
        time.sleep(5)

    # stopping modeller
    ml.shutdown()

if __name__ == "__main__":
    main()
