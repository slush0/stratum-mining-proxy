#!/usr/bin/env python
'''
    Stratum mining proxy
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

from stratum import settings
settings.LOGLEVEL='INFO'

import argparse
from twisted.internet import reactor, defer
from stratum.socket_transport import SocketTransportFactory, SocketTransportClientFactory
from stratum.services import ServiceEventHandler
from twisted.web.server import Site

import stratum_listener
import getwork_listener
import client_service
import jobs
import worker_registry
import multicast_responder

import stratum.logger
log = stratum.logger.get_logger('proxy')

def on_shutdown(f):
    '''Clean environment properly'''
    log.info("Shutting down proxy...")
    f.is_reconnecting = False # Don't let stratum factory to reconnect again
    
@defer.inlineCallbacks
def on_connect(f, workers, job_registry):
    '''Callback when proxy get connected to the pool'''
    log.info("Connected to Stratum pool at %s:%d" % f.main_host)
    
    # Every worker have to re-autorize
    workers.clear_authorizations() 
    
    # Hook to on_connect again
    f.on_connect.addCallback(on_connect, workers, job_registry)
    
    # Subscribe for receiving jobs
    log.info("Subscribing for mining jobs")
    (_, extranonce1, extranonce2_size) = (yield f.rpc('mining.subscribe', []))
    job_registry.set_extranonce(extranonce1, extranonce2_size)
    
    defer.returnValue(f)
     
def on_disconnect(f, workers, job_registry):
    '''Callback when proxy get disconnected from the pool'''
    log.info("Disconnected from Stratum pool at %s:%d" % f.main_host)

    # Reject miners because we don't give a *job :-)
    workers.clear_authorizations() 
        
    f.on_disconnect.addCallback(on_disconnect, workers, job_registry)
    return f              


    
@defer.inlineCallbacks
def main(args):
    if args.port != 3333:
        '''User most likely provided host/port
        for getwork interface. Let's try to detect
        Stratum host/port of given getwork pool.'''
        
        try:
            new_host = (yield detect_stratum(args.host, args.port))
        except:
            log.info("Stratum host/port autodetection failed")
            new_host = None
            
        if new_host != None:
            args.host = new_host[0]
            args.port = new_host[1]

    log.info("Trying to connect to Stratum pool at %s:%d" % (args.host, args.port))        
            
    # Connect to Stratum pool
    f = SocketTransportClientFactory(args.host, args.port,
                debug=args.verbose,
                event_handler=client_service.ClientMiningService)
    
    job_registry = jobs.JobRegistry(f, cmd=args.blocknotify_cmd, no_midstate=args.no_midstate)
    client_service.ClientMiningService.job_registry = job_registry
    
    workers = worker_registry.WorkerRegistry(f)
    f.on_connect.addCallback(on_connect, workers, job_registry)
    f.on_disconnect.addCallback(on_disconnect, workers, job_registry)
    
    # Cleanup properly on shutdown
    reactor.addSystemEventTrigger('before', 'shutdown', on_shutdown, f)

    # Block until proxy connect to the pool
    yield f.on_connect
    
    # Setup getwork listener    
    reactor.listenTCP(args.getwork_port, Site(getwork_listener.Root(job_registry, workers, stratum_port=args.port)),
                      interface=args.getwork_host)
    
    # Setup stratum listener
    #stratum_handler = StratumEventHandler(registry)
    reactor.listenTCP(args.stratum_port, SocketTransportFactory(debug=False, event_handler=ServiceEventHandler))

    # Setup multicast responder
    reactor.listenMulticast(3333, multicast_responder.MulticastResponder((args.host, args.port), args.stratum_port, args.getwork_port), listenMultiple=True)
        
    log.info("------------------------------------------------")
    if args.getwork_host == '0.0.0.0':
        log.info("PROXY IS LISTENING ON ALL IPs ON PORT %d (stratum) AND %d (getwork)" % (args.stratum_port, args.getwork_port))
    else:
        log.info("LISTENING FOR MINERS ON http://%s:%s" % (args.getwork_host, args.getwork_port))
    log.info("------------------------------------------------")

def parse_args():
    parser = argparse.ArgumentParser(description='This proxy allows you to run getwork-based miners against Stratum mining pool.')
    parser.add_argument('-o', '--host', dest='host', type=str, default='api-stratum.bitcoin.cz', help='Hostname of Stratum mining pool')
    parser.add_argument('-p', '--port', dest='port', type=int, default=3333, help='Port of Stratum mining pool')
    parser.add_argument('-sh', '--stratum-host', dest='stratum_host', type=str, default='0.0.0.0', help='On which network interface listen for stratum miners. Use "localhost" for listening on internal IP only.')
    parser.add_argument('-sp', '--stratum-port', dest='stratum_port', type=int, default=3333, help='Port on which port listen for stratum miners.')
    parser.add_argument('-oh', '--getwork-host', dest='getwork_host', type=str, default='0.0.0.0', help='On which network interface listen for getwork miners. Use "localhost" for listening on internal IP only.')
    parser.add_argument('-gp', '--getwork-port', dest='getwork_port', type=int, default=8332, help='Port on which port listen for getwork miners. Use another port if you have bitcoind RPC running on this machine already.')
    parser.add_argument('-nm', '--no-midstate', dest='no_midstate', action='store_true', help="Don't compute midstate for getwork. This has outstanding performance boost, but some old miners like Diablo don't work without midstate. ")
    parser.add_argument('--blocknotify', dest='blocknotify_cmd', type=str, default='', help='Execute command when the best block changes (%%s in BLOCKNOTIFY_CMD is replaced by block hash)')
    parser.add_argument('-v', '--verbose', dest='verbose', action='store_true', help='Enable low-level debugging messages')
    return parser.parse_args()

if __name__ == '__main__':
    args = parse_args()
    main(args)
    reactor.run()
