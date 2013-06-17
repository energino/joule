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
A command line utility for interfacing with the energino power 
consumption monitor.
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

from energino import PyEnergino
from click import read_handler, write_handler

DEFAULT_DEVICE = '/dev/ttyACM0'
DEFAULT_DEVICE_SPEED = 115200
DEFAULT_INTERVAL = 500
LOG_FORMAT = '%(asctime)-15s %(message)s'
DEFAULT_JOULE = '~/joule.json'

class ModellerLogger(threading.Thread):
    
    def __init__(self, options, virtual=False, stint=None):

        super(ModellerLogger, self).__init__()
        self.stop = threading.Event()
        self.daemon = True
        self.virtual = virtual
        self.interval = int(options.interval)
        self.device = options.device
        self.bps = options.bps
        self.bitrate = stint['bitrate_mbps']
        self.packetsize = stint['packetsize_bytes']
        self.readings = []

    def compute_virtual_power(self, bitrate, packetsize):

        from random import randint

        r = float(randint(1,1000))/10000

        if bitrate == 0:
            return 3.84 + r

        if bitrate > 20:
            return 4.6 + r

        base = bitrate * 0.0259 + 3.84

        if packetsize < 64:
            corr = 5.595 - 3.84
        else:
            corr = -0.2287 * math.log(packetsize) + 5.595 - 3.84

        return base + corr + r
        
    def run(self):
        
        logging.info("starting modeler")

        if not self.virtual:
            energino = PyEnergino(self.device, self.bps, self.interval)

        while True:
            if not self.virtual:
                energino.ser.flushInput()
                readings = energino.fetch()
                self.readings.append(readings['power'])
            else:
                pw =  self.compute_virtual_power(self.bitrate, self.packetsize)
                self.readings.append(pw)
                time.sleep(float(self.interval) / 1000)

    def shutdown(self):
        logging.info("stopping modeler")
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

    def execute_stint(self, stint):
        
        self._packet_rate = int(stint['bitrate_mbps'] * 1000000 / (stint['packetsize_bytes'] * 8))
        self._packets_nb = stint['duration_s'] * self._packet_rate
        self._packetsize_bytes = stint['packetsize_bytes'] 
        self._duration = stint['duration_s'] 

        logging.info("payload length is %u bytes" % self._packetsize_bytes )
        logging.info("transmission rate set to %u pkt/s" % self._packet_rate )
        logging.info("trasmitting a total of %u packets" % self._packets_nb )
        logging.info("trasmitting time is %u s" % self._duration )
        logging.info("target bitrate is %u bps" % ( self._packet_rate * 8 * self._packetsize_bytes / 2) )         

        self._set_length(self._packetsize_bytes)
        self._set_rate(self._packet_rate)
        self._set_limit(self._packets_nb)

        self._start()
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
    p.add_option('--device', '-d', dest="device", default=DEFAULT_DEVICE)
    p.add_option('--interval', '-i', dest="interval", default=DEFAULT_INTERVAL)
    p.add_option('--bps', '-b', dest="bps", default=DEFAULT_DEVICE_SPEED)
    p.add_option('--joule', '-j', dest="joule", default=DEFAULT_JOULE)
    p.add_option('--verbose', '-v', action="store_true", dest="verbose", default=False)    
    p.add_option('--log', '-l', dest="log")
    options, _ = p.parse_args()

    expanded_path = os.path.expanduser(options.joule)

    with open(expanded_path) as data_file:    
        data = json.load(data_file)
    
    probes = data['probes']
    stints = data['stints']

    if options.verbose:
        lvl = logging.DEBUG
    else:
        lvl = logging.INFO

    logging.basicConfig(level=lvl, format=LOG_FORMAT, filename=options.log, filemode='w')

    signal.signal(signal.SIGINT, sigint_handler)
    signal.signal(signal.SIGTERM, sigint_handler)

    logging.info("starting eJOULE modeler")
    
    global ml

    probeObjs = {}

    for probe in probes:
        probeObjs[probe] = Probe(probes[probe])

    for i in range(0, len(stints)):

        stint = stints[i]

        src = probeObjs[stint['src']]
        dst = probeObjs[stint['dst']]

        # run tests (A->B)
        state = (i+1, len(stints), src.ip, dst.ip, dst.receiver_port)
        logging.info("running profile %u/%u, %s -> %s:%u" % state)

        # reset probes
        src.reset()
        dst.reset()

        ml = ModellerLogger(options, True, stint)
        ml.start()

        src.execute_stint(stint)

        ml.shutdown()

        stint['results'] = {}
        stint['results'][stint['src']] = src.status()
        stint['results'][stint['dst']] = dst.status()
        
        median = numpy.median(ml.readings)
        mean = numpy.mean(ml.readings)

        client_count = stint['results'][stint['src']]['client_count']
        server_count = stint['results'][stint['dst']]['server_count']
        losses = ( client_count - server_count ) / client_count
        
        stint['stats'] = { 'median' : median, 'mean' : mean, 'losses' : losses }

        with open(expanded_path, 'w') as data_file:    
            json.dump(data, data_file, sort_keys=True, indent=4, separators=(',', ': '))
            
if __name__ == "__main__":
    main()
