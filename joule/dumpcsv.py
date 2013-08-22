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
Joule Dump CSV. The dumpcsv commands outputs the content of a Joule descriptor
to CSV format. Noticice that the Joule descriptor must be the one saved by the
Joule profiler, i.e. it must contain the power consumption statistics. The csv
is printed to the standard output.
"""

import os
import json
import optparse

DEFAULT_JOULE = './joule.json'

def main():

    p = optparse.OptionParser()
    p.add_option('--joule', '-j', dest="joule", default=DEFAULT_JOULE)
    p.add_option('--byrate', '-r', action="store_true", dest="byrate", default=False)    
    options, _ = p.parse_args()

    with open(os.path.expanduser(options.joule)) as data_file:    
        data = json.load(data_file)

    pairs = {}
    
    for stint in data['stints']:
        probe_ids = ( stint['src'], stint['dst'] )
        if not probe_ids in pairs:
            pairs[probe_ids] = []
        pairs[probe_ids].append([ stint['bitrate_mbps'], stint['packetsize_bytes'], stint['stats']['losses'], stint['stats']['median'], stint['stats']['mean']])

    for entry in pairs:
        print("# %s -> %s" % (data['probes'][entry[0]]['ip'], data['probes'][entry[1]]['ip']))
        print("# bitrate, packet length, packet loss, median power consumption, mean power consumption")
        if options.byrate:
            print("\n".join([ "%f;%f;%f;%f;%f" % tuple(line) for line in sorted(pairs[entry], key=lambda d: (d[1], d[0]), reverse=False) ]))
        else:
            print("\n".join([ "%f;%f;%f;%f;%f" % tuple(line) for line in sorted(pairs[entry], key=lambda d: (d[0], d[1]), reverse=False) ]))

if __name__ == "__main__":
    main()
