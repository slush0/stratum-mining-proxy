#!/usr/bin/env python
'''
    This is just an example script for miner developers.
    If you're end user, you don't need to use this script.

    Detector of Stratum mining proxies on local network
    Copyright (C) 2012 Marek Palatinus <info@bitcoin.cz>
    
    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''

from twisted.internet.protocol import DatagramProtocol
from twisted.internet import reactor, defer

import json

class MulticastClient(DatagramProtocol):

    def startProtocol(self):
        self.transport.joinGroup("239.3.3.3")
        self.transport.write(json.dumps({"id": 0, "method": "mining.get_upstream", "params": []}), ('239.3.3.3', 3333))

    def datagramReceived(self, datagram, address):
        '''Some data from peers received.

           Example of valid datagram:
              {"id": 0, "result": [["api-stratum.bitcoin.cz", 3333], 3333, 8332], "error": null}

           First argument - (host, port) of upstream pool
           Second argument - Stratum port where proxy is listening
           Third parameter - Getwork port where proxy is listening
        '''
        #print "Datagram %s received from %s" % (datagram, address)

        try:
            data = json.loads(datagram)
        except:
            print "Unparsable datagram received"


        if data.get('id') != 0 or data.get('result') == None:
            return


        (proxy_host, proxy_port) = address
	(pool_host, pool_port) = data['result'][0]
        stratum_port = data['result'][1]
        getwork_port = data['result'][2]

        print "Found stratum proxy on %(proxy_host)s:%(stratum_port)d (stratum), "\
               "%(proxy_host)s:%(getwork_port)d (getwork), "\
               "mining for %(pool_host)s:%(pool_port)d" % \
              {'proxy_host': proxy_host,
               'pool_host': pool_host,
               'pool_port': pool_port,
               'stratum_port': stratum_port,
               'getwork_port': getwork_port}

def stop():
    print "Local discovery of Stratum proxies is finished."
    reactor.stop()

print "Listening for Stratum proxies on local network..."
reactor.listenMulticast(3333, MulticastClient(), listenMultiple=True)
reactor.callLater(5, stop)
reactor.run()
