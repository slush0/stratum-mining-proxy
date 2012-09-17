from stratum.services import GenericService

class StratumProxyService(GenericService):
    service_type = 'mining'
    service_vendor = 'mining_proxy'
    is_default = True
    
    def authorize(self, worker_name, worker_password):
        return True
    
    def subscribe(self):
        pass
        #return Pubsub.subscribe(self.connection_ref(), MiningSubscription()) + (extranonce1_hex, extranonce2_size)
            
    def submit(self, worker_name, job_id, extranonce2, ntime, nonce):
        return True