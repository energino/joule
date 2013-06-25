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
import numpy

from click import read_handler, write_handler
from energino import PyEnergino, DEFAULT_PORT, DEFAULT_PORT_SPEED, DEFAULT_INTERVAL

LOG_FORMAT = '%(asctime)-15s %(message)s'
DEFAULT_JOULE = '~/joule.json'

class Modeller(threading.Thread):
    
    def __init__(self, options):

        super(Modeller, self).__init__()
        self.stop_event = threading.Event()
        self.daemon = True
        self.interval = int(options.interval)
        self.device = options.device
        self.bps = options.bps
        self.readings = []
        logging.info("starting energino")
        self.energino = PyEnergino(self.device, self.bps, self.interval)

    def run(self):
        while not self.stop_event.isSet():
            try:
                readings = self.energino.fetch()
                self.readings.append(readings['power'])
            except:
                pass

    def shutdown(self):
        logging.info("stopping energino")
        self.energino.ser.close()
        self.stop_event.set()
        time.sleep(2)

class VirtualModeller(threading.Thread):
    
    def __init__(self, interval, bitrate, packetsize):
        super(VirtualModeller, self).__init__()
        self.stop = threading.Event()
        self.daemon = True
        self.bitrate = bitrate
        self.packetsize = packetsize
        self.interval = interval
        self.readings = []

    def compute_virtual_power(self, bitrate, packetsize):
        from random import randint
        r = float(randint(1,1000) - 500) / 20000
        if bitrate > 20:
            base = 4.6
        else:
            base = bitrate * 0.04 + 3.84
        if packetsize <= 60:
            corr = 5.595 - 3.84
        else:
            corr = -0.2287 * math.log(packetsize) + 5.595 - 3.84
        return base + corr + r
        
    def run(self):
        logging.info("starting virtual energino")
        while True:
            self.readings.append(self.compute_virtual_power(self.bitrate, self.packetsize))
            time.sleep(float(self.interval) / 1000)

    def shutdown(self):
        logging.info("stopping virtual energino")
        self.stop.set()
        
def sigint_handler(signal, frame):
    logging.info("Received SIGINT, terminating...")
    global ml
    ml.shutdown()
    sys.exit(0)

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
        logging.info('resetting click sender daemon (%s:%s)' % (self.ip, self.sender_control))
        self._dh(write_handler(self.ip, self.sender_control, 'src.active false'))
        self._dh(write_handler(self.ip, self.sender_control, 'src.reset'))
        self._dh(write_handler(self.ip, self.sender_control, 'counter_client.reset'))
        self._dh(write_handler(self.ip, self.sender_control, 'tr_client.reset'))
        logging.info('resetting click recevier daemon (%s:%s)' % (self.ip, self.sender_control))
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

    def _bps_to_human(self, bps):
        if bps >= 1000000:
            return "%u Mbps" % (float(bps) / 1000000)
        elif bps >= 100000:
            return "%u Kbps" % (float(bps) / 1000)
        else:
            return "%u bps" % bps

    def execute_stint(self, stint):
        
        self._packet_rate = int(float(stint['bitrate_mbps'] * 1000000) / float(stint['packetsize_bytes'] * 8))
        
        self._packets_nb = stint['duration_s'] * self._packet_rate
        self._packetsize_bytes = stint['packetsize_bytes'] 
        self._duration = stint['duration_s'] 

        logging.info("payload length is %u bytes" % self._packetsize_bytes )
        logging.info("transmission rate set to %u pkt/s" % self._packet_rate )
        logging.info("trasmitting a total of %u packets" % self._packets_nb )
        logging.info("trasmitting time is %us" % self._duration )
        logging.info("target bitrate is %s" % self._bps_to_human(stint['bitrate_mbps'] * 1000000) )         

        self._set_length(self._packetsize_bytes)
        self._set_rate(self._packet_rate)
        self._set_limit(self._packets_nb)

        self._start()
        logging.info("running stint...")
        time.sleep(self._duration)
        self._stop()

    def _set_length(self, length):
        self._dh(write_handler(self.ip, self.sender_control, 'src.length %s' % length))

    def _set_rate(self, rate):
        self._dh(write_handler(self.ip, self.sender_control, 'src.rate %s' % rate))

    def _set_limit(self, limit):
        self._dh(write_handler(self.ip, self.sender_control, 'src.limit %s' % limit))

    def _start(self):
        logging.info("starting probe (%s)" % self.ip)
        self._dh(write_handler(self.ip, self.sender_control, 'src.active true'))

    def _stop(self):
        logging.info("stopping probe (%s)" % self.ip)
        self._dh(write_handler(self.ip, self.sender_control, 'src.active false'))

