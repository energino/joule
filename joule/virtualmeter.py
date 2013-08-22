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

import sys
import optparse
import logging
import numpy as np
import time
import json
import os
import datetime

from click import write_handler

DEFAULT_MODELS = './models.json'
DEFAULT_INTERVAL = 2000

LOG_FORMAT = '%(asctime)-15s %(message)s'

def compute_power(alpha0, alpha1, x_min, x_max, beta, gamma, x, d):
    if x < x_min:
        return gamma
    if x > x_max[str(d)]:
        x = x_max[str(d)]
    alpha_d = alpha0 * ( 1 + (alpha1 / d))
    return alpha_d * x + beta[str(d)] + gamma

class VirtualMeter(object):
    
    def __init__(self, models, interval):
        
        self.models = models
        self.interval = interval
        
        self.packet_sizes = {}
        self.packet_sizes['RX'] = sorted([ int(x) for x in self.models['RX']['x_max'].keys() ], key=int)
        self.packet_sizes['TX'] = sorted([ int(x) for x in self.models['TX']['x_max'].keys() ], key=int)

        self.bins = {}
        self.bins['RX'] = self.generate_bins('RX')
        self.bins['TX'] = self.generate_bins('TX')
        
        self.last = time.time()
        
    def fetch(self, field = None):

        if self.interval > 0:
            time.sleep(float(self.interval) / 1000)

        delta = time.time() - self.last
        self.last = time.time()

        bins = {}
        bins['RX'] = self.generate_bins('RX')
        bins['TX'] = self.generate_bins('TX')

        power_rx = self.compute(bins['RX'], self.bins['RX'], 'RX', delta)
        power_tx = self.compute(bins['TX'], self.bins['TX'], 'TX', delta)

        self.bins['RX'] = bins['RX'][:]
        self.bins['TX'] = bins['TX'][:]

        readings = {}
        readings['power'] = power_tx + power_rx + self.models['gamma'] 
        readings['at'] = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                
        if field != None:
            return readings[field]
        return readings
  
    def compute(self, bins_curr, bins_prev, model, delta):
        
        power = 0.0

        diff = [ x[0] for x in (bins_curr - bins_prev).tolist() ]

        alpha0 = self.models[model]['alpha0']
        alpha1 = self.models[model]['alpha1']
        x_max = self.models[model]['x_max']
        beta = self.models[model]['beta']
        gamma = self.models['gamma']

        # this should be generalized        
        x_min = 0.06

        for i in range(0, len(diff)):
            if diff[i] == 0.0:
                continue
            x = ( ( self.packet_sizes[model][i] * diff[i] * 8 ) / delta ) / 1000000
            d = self.packet_sizes[model][i]
            p = compute_power(alpha0, alpha1, x_min, x_max, beta, gamma, x, d) - gamma
            power = power + p
            logging.debug("%u bytes, %u pkts, %f s -> %f [Mb/s] %f [W]" % (d, diff[i], delta, x, p))
            
        return power

    def generate_bins(self, model):
        results = write_handler('127.0.0.1', 5555, "%s.write_text_file /tmp/%s" % (model, model))
        if results[0] != '200':
            return np.array([])
        time.sleep(0.1)
        try:
            A = np.genfromtxt('/tmp/%s' % model, dtype=int, comments="!")
        except IOError:
            A = np.array([[]])
        bins = np.zeros(shape=(len(self.packet_sizes[model]),1))
        if np.ndim(A) != 2:
            return bins
        for a in A:
            if len(a) == 0:
                continue
            size = a[0]
            count = a[1]
            for i in range(0, len(self.packet_sizes[model])):
                if size <= self.packet_sizes[model][i]:
                    bins[i] = bins[i] + count
                    break
        return bins
                
def main():

    p = optparse.OptionParser()

    p.add_option('--interval', '-i', dest="interval", type="int", default=DEFAULT_INTERVAL)
    p.add_option('--models', '-m', dest="models", default=DEFAULT_MODELS)
    p.add_option('--matlab', '-t', dest="matlab")
    p.add_option('--verbose', '-v', action="store_true", dest="verbose", default=False)    
    p.add_option('--log', '-l', dest="log")
    
    options, _ = p.parse_args()

    with open(os.path.expanduser(options.models)) as data_file:    
        models = json.load(data_file)

    if options.verbose:
        lvl = logging.DEBUG
    else:
        lvl = logging.INFO
    
    logging.basicConfig(level=lvl, format=LOG_FORMAT, filename=options.log, filemode='w')
    
    vm = VirtualMeter(models, options.interval)

    if options.matlab != None:
        mat = []
    
    while True:
        try:
            readings = vm.fetch()
        except KeyboardInterrupt:
            logging.debug("Bye!")
            sys.exit()
        except:
            logging.debug("0 [W]")
        else:
            logging.info("%f [W]" % readings['power'])

        if options.matlab != None:
            scipy.io.savemat(options.matlab, { 'READINGS' : np.array(mat) }, oned_as = 'column')
    
if __name__ == "__main__":
    main()
    
