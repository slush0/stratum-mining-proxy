import json
from twisted.internet.protocol import DatagramProtocol

import stratum.logger
log = stratum.logger.get_logger('proxy')

class MulticastResponder(DatagramProtocol):
    def __init__(self, pool_host, stratum_port, getwork_port):
        # Upstream Stratum host/port
        # Used for identifying the pool which we're connected to.
        # Some load balancing strategies can change the host/port
        # during the mining session (by mining.reconnect()), but this points
        # to initial host/port provided by user on cmdline or by X-Stratum 
        self.pool_host = pool_host
        
        self.stratum_port = stratum_port
        self.getwork_port = getwork_port
        
    def startProtocol(self):        
        # 239.0.0.0/8 are for private use within an organization
        self.transport.joinGroup("239.3.3.3")
        self.transport.setTTL(5)

    def writeResponse(self, address, msg_id, result, error=None):
        self.transport.write(json.dumps({"id": msg_id, "result": result, "error": error}), address)
        
    def datagramReceived(self, datagram, address):
        log.info("Received local discovery request from %s:%d" % address)
        
        try:
            data = json.loads(datagram)
        except:
            # Skip response if datagram is not parsable
            log.error("Unparsable datagram")
            return
        
        msg_id = data.get('id')
        msg_method = data.get('method')
        #msg_params = data.get('params')
        
        if msg_method == 'mining.get_upstream':
            self.writeResponse(address, msg_id, (self.pool_host, self.stratum_port, self.getwork_port))