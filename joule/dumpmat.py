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
Joule Dump Mat The dumpmat command saves the content of the Joule descriptor and
the Joule model file in Matlab format. The Matfile
"""

import os
import json
import optparse
import sqlite3
import numpy as np
import scipy.io

DEFAULT_JOULE = '~/joule.json'
DEFAULT_MODELS = '~/models.json'
DEFAULT_OUTPUT_PREFIX = '~/joule'

def main():

    p = optparse.OptionParser()
    p.add_option('--joule', '-j', dest="joule", default=DEFAULT_JOULE)
    p.add_option('--models', '-m', dest="models", default=DEFAULT_MODELS)
    p.add_option('--output', '-o', dest="output", default=DEFAULT_OUTPUT_PREFIX)
    options, _ = p.parse_args()

    # dump joule descriptor
    with open(os.path.expanduser(options.joule)) as data_file:    
        data = json.load(data_file)

    conn = sqlite3.connect(':memory:')
    c = conn.cursor()
    c.execute('''create table data (src, dst, bitrate_mbps, packetsize_bytes, losses, median, mean)''')
    conn.commit()

    for stint in data['stints']:
        row = [ stint['src'], stint['dst'], stint['bitrate_mbps'], stint['packetsize_bytes'], stint['stats']['losses'], stint['stats']['median'], stint['stats']['mean']]
        c.execute("""insert into data values (?,?,?,?,?,?,?)""", row)
        conn.commit()

    pairs =[]
    c.execute("select src, dst from data group by src, dst")
    for row in c:
        pairs.append(row)

    rates =[]
    c.execute("select bitrate_mbps from data group by bitrate_mbps")
    for row in c:
        rates.append(row)
            
    sizes =[]
    c.execute("select packetsize_bytes from data group by packetsize_bytes")
    for row in c:
        sizes.append(row)

    for pair in pairs:

        datum = []
        
        c.execute("select bitrate_mbps, packetsize_bytes, losses, median, mean from data where src = \"%s\" and dst = \"%s\"" % tuple(pair))
        for row in c:
            datum.append(row)

        with open(os.path.expanduser(options.models)) as data_file:    
            models = json.load(data_file)

        model_rates = []
        model_sizes = []

        for model in models.values():
    
            if model['src'] == pair[0] and model['dst'] == pair[1]:

                if model['select'] == 'bitrate_mbps':
                    for group in model['groups']:
                        model_sizes.append([ float(group) ] + model['groups'][group]['params'])
                    
                if model['select'] == 'packetsize_bytes':
                    for group in model['groups']:
                        model_rates.append([ float(group) ] + model['groups'][group]['params'])

        filename = os.path.expanduser(options.output + '_%s_%s.mat' % tuple(pair))
        scipy.io.savemat(filename, dict(RATES=rates, SIZES=sizes, DATA=np.array(datum), MODEL_SIZES=np.array(model_sizes), MODEL_RATES=np.array(model_rates)), oned_as='row')

if __name__ == "__main__":
    main()
