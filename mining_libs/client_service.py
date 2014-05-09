from twisted.internet import reactor

from stratum.event_handler import GenericEventHandler
from jobs import Job
import utils
import version as _version

import stratum_listener

import stratum.logger
log = stratum.logger.get_logger('proxy')

class ClientMiningService(GenericEventHandler):
    job_registry = None # Reference to JobRegistry instance
    timeout = None # Reference to IReactorTime object
    cf_counter = 0
    cf_path = None
    cf_notif = 10
    controlled_disconnect = False
    new_custom_auth = False
    
    @classmethod
    def check_control_file(cls):
        # Contorl file syntax is: <pool:port> [user:pass]
        # Example: mypool.com:3333 user.1:foo
        if cls.cf_path != None and cls.cf_counter > cls.cf_notif:
            cls.cf_counter = 0
            log.info("Checking control file")
            try:
                with open(cls.cf_path,'r') as cf:
                    data = cf.read()
                    sdata = data.strip().split(' ')
                    host = sdata[0].split(':')[0]
                    port = int(sdata[0].split(':')[1])
                    if len(sdata) > 1:
                        cls.new_custom_auth = (sdata[1].split(':')[0],sdata[1].split(':')[1])
                new = list(cls.job_registry.f.main_host[::])
                log.info("Current pool is %s:%d" % tuple(new))
                if new[0] != host or new[1] != port:
                    new[0] = host
                    new[1] = port
                    log.info("Found new pool configuration on host control file, reconnecting to %s:%d" % tuple(new))
                    log.info("New custom authorization data found %s:%s" %cls.new_custom_auth)
                    cls.controlled_disconnect = True
                    cls.job_registry.f.reconnect(new[0], new[1], None)

            except:
                log.error("Cannot open or read control file %s, keeping current pool configuration" % cls.cf_path)
        elif cls.cf_path != None:
            cls.cf_counter += 1

    @classmethod
    def reset_timeout(cls):
        if cls.timeout != None:
            if not cls.timeout.called:
                cls.timeout.cancel()
            cls.timeout = None
        cls.check_control_file()
        cls.timeout = reactor.callLater(2*60, cls.on_timeout)

    @classmethod
    def on_timeout(cls):
        '''
            Try to reconnect to the pool after two minutes of no activity on the connection.
            It will also drop all Stratum connections to sub-miners
            to indicate connection issues.
        '''
        log.error("Connection to upstream pool timed out")
        cls.reset_timeout()
        cls.job_registry.f.reconnect()
                
    def handle_event(self, method, params, connection_ref):
        '''Handle RPC calls and notifications from the pool'''

        # Yay, we received something from the pool,
        # let's restart the timeout.
        self.reset_timeout()
        
        if method == 'mining.notify':
            '''Proxy just received information about new mining job'''
            
            (job_id, prevhash, coinb1, coinb2, merkle_branch, version, nbits, ntime, clean_jobs) = params[:9]
            #print len(str(params)), len(merkle_branch)
            
            '''
            log.debug("Received new job #%s" % job_id)
            log.debug("prevhash = %s" % prevhash)
            log.debug("version = %s" % version)
            log.debug("nbits = %s" % nbits)
            log.debug("ntime = %s" % ntime)
            log.debug("clean_jobs = %s" % clean_jobs)
            log.debug("coinb1 = %s" % coinb1)
            log.debug("coinb2 = %s" % coinb2)
            log.debug("merkle_branch = %s" % merkle_branch)
            '''
        
            # Broadcast to Stratum clients
            stratum_listener.MiningSubscription.on_template(
                            job_id, prevhash, coinb1, coinb2, merkle_branch, version, nbits, ntime, clean_jobs)
            
            # Broadcast to getwork clients
            job = Job.build_from_broadcast(job_id, prevhash, coinb1, coinb2, merkle_branch, version, nbits, ntime)
            log.info("New job %s for prevhash %s, clean_jobs=%s" % \
                 (job.job_id, utils.format_hash(job.prevhash), clean_jobs))

            self.job_registry.add_template(job, clean_jobs)
            
            
            
        elif method == 'mining.set_difficulty':
            difficulty = params[0]
            log.info("Setting new difficulty: %s" % difficulty)
            
            stratum_listener.DifficultySubscription.on_new_difficulty(difficulty)
            self.job_registry.set_difficulty(difficulty)
                    
        elif method == 'client.reconnect':
            try:
                (hostname, port, wait) = params[:3]
            except:
                log.error("Pool send client.reconnect, but params are not correct, skipping it...")
                hostname = False
                port = False
                wait = False
            new = list(self.job_registry.f.main_host[::])
            if hostname and len(hostname) > 6: new[0] = hostname
            if port and port > 2: new[1] = port
            log.info("Server asked us to reconnect to %s:%d" % tuple(new))
            self.job_registry.f.reconnect(new[0], new[1], wait)
        
        elif method == 'client.add_peers':
            '''New peers which can be used on connection failure'''
            return False
            '''
            peerlist = params[0] # TODO
            for peer in peerlist:
                self.job_registry.f.add_peer(peer)
            return True
            '''
        elif method == 'client.get_version':
            return "stratum-proxy/%s" % _version.VERSION

        elif method == 'client.show_message':
            
            # Displays message from the server to the terminal
            utils.show_message(params[0])
            return True
            
        elif method == 'mining.get_hashrate':
            return {} # TODO
        
        elif method == 'mining.get_temperature':
            return {} # TODO
        
        else:
            '''Pool just asked us for something which we don't support...'''
            log.error("Unhandled method %s with params %s" % (method, params))

