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
Handle the communications with the click ControlSocket element. It supports
basic READ and WRITE handlers. It does NOT support multiple read/write
statements.
"""

import socket

def _handler(address, port, read_write, handler):
    """ Connect to the ControlSocket element and call 'handler'. """

    ctrl = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    ctrl.connect((address, port))
    ctrl.send("%s %s\nQUIT\n" % (read_write, handler))

    buf = ''

    while True:
        data = ctrl.recv(1024)
        if not data:
            break
        buf += data

    if not buf.startswith("Click::ControlSocket/1.3"):
        return None

    buf = buf[buf.find('\r\n')+2:]

    if buf[0:3] != "200":
        return [ buf[0:3], buf[4:buf.find('\r\n')], '' ]

    data = buf[buf.find('\r\n')+2:]

    if not data.startswith("DATA"):
        return [ buf[0:3], buf[4:buf.find('\r\n')], '' ]

    length = int(data[data.find(' ')+1:data.find('\r\n')])

    data = data[data.find('\r\n')+2:]

    return [ buf[0:3], buf[4:buf.find('\r\n')], data[0:length] ]

def read_handler(address, port, handler):
    """ Connect to the ControlSocket element and read 'handler'. """

    return _handler(address, port, 'READ', handler)

def write_handler(address, port, handler):
    """ Connect to the ControlSocket element and write 'handler'. """

    return _handler(address, port, 'WRITE', handler)