def main():

    p = optparse.OptionParser()
    p.add_option('--device', '-d', dest="device", default=DEFAULT_PORT)
    p.add_option('--interval', '-i', dest="interval", default=DEFAULT_INTERVAL)
    p.add_option('--bps', '-b', dest="bps", default=DEFAULT_PORT_SPEED)
    p.add_option('--joule', '-j', dest="joule", default=DEFAULT_JOULE)
    p.add_option('--verbose', '-v', action="store_true", dest="verbose", default=False)    
    p.add_option('--virtual', '-e', action="store_true", dest="virtual", default=False)    
    p.add_option('--log', '-l', dest="log")
    options, _ = p.parse_args()

    expanded_path = os.path.expanduser(options.joule)

    with open(expanded_path) as data_file:    
        data = json.load(data_file)

    if options.verbose:
        logging.basicConfig(level=logging.DEBUG, format=LOG_FORMAT, filename=options.log, filemode='w')
    else:
        logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, filename=options.log, filemode='w')

    signal.signal(signal.SIGINT, sigint_handler)
    signal.signal(signal.SIGTERM, sigint_handler)

    logging.info("starting eJOULE profiler")

    logging.info("measuring idle power consumption")
    
    global ml

    probeObjs = {}

    for probe in data['probes']:
        probeObjs[probe] = Probe(data['probes'][probe])

    for i in range(0, len(data['stints'])):

        stint = data['stints'][i]

        src = probeObjs[stint['src']]
        dst = probeObjs[stint['dst']]

        # run stint
        logging.info('-----------------------------------------------------')
        logging.info("running profile %u/%u, %s -> %s:%u" % (i+1, len(data['stints']), src.ip, dst.ip, dst.receiver_port))

        # reset probes
        src.reset()
        dst.reset()

        if options.virtual:
            ml = VirtualModeller(options.interval, stint['bitrate_mbps'], stint['packetsize_bytes'])
        else:
            ml = Modeller(options)
            
        ml.start()
        src.execute_stint(stint)
        ml.shutdown()

        stint['results'] = {}
        stint['results'][stint['src']] = src.status()
        stint['results'][stint['dst']] = dst.status()
        
        median = numpy.median(ml.readings)
        mean = numpy.mean(ml.readings)
        ci = 1.96 * (numpy.std(ml.readings) / numpy.sqrt(len(ml.readings)) )

        client_count = stint['results'][stint['src']]['client_count']
        server_count = stint['results'][stint['dst']]['server_count']
        
        client_interval = stint['results'][stint['src']]['client_interval']
        server_interval = stint['results'][stint['dst']]['server_interval']
        
        tp = float(client_count * stint['packetsize_bytes'] * 8) / client_interval
        gp = float(server_count * stint['packetsize_bytes'] * 8) / server_interval
        
        losses = float( client_count - server_count ) / client_count
        
        stint['stats'] = { 'ci' : ci, 'median' : median, 'mean' : mean, 'losses' : losses, 'tp' : tp, 'gp' : gp }
        
        with open(expanded_path, 'w') as data_file:    
            json.dump(data, data_file, sort_keys=True, indent=4, separators=(',', ': '))
        
if __name__ == "__main__":
    main()
