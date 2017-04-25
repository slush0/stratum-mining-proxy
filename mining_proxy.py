#!/usr/bin/env python
'''
    Stratum mining proxy
    Copyright (C) 2012 Marek Palatinus <slush@satoshilabs.com>
    
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

import argparse
import time
import os
import socket

def parse_args():
    parser = argparse.ArgumentParser(description='This proxy allows you to run getwork-based miners against Stratum mining pool.')
    parser.add_argument('-o', '--host', dest='host', type=str, default='stratum.bitcoin.cz', help='Hostname of Stratum mining pool')
    parser.add_argument('-p', '--port', dest='port', type=int, default=3333, help='Port of Stratum mining pool')
    parser.add_argument('-sh', '--stratum-host', dest='stratum_host', type=str, default='0.0.0.0', help='On which network interface listen for stratum miners. Use "localhost" for listening on internal IP only.')
    parser.add_argument('-sp', '--stratum-port', dest='stratum_port', type=int, default=3333, help='Port on which port listen for stratum miners.')
    parser.add_argument('-oh', '--getwork-host', dest='getwork_host', type=str, default='0.0.0.0', help='On which network interface listen for getwork miners. Use "localhost" for listening on internal IP only.')
    parser.add_argument('-gp', '--getwork-port', dest='getwork_port', type=int, default=8332, help='Port on which port listen for getwork miners. Use another port if you have bitcoind RPC running on this machine already.')
    parser.add_argument('-nm', '--no-midstate', dest='no_midstate', action='store_true', help="Don't compute midstate for getwork. This has outstanding performance boost, but some old miners like Diablo don't work without midstate.")
    parser.add_argument('-b', '--backup', dest='backup_pool', type=str, default=False, help='Stratum mining pool used as backup in format host:port.')
    parser.add_argument('-rt', '--real-target', dest='real_target', action='store_true', help="Propagate >diff1 target to getwork miners. Some miners work incorrectly with higher difficulty.")
    parser.add_argument('-cl', '--custom-lp', dest='custom_lp', type=str, help='Override URL provided in X-Long-Polling header')
    parser.add_argument('-cs', '--custom-stratum', dest='custom_stratum', type=str, help='Override URL provided in X-Stratum header')
    parser.add_argument('-cu', '--custom-user', dest='custom_user', type=str, help='Use this username for submitting shares')
    parser.add_argument('-cp', '--custom-password', dest='custom_password', type=str, help='Use this password for submitting shares')
    parser.add_argument('--set-extranonce', dest='set_extranonce', action='store_true', help='Enable set extranonce method from stratum pool')
    parser.add_argument('-cf', '--control-file', dest='cf_path', type=str, default=None, help='Control file path. If set proxy will check periodically for the contents of this file, if a new destination pool is specified in format pool:port, proxy will switch to this new pool.')
    parser.add_argument('--cf-interval', dest='cf_notif', type=int, default=10, help='Control file check interval (in pool notifications number). Low one implies more filesystem I/O and delays.')
    parser.add_argument('--idle', dest='set_idle', action='store_true', help='Close listening stratum ports in case connection with pool is lost (recover it later if success)')
    parser.add_argument('--old-target', dest='old_target', action='store_true', help='Provides backward compatible targets for some deprecated getwork miners.')    
    parser.add_argument('--blocknotify', dest='blocknotify_cmd', type=str, default='', help='Execute command when the best block changes (%%s in BLOCKNOTIFY_CMD is replaced by block hash)')
    parser.add_argument('--sharenotify', dest='sharestats_module', type=str, default=None, help='Execute a python snippet when a share is accepted. Use absolute path (i.e /root/snippets/log.py)')
    parser.add_argument('--socks', dest='proxy', type=str, default='', help='Use socks5 proxy for upstream Stratum connection, specify as host:port')
    parser.add_argument('-t', '--test', dest='test', action='store_true', help='Run performance test on startup')    
    parser.add_argument('-v', '--verbose', dest='verbose', action='store_true', help='Enable low-level debugging messages')
    parser.add_argument('-q', '--quiet', dest='quiet', action='store_true', help='Make output more quiet')
    parser.add_argument('-i', '--pid-file', dest='pid_file', type=str, help='Store process pid to the file')
    parser.add_argument('-l', '--log-file', dest='log_file', type=str, help='Log to specified file')
    parser.add_argument('-st', '--scrypt-target', dest='scrypt_target', action='store_true', help='Calculate targets for scrypt algorithm')
    return parser.parse_args()

from stratum import settings
settings.LOGLEVEL='INFO'

if __name__ == '__main__':
    # We need to parse args & setup Stratum environment
    # before any other imports
    global IDLE, backup_pool, original_pool
    args = parse_args()
    if args.quiet:
        settings.DEBUG = False
        settings.LOGLEVEL = 'WARNING'
    elif args.verbose:
        settings.DEBUG = True
        settings.LOGLEVEL = 'DEBUG'
    if args.log_file:
        settings.LOGFILE = args.log_file
    if args.set_idle:
        IDLE=False

    backup_pool = args.backup_pool
    original_pool = "%s:%s" %(args.host,args.port)
    IDLE=None
    
from twisted.internet import reactor, defer
from stratum.socket_transport import SocketTransportFactory, SocketTransportClientFactory
from stratum.services import ServiceEventHandler
from twisted.web.server import Site

from mining_libs import stratum_listener
from mining_libs import getwork_listener
from mining_libs import client_service
from mining_libs import jobs
from mining_libs import worker_registry
from mining_libs import multicast_responder
from mining_libs import version
from mining_libs import utils

import stratum.logger
log = stratum.logger.get_logger('proxy')

def on_shutdown(f):
    '''Clean environment properly'''
    log.info("Shutting down proxy...")
    f.is_reconnecting = False # Don't let stratum factory to reconnect again
    
@defer.inlineCallbacks
def on_connect(f, workers, job_registry):
    '''Callback when proxy get connected to the pool'''
    global IDLE
    log.info("Connected to Stratum pool at %s:%d" % f.main_host)
    #reactor.callLater(30, f.client.transport.loseConnection)
    if IDLE != None and IDLE:
        log.info("Found proxy in IDLE state, opening stratum server")
        IDLE=False
        reactor_listen.startListening()

    # Hook to on_connect again
    f.on_connect.addCallback(on_connect, workers, job_registry)
    
    # Every worker have to re-autorize
    workers.clear_authorizations() 

    # Subscribe for receiving jobs
    log.info("Subscribing for mining jobs")
    (_, extranonce1, extranonce2_size) = (yield f.rpc('mining.subscribe', []))[:3]

    if args.set_extranonce:
        log.info("Enable extranonce subscription method")
        f.rpc('mining.extranonce.subscribe', [])

    job_registry.set_extranonce(extranonce1, extranonce2_size)
    stratum_listener.StratumProxyService._set_extranonce(extranonce1, extranonce2_size)
    
    if args.custom_user:
        if f.event_handler.new_custom_auth:
            user,password = f.event_handler.new_custom_auth
        else:
            user = args.custom_user
            password = args.custom_password
        log.warning("Authorizing custom user %s, password %s" % (user, password))
        workers.authorize(user, password)
        stratum_listener.StratumProxyService._set_custom_user(user, password)

    # Set controlled disconnect to False
    f.event_handler.controlled_disconnect = False

    defer.returnValue(f)

def on_disconnect(f, workers, job_registry):
    '''Callback when proxy get disconnected from the pool'''
    global IDLE, backup_pool, original_pool
    f.on_disconnect.addCallback(on_disconnect, workers, job_registry)

    if not f.event_handler.controlled_disconnect:
        log.info("Disconnected from Stratum pool at %s:%d" % f.main_host)
        stratum_listener.MiningSubscription.disconnect_all()
        # Reject miners because we don't give a *job :-)
        workers.clear_authorizations()
    
    if not f.event_handler.controlled_disconnect and IDLE != None:
        log.info("Entering in IDLE state")
        reactor_listen.stopListening()
        IDLE=True

    if (not f.event_handler.controlled_disconnect) and backup_pool:
        host = backup_pool.split(':')[0]
        port = int(backup_pool.split(':')[1])
        log.info("Backup pool configured, trying to stablish connection with %s" %backup_pool)
        stratum_listener.MiningSubscription.reconnect_all()
        f.reconnect(host=host,port=port)
        workers.clear_authorizations()
        log.info("Sending reconnect order to workers")
        aux_pool = backup_pool
        backup_pool = original_pool
        original_pool = aux_pool
        f.event_handler.is_backup_active = not f.event_handler.is_backup_active

    if f.event_handler.controlled_disconnect:
        log.info("Sending reconnect order to workers")
        stratum_listener.MiningSubscription.reconnect_all()
        workers.clear_authorizations()

    return f

def test_launcher(result, job_registry):
    def run_test():
        log.info("Running performance self-test...")
        for m in (True, False):
            log.info("Generating with midstate: %s" % m)
            log.info("Example getwork:")
            log.info(job_registry.getwork(no_midstate=not m))

            start = time.time()
            n = 10000
            
            for x in range(n):
                job_registry.getwork(no_midstate=not m)
                
            log.info("%d getworks generated in %.03f sec, %d gw/s" % \
                     (n, time.time() - start, n / (time.time()-start)))
            
        log.info("Test done")
    reactor.callLater(1, run_test)
    return result

def print_deprecation_warning():
    '''Once new version is detected, this method prints deprecation warning every 30 seconds.'''

    log.warning("New proxy version available! Please update!")
    reactor.callLater(30, print_deprecation_warning)

def test_update():
    '''Perform lookup for newer proxy version, on startup and then once a day.
    When new version is found, it starts printing warning message and turned off next checks.'''
 
    GIT_URL='https://raw.github.com/slush0/stratum-mining-proxy/master/mining_libs/version.py'

    import urllib2
    log.warning("Checking for updates...")
    try:
        if version.VERSION not in urllib2.urlopen(GIT_URL).read():
            print_deprecation_warning()
            return # New version already detected, stop periodic checks
    except:
        log.warning("Check failed.")
        
    reactor.callLater(3600*24, test_update)

@defer.inlineCallbacks
def main(args):
    global reactor_listen
    if args.pid_file:
        fp = file(args.pid_file, 'w')
        fp.write(str(os.getpid()))
        fp.close()
    
    if args.port != 3333:
        '''User most likely provided host/port
        for getwork interface. Let's try to detect
        Stratum host/port of given getwork pool.'''
        
        try:
            new_host = (yield utils.detect_stratum(args.host, args.port))
        except:
            log.exception("Stratum host/port autodetection failed")
            new_host = None
            
        if new_host != None:
            args.host = new_host[0]
            args.port = new_host[1]

    log.warning("Stratum proxy version: %s" % version.VERSION)
    
    if args.proxy:
        proxy = args.proxy.split(':')
        if len(proxy) < 2:
            proxy = (proxy, 9050)
        else:
            proxy = (proxy[0], int(proxy[1]))
        log.warning("Using proxy %s:%d" % proxy)
    else:
        proxy = None

    log.warning("Trying to connect to Stratum pool at %s:%d" % (args.host, args.port))        
        
    # Connect to Stratum pool
    f = SocketTransportClientFactory(args.host, args.port,
                debug=args.verbose, proxy=proxy,
                event_handler=client_service.ClientMiningService)
    
    
    job_registry = jobs.JobRegistry(f, cmd=args.blocknotify_cmd, scrypt_target=args.scrypt_target,
                   no_midstate=args.no_midstate, real_target=args.real_target, use_old_target=args.old_target)
    client_service.ClientMiningService.job_registry = job_registry
    client_service.ClientMiningService.reset_timeout()
    if args.cf_path != None:
        log.info("Using pool control file %s" %args.cf_path)
    client_service.ClientMiningService.cf_path = args.cf_path
    client_service.ClientMiningService.cf_notif = args.cf_notif

    if args.custom_user != None:
        client_service.ClientMiningService.new_custom_auth = (args.custom_user, args.custom_password)

    workers = worker_registry.WorkerRegistry(f)
    f.on_connect.addCallback(on_connect, workers, job_registry)
    f.on_disconnect.addCallback(on_disconnect, workers, job_registry)


    if args.test:
        f.on_connect.addCallback(test_launcher, job_registry)
    
    # Cleanup properly on shutdown
    reactor.addSystemEventTrigger('before', 'shutdown', on_shutdown, f)

    # Block until proxy connect to the pool
    yield f.on_connect
    
    # Setup getwork listener
    if args.getwork_port > 0:
        conn = reactor.listenTCP(args.getwork_port, Site(getwork_listener.Root(job_registry, workers,
                                                    stratum_host=args.stratum_host, stratum_port=args.stratum_port,
                                                    custom_lp=args.custom_lp, custom_stratum=args.custom_stratum,
                                                    custom_user=args.custom_user, custom_password=args.custom_password)),
                                                    interface=args.getwork_host)

        try:
            conn.socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1) # Enable keepalive packets
            conn.socket.setsockopt(socket.SOL_TCP, socket.TCP_KEEPIDLE, 60) # Seconds before sending keepalive probes
            conn.socket.setsockopt(socket.SOL_TCP, socket.TCP_KEEPINTVL, 1) # Interval in seconds between keepalive probes
            conn.socket.setsockopt(socket.SOL_TCP, socket.TCP_KEEPCNT, 5) # Failed keepalive probles before declaring other end dead
        except:
            pass # Some socket features are not available on all platforms (you can guess which one)
    
    # Setup stratum listener
    if args.stratum_port > 0:
        stratum_listener.StratumProxyService._set_upstream_factory(f)
        stratum_listener.StratumProxyService._set_custom_user(args.custom_user, args.custom_password)
        stratum_listener.StratumProxyService._set_sharestats_module(args.sharestats_module)
        reactor_listen = reactor.listenTCP(args.stratum_port, SocketTransportFactory(debug=False, event_handler=ServiceEventHandler), interface=args.stratum_host)

    # Setup multicast responder
    reactor.listenMulticast(3333, multicast_responder.MulticastResponder((args.host, args.port), args.stratum_port, args.getwork_port), listenMultiple=True)
    
    log.warning("-----------------------------------------------------------------------")
    if args.getwork_host == '0.0.0.0' and args.stratum_host == '0.0.0.0':
        log.warning("PROXY IS LISTENING ON ALL IPs ON PORT %d (stratum) AND %d (getwork)" % (args.stratum_port, args.getwork_port))
    else:
        log.warning("LISTENING FOR MINERS ON http://%s:%d (getwork) and stratum+tcp://%s:%d (stratum)" % \
                 (args.getwork_host, args.getwork_port, args.stratum_host, args.stratum_port))
    log.warning("-----------------------------------------------------------------------")

if __name__ == '__main__':
    main(args)
    reactor.run()
