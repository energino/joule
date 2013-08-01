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
The Joule Modeller. The Modeller takes as input a Joule descriptor saved by
the Joule profiler and a JSON document defining the models to be generated 
and computes the parameters that produce the best fitting between empirical 
data and models.
"""

import os
import json
import optparse
import logging 
import sqlite3
import numpy as np
from scipy.optimize import curve_fit

LOG_FORMAT = '%(asctime)-15s %(message)s'
DEFAULT_JOULE = '~/joule.json'
DEFAULT_MODELS = '~/models.json'

LOOKUP = { ('A', 'B') : 'TX',
           ('B', 'A') : 'RX' }

def main():

    p = optparse.OptionParser()
    p.add_option('--joule', '-j', dest="joule", default=DEFAULT_JOULE)
    p.add_option('--models', '-m', dest="models", default=DEFAULT_MODELS)
    p.add_option('--verbose', '-v', action="store_true", dest="verbose", default=False)    
    p.add_option('--log', '-l', dest="log")
    options, _ = p.parse_args()

    with open(os.path.expanduser(options.joule)) as data_file:    
        data = json.load(data_file)

    if options.verbose:
        logging.basicConfig(level=logging.DEBUG, format=LOG_FORMAT, filename=options.log, filemode='w')
    else:
        logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, filename=options.log, filemode='w')

    logging.info("starting eJOULE modeller")
    logging.info("importing data into db")

    conn = sqlite3.connect(':memory:')
    c = conn.cursor()
    c.execute('''create table data (src, dst, bitrate_mbps, goodput_mbps, packetsize_bytes, losses, median, mean)''')
    conn.commit()

    for stint in data['stints']:
        row = [ stint['src'], stint['dst'], stint['bitrate_mbps'], stint['stats']['gp'] / 1000000, stint['packetsize_bytes'], stint['stats']['losses'], stint['stats']['median'], stint['stats']['mean']]
        c.execute("""insert into data values (?,?,?,?,?,?,?,?)""", row)
        conn.commit()

    logging.info("generating models")

    pairs = conn.cursor().execute("select src, dst from data group by src, dst")

    models = {}

    gamma = data['idle']['median']

    for pair in pairs:

        if pair in LOOKUP:
            model = LOOKUP[pair]
        else: 
            model = '%s -> %s' % pair
            
        models[model] = { 'gamma' : gamma }

        sql = """SELECT MAX(goodput_mbps), packetsize_bytes 
                 FROM data where src = \"%s\" and dst = \"%s\" 
                 GROUP BY packetsize_bytes""" % (pair)

        xmaxs = conn.cursor().execute(sql)
        
        slopes = []
        models[model]['x_max'] = []
        
        for xmax in xmaxs:
            
            models[model]['x_max'].append(xmax[0])
            
            sql = """SELECT (MAX(median) - MIN(median)) / (MAX(bitrate_mbps) - MIN(bitrate_mbps)), packetsize_bytes 
                     FROM data 
                     WHERE src = \"%s\" and dst = \"%s\" and bitrate_mbps < %f and packetsize_bytes = %f 
                     ORDER BY bitrate_mbps ASC""" % (pair+xmax)

            slopes.append(conn.cursor().execute(sql).fetchone())
            
        A = np.array(slopes)
        
        popt, _ = curve_fit(lambda x, a0, a1: a0 * (1 + a1 / x), A[:,1], A[:,0])

        models[model]['packet_sizes'] = [ int(x) for x in A[:,1] ]

        models[model]['alpha0'] = popt[0]
        models[model]['alpha1'] = popt[1]

        sql = """SELECT AVG(median) - %f, packetsize_bytes 
                 FROM data where src = \"%s\" and dst = \"%s\" 
                 GROUP BY packetsize_bytes 
                 ORDER BY packetsize_bytes ASC""" % ( tuple([models[model]['gamma']]) + pair )

        beta = conn.cursor().execute(sql)

        models[model]['beta'] = [ x[0] for x in beta ]

        print "alpha0: \t %f" % models[model]['alpha0']
        print "alpha1: \t %f" % models[model]['alpha1']
        print "gamma: \t\t %f" % gamma
        print "packet sizes: \t %s" % ' \t'.join([ str(int(x)) for x in A[:,1] ])
        print "beta(d): \t %s" % ' \t'.join( [ "%.3f" % x for x in models[model]['beta'] ])
        print "x_max(d): \t %s" % ' \t'.join( [ "%.3f" % x for x in models[model]['x_max'] ])

    with open(os.path.expanduser(options.models), 'w') as data_file:    
        json.dump(models, data_file, indent=4, separators=(',', ': '))

    logging.info("models saved to %s" % os.path.expanduser(options.models))

if __name__ == "__main__":
    main()
