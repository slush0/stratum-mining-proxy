import time

from stratum.services import GenericService
from stratum.pubsub import Pubsub, Subscription

import stratum.logger
log = stratum.logger.get_logger('proxy')

class MiningSubscription(Subscription):
    '''This subscription object implements
    logic for broadcasting new jobs to the clients.'''
    
    event = 'mining.notify'
    
    @classmethod
    def on_template(cls, is_new_block):
        '''This is called when proxy registers
           new block which we have to broadcast clients.'''
        
        '''
        start = time.time()
        
        clean_jobs = is_new_block
        (job_id, prevhash, coinb1, coinb2, merkle_branch, version, nbits, ntime, _) = \
                        Interfaces.template_registry.get_last_broadcast_args()
        
        # Push new job to subscribed clients
        cls.emit(job_id, prevhash, coinb1, coinb2, merkle_branch, version, nbits, ntime, clean_jobs)
        
        cnt = Pubsub.get_subscription_count(cls.event)
        log.info("BROADCASTED to %d connections in %.03f sec" % (cnt, (time.time() - start)))
        '''
        
    def _finish_after_subscribe(self, result):
        '''Send new job to newly subscribed client'''
        
        '''
        try:        
            (job_id, prevhash, coinb1, coinb2, merkle_branch, version, nbits, ntime, _) = \
                        Interfaces.template_registry.get_last_broadcast_args()
        except Exception:
            log.error("Template not ready yet")
            return result
        
        self.emit_single(job_id, prevhash, coinb1, coinb2, merkle_branch, version, nbits, ntime, True)
        
        return result
        '''
             
    def after_subscribe(self, *args):
        '''This will send new job to the client *after* he receive subscription details.
        on_finish callback solve the issue that job is broadcasted *during*
        the subscription request and client receive messages in wrong order.'''
        self.connection_ref().on_finish.addCallback(self._finish_after_subscribe)
        
class StratumProxyService(GenericService):
    service_type = 'mining'
    service_vendor = 'mining_proxy'
    is_default = True
    
    def authorize(self, worker_name, worker_password):
        return True
    
    def subscribe(self):
        '''
        return Pubsub.subscribe(self.connection_ref(), MiningSubscription()) + (extranonce1_hex, extranonce2_size)
        '''
            
    def submit(self, worker_name, job_id, extranonce2, ntime, nonce):
        return True