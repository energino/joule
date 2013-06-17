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
import optparse
import logging 

LOG_FORMAT = '%(asctime)-15s %(message)s'
DEFAULT_JOULE = '~/joule.json'
DEFAULT_PROBE_A = "127.0.0.1"
DEFAULT_PROBE_B = "127.0.0.1"
DEFAULT_RATES = "1 2 4 8"
DEFAULT_SIZES = "64 1000 1460"
DEFAULT_DURATION = 5

def main():

    p = optparse.OptionParser()
    p.add_option('--joule', '-j', dest="joule", default=DEFAULT_JOULE)
    p.add_option('--probea', '-a', dest="probea", default=DEFAULT_PROBE_A)
    p.add_option('--probeb', '-b', dest="probeb", default=DEFAULT_PROBE_B)
    p.add_option('--rates', '-r', dest="rates", default=DEFAULT_RATES)
    p.add_option('--sizes', '-s', dest="sizes", default=DEFAULT_SIZES)
    p.add_option('--duration', '-d', dest="duration", default=DEFAULT_DURATION)
    p.add_option('--verbose', '-v', action="store_true", dest="verbose", default=False)    
    p.add_option('--log', '-l', dest="log")
    options, _ = p.parse_args()

    expanded_path = os.path.expanduser(options.joule)

    if options.verbose:
        lvl = logging.DEBUG
    else:
        lvl = logging.INFO

    logging.basicConfig(level=lvl, format=LOG_FORMAT, filename=options.log, filemode='w')

    joule = { 'probes' : {}, 'stints' : [], 'models' : {} }

    for rate in options.rates.split(" "):
        
        for size in options.sizes.split(" "):
            
            stint = {
                "bitrate_mbps": int(rate),
                "dst": "A",
                "duration_s": int(options.duration),
                "packetsize_bytes": int(size),
                "src": "B"
            }   

            joule['stints'].append(stint)

            stint = {
                "bitrate_mbps": int(rate),
                "dst": "B",
                "duration_s": int(options.duration),
                "packetsize_bytes": int(size),
                "src": "A"
            }   

            joule['stints'].append(stint)
    
    joule['models'] = { 'rx_bitrate' : { 'src' : 'A', 
                                            'dst': 'B', 
                                            'select' : 'bitrate_mbps', 
                                            'group_by' : 'packetsize_bytes', 
                                            'lambda' : 'lambda x, a, b: a*x + b' }, 
                        'rx_packetsize' : { 'src' : 'A', 
                                         'dst': 'B', 
                                         'select' : 'packetsize_bytes', 
                                         'group_by' : 'bitrate_mbps', 
                                         'lambda' : 'lambda x, a, b: -a*x + b' },
                        'tx_bitrate' : { 'src' : 'B', 
                                            'dst': 'A', 
                                            'select' : 'bitrate_mbps', 
                                            'group_by' : 'packetsize_bytes', 
                                            'lambda' : 'lambda x, a, b: a*x + b' }, 
                        'tx_packetsize' : { 'src' : 'B', 
                                         'dst': 'A', 
                                         'select' : 'packetsize_bytes', 
                                         'group_by' : 'bitrate_mbps', 
                                         'lambda' : 'lambda x, a, b: -a*x + b' }                       
                       } 

    joule['probes'] = {
        "A": {
            "ip": options.probea,
            "receiver_port": 9998,
            "receiver_control": 8888
        },
        "B": {
            "ip": options.probeb,
            "receiver_port": 9997,
            "receiver_control": 7777
        }
    }

    with open(expanded_path, 'w') as data_file:    
        json.dump(joule, data_file, sort_keys=True, indent=4, separators=(',', ': '))
            
if __name__ == "__main__":
    main()
