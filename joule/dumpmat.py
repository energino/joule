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
Joule Dump Mat The dumpmat command saves the content of the Joule descriptor
and the Joule model file in Matlab format. The Matfile
"""

import os
import json
import optparse
import sqlite3
import numpy as np
import scipy.io

DEFAULT_OUTPUT_DIR = './'

DEFAULT_JOULE = './joule.json'

def main():
    """ Dump Joule file descriptor as mat. """

    parser = optparse.OptionParser()

    parser.add_option('--joule', '-j',
                      dest="joule",
                      default=DEFAULT_JOULE)

    parser.add_option('--output', '-o',
                      dest="output",
                      default=DEFAULT_OUTPUT_DIR)

    options, _ = parser.parse_args()

    # load joule descriptor
    with open(os.path.expanduser(options.joule)) as data_file:
        data = json.load(data_file)

    lookup_table = {(data['models'][model]['src'],
                     data['models'][model]['dst']) :
                     model for model in data['models']}

    conn = sqlite3.connect(':memory:')
    cursor = conn.cursor()
    cursor.execute("""create table data (src, dst, bitrate_mbps, goodput_mbps,
                      packetsize_bytes, losses, median, mean, ci)""")
    conn.commit()

    for stint in data['stints']:

        row = [stint['src'],
               stint['dst'],
               stint['bitrate_mbps'],
               stint['stats']['gp'] / 1000000,
               stint['packetsize_bytes'],
               stint['stats']['losses'],
               stint['stats']['median'],
               stint['stats']['mean'],
               stint['stats']['ci']]

        cursor.execute("insert into data values (?,?,?,?,?,?,?,?,?)", row)
        conn.commit()

    pairs = []
    cursor.execute("select src, dst from data group by src, dst")
    for row in cursor:
        pairs.append(row)

    for pair in pairs:

        if pair in lookup_table:
            model = lookup_table[pair]
        else:
            model = '%s_%s' % pair

        cursor.execute("""select bitrate_mbps, goodput_mbps, packetsize_bytes,
                                 losses, median, mean, ci
                          from data
                          where src = \"%s\" and dst = \"%s\" """ %
                       tuple(pair))

        stints = [x for x in cursor]

        joule_expand_user = os.path.expanduser(options.joule)
        joule_basename = os.path.basename(joule_expand_user)

        basename = os.path.splitext(joule_basename)[0]

        filename = os.path.expanduser(options.output +
                                      '/' +
                                      basename + '_%s.mat' % model)

        scipy.io.savemat(filename, {'DATA':np.array(stints),
                                    'IDLE':data['idle']['stats']['median']},
                         oned_as='column')

if __name__ == "__main__":
    main()
