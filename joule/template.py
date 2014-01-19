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

The Joule Template generator.

It generates a Joule descriptor to be used with the Joule Daemon(s) and with
the Joule Profiler. The generated descriptor defines two
probes and a list of rates and packet sizes. Stints are defined as all the
possible permutations between the rates list and the packets sizes list. It
is possible to define also the duration of each stint. By default the
descriptor is ~/joule.json.

Command Line Arguments:

  --joule, -j:      output joule descriptor, e.g. ~/joule.json
  --probea, -a:     probe A's IP Address, e.g. 192.168.1.1
  --probeb, -b:     probe B's IP Address, e.g. 192.168.1.2
  --rates, -r:      list of transmission rates, e.g. "0.1 0.5 1"
  --sizes, -s:      list probe sizes in bytes (UDP payload), e.g. "64 128, 256"
  --duration, -d:   probe duration in seconds, e.g. 30

The default behavior is the following:

template -j ./joule.json
         -a 127.0.0.1 \
         -b 127.0.0.1 \
         -r "0.1 0.5 1 2 5 10 15 20 25 30 35 40" \
         -s "32 64 128 256 384 512 640 768 1024 1280 1460 1534 1788 2048" \
         -d 30

"""

import os
import json
import optparse
import logging

DEFAULT_PROBE_A = "127.0.0.1"
DEFAULT_PROBE_B = "127.0.0.1"
DEFAULT_RATES = "0.1 0.5 1 2 5 10 15 20 25 30 35 40"
DEFAULT_SIZES = "64 128 256 384 512 640 768 1024 1280 1460 1534 1788 2048"
DEFAULT_DURATION = 30

DEFAULT_JOULE = './joule.json'
LOG_FORMAT = '%(asctime)-15s %(message)s'

def main():
    """ Launcher method. """

    parser = optparse.OptionParser()
    parser.add_option('--joule', '-j', dest="joule", default=DEFAULT_JOULE)
    parser.add_option('--probea', '-a', dest="probea", default=DEFAULT_PROBE_A)
    parser.add_option('--probeb', '-b', dest="probeb", default=DEFAULT_PROBE_B)
    parser.add_option('--rates', '-r', dest="rates", default=DEFAULT_RATES)
    parser.add_option('--sizes', '-s', dest="sizes", default=DEFAULT_SIZES)
    parser.add_option('--duration', '-d',
                      dest="duration",
                      type="int",
                      default=DEFAULT_DURATION)
    parser.add_option('--verbose', '-v',
                      action="store_true",
                      dest="verbose",
                      default=False)
    parser.add_option('--log', '-l', dest="log")
    options, _ = parser.parse_args()

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

    joule = { 'probes' : {}, 'models' : {}, 'stints' : [] }

    for rate in options.rates.split(" "):

        for size in options.sizes.split(" "):

            stint = {
                "bitrate_mbps": float(rate),
                "dst": "A",
                "duration_s": options.duration,
                "packetsize_bytes": int(size),
                "src": "B"
            }

            joule['stints'].append(stint)

            stint = {
                "bitrate_mbps": float(rate),
                "dst": "B",
                "duration_s": options.duration,
                "packetsize_bytes": int(size),
                "src": "A"
            }

            joule['stints'].append(stint)

    joule['idle'] = { "duration_s": options.duration }

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

    joule['models'] = {
        "TX": {
            "src": "A",
            "dst": "B"
        },
        "RX": {
            "src": "B",
            "dst": "A"
        }
    }

    with open(os.path.expanduser(options.joule), 'w') as data_file:
        json.dump(joule, data_file, sort_keys=True, indent=4,
                  separators=(',', ': '))

if __name__ == "__main__":
    main()
