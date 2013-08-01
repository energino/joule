#!/usr/bin/env python
#
# Copyright (c) 2012, Roberto Riggio
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
The Joule Virtual Power Meter
"""

import signal
import uuid
import sys
import optparse
import logging
import time

from energino import PyEnergino
from xively_client import Dispatcher, DEFAULT_CONFIG, LOG_FORMAT, BACKOFF    
    
class VirtualMeter(Dispatcher):
        
    def start(self):
        
        # start dispatcher
        self.dispatcher.add_stream("voltage", "derivedSI", "Volts", "V")
        self.dispatcher.add_stream("current", "derivedSI", "Amperes", "A")
        self.dispatcher.add_stream("power", "derivedSI", "Watts", "W")
        self.dispatcher.add_stream("switch", "derivedSI", "Switch", "S")
        self.dispatcher.start()
        
        # start pool loop
        while True:
            try:
                # configure feed
                self.discover()
                # setup serial port
                energino = PyEnergino(self.device, self.bps, self.interval)
                # start updating
                logging.info("begin polling")
                while True:
                    if self.stop.isSet():
                        return
                    try:
                        readings = energino.fetch()
                        logging.debug("appending new readings: %s [V] %s [A] %s [W] %u [Q]" % (readings['voltage'], readings['current'], readings['power'], len(self.dispatcher.outgoing)))
                        self.dispatcher.enqueue(readings)
                    except:
                        logging.warning("sample lost")
            except Exception:
                logging.exception("exception, backing off for %u seconds" % BACKOFF)
                time.sleep(BACKOFF)
        # thread stopped
        logging.info("thread %s stopped" % self.__class__.__name__) 

def sigint_handler(signal, frame):
    global vm
    vm.shutdown()
    sys.exit(0)

def main():

    p = optparse.OptionParser()
    p.add_option('--uuid', '-u', dest="uuid", default=uuid.getnode())
    p.add_option('--config', '-c', dest="config", default=DEFAULT_CONFIG)
    p.add_option('--log', '-l', dest="log")
    p.add_option('--debug', '-d', action="store_true", dest="debug", default=False)       
    options, _ = p.parse_args()

    if options.debug:
        lvl = logging.DEBUG
    else:
        lvl = logging.INFO

    if options.log != None:
        logging.basicConfig(level=lvl, format=LOG_FORMAT, filename=options.log, filemode='w')
    else:
        logging.basicConfig(level=lvl, format=LOG_FORMAT)

    signal.signal(signal.SIGINT, sigint_handler)
    signal.signal(signal.SIGTERM, sigint_handler)

    global vm
    
    vm = VirtualMeter(options.uuid, options.config)
    vm.start()   
         
    signal.signal(signal.SIGINT, sigint_handler)
    signal.signal(signal.SIGTERM, sigint_handler)
        
if __name__ == "__main__":
    main()
    