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

DEFAULT_JOULE = './joule.json'
DEFAULT_MODELS = './models.json'
LOG_FORMAT = '%(asctime)-15s %(message)s'

def main():
    """ Load descriptor file and compute models. """

    parser = optparse.OptionParser()

    parser.add_option('--joule', '-j',
                      dest="joule",
                      default=DEFAULT_JOULE)

    parser.add_option('--models', '-m',
                      dest="models",
                      default=DEFAULT_MODELS)

    parser.add_option('--verbose', '-v',
                      action="store_true",
                      dest="verbose",
                      default=False)

    parser.add_option('--log', '-l', dest="log")

    options, _ = parser.parse_args()

    with open(os.path.expanduser(options.joule)) as data_file:
        data = json.load(data_file)

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

    logging.info("starting eJOULE modeller")
    logging.info("importing data into db")

    lookup_table = {(data['models'][model]['src'],
                     data['models'][model]['dst']) :
                     model for model in data['models']}

    conn = sqlite3.connect(':memory:')
    cursor = conn.cursor()

    cursor.execute("""create table data (src, dst, bitrate_mbps, goodput_mbps,
                      packetsize_bytes, losses, median, mean)""")

    conn.commit()

    for stint in data['stints']:

        row = [stint['src'],
               stint['dst'],
               stint['bitrate_mbps'],
               stint['stats']['gp'] / 1000000,
               stint['packetsize_bytes'],
               stint['stats']['losses'],
               stint['stats']['median'],
               stint['stats']['mean']]

        cursor.execute("""insert into data values (?,?,?,?,?,?,?,?)""", row)
        conn.commit()

    logging.info("generating models")

    pairs = conn.cursor().execute("select src,dst from data group by src,dst")

    models = {'gamma' : data['idle']['stats']['median']}

    for pair in pairs:

        if pair in lookup_table:
            model = lookup_table[pair]
        else:
            model = '%s -> %s' % pair

        models[model] = {}
        models[model]['x_max'] = {}

        sql = """SELECT MAX(goodput_mbps), packetsize_bytes
                 FROM data where src = \"%s\" and dst = \"%s\"
                 GROUP BY packetsize_bytes""" % (pair)

        xmaxs = conn.cursor().execute(sql)

        for xmax in xmaxs:
            models[model]['x_max'][xmax[1]] = xmax[0]

        slopes = []

        sql = """SELECT packetsize_bytes
                 FROM DATA
                 WHERE src = \"%s\" AND dst = \"%s\"
                 GROUP BY packetsize_bytes
                 ORDER BY packetsize_bytes ASC""" % pair

        sizes = conn.cursor().execute(sql)

        models[model]['beta'] = {}

        for size in sizes:

            x_max = models[model]['x_max'][size[0]]

            sql = """SELECT bitrate_mbps, median
                     FROM DATA
                     WHERE bitrate_mbps < %f AND packetsize_bytes = %s AND src = \"%s\" AND dst = \"%s\"
                     ORDER BY bitrate_mbps""" % (tuple([x_max]) + size + pair)

            rates = conn.cursor().execute(sql).fetchall()

            slope = ((rates[len(rates) - 1][1] - rates[0][1]) /
                     (rates[len(rates) - 1][0] - rates[0][0]))

            slopes.append([size[0], slope])

        A = np.array(slopes)

        fitting_func = lambda x, a0, a1: a0 * (1 + a1 / x)

        popt, _ = curve_fit(fitting_func, A[:, 0], A[:, 1])

        models[model]['alpha0'] = popt[0]
        models[model]['alpha1'] = popt[1]

        if 'TX' in models:
            models['TX']['alpha0'] = 0.0065
            models['TX']['alpha1'] = 966.8018

        if 'RX' in models:
            models['RX']['alpha0'] = 0.002565092236542
            models['RX']['alpha1'] = 1749.155415849026

        sql = """SELECT packetsize_bytes
                 FROM DATA
                 WHERE src = \"%s\" AND dst = \"%s\"
                 GROUP BY packetsize_bytes
                 ORDER BY packetsize_bytes ASC""" % pair

        sizes = conn.cursor().execute(sql)

        models[model]['beta'] = {}

        for size in sizes:

            sql = """SELECT bitrate_mbps, packetsize_bytes, median
                     FROM DATA
                     WHERE packetsize_bytes = %s AND
                           src = \"%s\" AND dst = \"%s\"""" % (size + pair)

            rates = conn.cursor().execute(sql)

            beta = []

            for rate in rates:

                x_var = rate[0]
                d_var = rate[1]

                if x_var > models[model]['x_max'][d_var]:
                    x_var = models[model]['x_max'][d_var]

                beta.append(rate[2] -
                            (models[model]['alpha0'] *
                             (1 + models[model]['alpha1'] / d_var) *
                             x_var +
                             models['gamma']))

            models[model]['beta'][size[0]] = np.mean(beta)

    with open(os.path.expanduser(options.models), 'w') as data_file:
        json.dump(models,
                  data_file,
                  indent=4,
                  separators=(',', ': '),
                  sort_keys=True)

    logging.info("models saved to %s", os.path.expanduser(options.models))

if __name__ == "__main__":
    main()
