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
import optparse
import logging 
import sys
import numpy as np
import scipy.io

from energino import PyEnergino, DEFAULT_PORT, DEFAULT_PORT_SPEED, DEFAULT_INTERVAL
from virtualmeter import VirtualMeter

DEFAULT_MODELS = './models.json'
LOG_FORMAT = '%(asctime)-15s %(message)s'

def main():

    p = optparse.OptionParser()
    p.add_option('--device', '-d', dest="device", default=DEFAULT_PORT)
    p.add_option('--bps', '-b', dest="bps", type="int", default=DEFAULT_PORT_SPEED)
    p.add_option('--interval', '-i', dest="interval", type="int", default=DEFAULT_INTERVAL)
    p.add_option('--models', '-m', dest="models", default=DEFAULT_MODELS)
    p.add_option('--matlab', '-t', dest="matlab")
    p.add_option('--verbose', '-v', action="store_true", dest="verbose", default=False)    
    p.add_option('--log', '-l', dest="log")
    options, _ = p.parse_args()

    with open(os.path.expanduser(options.models)) as data_file:    
        models = json.load(data_file)

    if options.verbose:
        logging.basicConfig(level=logging.DEBUG, format=LOG_FORMAT, filename=options.log, filemode='w')
    else:
        logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, filename=options.log, filemode='w')

    energino = PyEnergino(options.device, options.bps, options.interval)
    virtual = VirtualMeter(models, 0)

    if options.matlab != None:
        mat = []

    while True:
        energino.ser.flushInput()
        try:
            readings = energino.fetch()
            virtual_readings = virtual.fetch()
        except KeyboardInterrupt:
            logging.debug("Bye!")
            sys.exit()
        except:
            logging.debug("%s [V] %s [A] %s [W] %s [samples] %s [window] %s [virtual] %s [error]" % tuple(["0.0"] * 7))
        else:
            if options.matlab != None:
                mat.append((readings['voltage'], readings['current'], readings['power'], readings['samples'], readings['window'], virtual_readings['power'], virtual_readings['power'] - readings['power']))
            logging.info("%s [V] %s [A] %s [W] %s [samples] %s [window] %s [virtual] %s [error]" % (readings['voltage'], readings['current'], readings['power'], readings['samples'], readings['window'], virtual_readings['power'], virtual_readings['power'] - readings['power']))

        if options.matlab != None:
            scipy.io.savemat(options.matlab, { 'READINGS' : np.array(mat) }, oned_as = 'column')

if __name__ == "__main__":
    main()
