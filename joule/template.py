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

The Joule Template. It generate a Joule descriptor to be used with the Joule 
Daemon(s) and with the Joule Profiler. The generated descriptor defines two
probes and a list of rates and packet sizes. Stints are defined as all the 
possible permutations between the rates list and the packets sizes list. It
is possible to define also the duration of each stint. By default the 
descriptor is ~/joule.json. The default behavior is the following:

profiler -a 127.0.0.1 -b 127.0.01 -r "1 2 4 8" -s "64 1000 1460" -d 5

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

    if options.verbose:
        logging.basicConfig(level=logging.DEBUG, format=LOG_FORMAT, filename=options.log, filemode='w')
    else:
        logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, filename=options.log, filemode='w')

    joule = { 'probes' : {}, 'stints' : [] }

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
    
    joule['probes'] = {
        "A": {
            "ip": options.probea,
            "receiver": options.probeb,
            "sender_port": 9997,
            "receiver_port": 9998,
            "receiver_control": 8888,
            "sender_control": 8889
        },
        "B": {
            "ip": options.probeb,
            "receiver": options.probea,
            "sender_port": 9998,
            "receiver_port": 9997,
            "receiver_control": 7777,
            "sender_control": 7778
        }
    }

    with open(os.path.expanduser(options.joule), 'w') as data_file:    
        json.dump(joule, data_file, sort_keys=True, indent=4, separators=(',', ': '))
            
if __name__ == "__main__":
    main()
