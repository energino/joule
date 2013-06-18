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
The Joule Daemon. At least two daemons should be configured on a network. 
Daemons are controller by Joule Profiler which can trigger different traffic 
generation patterns. At the moment only UDP CBR flows are supported. Daemons
can be started using CLI options (not recommended) or by passing a Joule 
descriptor file generated with the joule-template command and by specifying
the probe id.
"""

import os
import json
import optparse
import logging 
import threading
import subprocess

CLICK_SENDER = "src :: RatedSource(ACTIVE false) -> counter_client :: Counter() -> tr_client :: TimeRange() -> Socket(UDP, %s, %u); ControlSocket(TCP, %u);"
CLICK_RECEIVER = "Socket(UDP, 0.0.0.0, %u) -> counter_server :: Counter()-> tr_server :: TimeRange() -> Discard(); ControlSocket(TCP, %u);" 
DEFAULT_RECEIVER_IP = "172.16.0.172"
DEFAULT_RECEIVER_PORT = 9998
DEFAULT_SENDER_PORT = 9999
DEFAULT_CONTROL = 7777

LOG_FORMAT = '%(asctime)-15s %(message)s'

class ClickDaemon(threading.Thread):
    def __init__(self, script, mode):
        super(ClickDaemon, self).__init__()
        logging.debug(script)
        self.script = "/usr/local/bin/click -e \"%s\"" % script
        self.mode = mode
    def run(self):
        logging.info("starting click process (%s)" % self.mode)
        p = subprocess.Popen(self.script, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        for line in iter(p.stdout.readline, ""):
            logging.debug(line.replace("\n", ""))
        retval = p.wait()
        logging.info("click %s process terminated with code %u" % (self.mode, retval))

def main():

    p = optparse.OptionParser()

    p.add_option('--receiver_ip', '-d', dest="receiver", default=DEFAULT_RECEIVER_IP)
    p.add_option('--receiver_port', '-r', dest="rport", default=DEFAULT_RECEIVER_PORT)
    p.add_option('--sender_port', '-s', dest="sport", default=DEFAULT_SENDER_PORT)
    p.add_option('--control', '-c', dest="control", default=DEFAULT_CONTROL)
    p.add_option('--joule', '-j', dest="joule", default=None)
    p.add_option('--probe', '-p', dest="probe", default=None)
    p.add_option('--verbose', '-v', action="store_true", dest="verbose", default=False)    
    p.add_option('--log', '-l', dest="log")
    options, _ = p.parse_args()
   
    if options.verbose:
        logging.basicConfig(level=logging.DEBUG, format=LOG_FORMAT, filename=options.log, filemode='w')
    else:
        logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, filename=options.log, filemode='w')

    logging.info("starting eJOULE daemon")

    if options.joule != None and options.probe != None:
        
        logging.info("using probe profile %s" % options.probe)
    
        with open(os.path.expanduser(options.joule)) as data_file:    
            joule = json.load(data_file)

        receiver = joule['probes'][options.probe]['receiver']
        sport = joule['probes'][options.probe]['sender_port']
        rport = joule['probes'][options.probe]['receiver_port']
        scontrol = joule['probes'][options.probe]['sender_control']
        rcontrol = joule['probes'][options.probe]['receiver_control']

    else:

        receiver = options.receiver
        rport = int(options.rport)
        sport = int(options.sport)
        rcontrol = int(options.control)
        scontrol = int(options.control) + 1

    logging.info("receiver ip address: %s" % receiver)
    logging.info("receiver port: %s" % rport)
    logging.info("sender port: %s" % sport)
    logging.info("receiver control port: %u" % rcontrol)
    logging.info("sender control port: %u" % scontrol)

    server = ClickDaemon(CLICK_RECEIVER % (rport, rcontrol), "receiver")
    server.start()

    client = ClickDaemon(CLICK_SENDER % (receiver, sport, scontrol), "sender")
    client.start()
        
if __name__ == "__main__":
    main()
    