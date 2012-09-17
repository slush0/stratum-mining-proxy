from stratum.event_handler import GenericEventHandler
from jobs import Job
import utils

import stratum.logger
log = stratum.logger.get_logger('proxy')

class ClientMiningService(GenericEventHandler):
    job_registry = None # Reference to JobRegistry instance
    
    def handle_event(self, method, params, connection_ref):
        '''Handle RPC calls and notifications from the pool'''

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
            
            job = Job.build_from_broadcast(job_id, prevhash, coinb1, coinb2, merkle_branch, version, nbits, ntime)
            self.job_registry.add_template(job, clean_jobs)
            
        elif method == 'mining.set_difficulty':
            difficulty = params[0]
            log.info("Setting new difficulty: %s" % difficulty)
            self.job_registry.set_difficulty(difficulty)
                    
        elif method == 'client.reconnect':
            (hostname, port) = params[:2]
            log.info("Server asked us to reconnect to %s:%d" % (hostname, port))
            self.job_registry.f.reconnect(hostname, port)
            
        elif method == 'client.add_peers':
            '''New peers which can be used on connection failure'''
            peerlist = params[0] # TODO
            return False
        
        elif method == 'client.get_version':
            return "stratum-proxy/0.5"

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

