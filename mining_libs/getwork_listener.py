import json
import time

from twisted.internet import defer
from twisted.web.resource import Resource
from twisted.web.server import NOT_DONE_YET

import stratum.logger
log = stratum.logger.get_logger('proxy')

class Root(Resource):
    isLeaf = True
    
    def __init__(self, job_registry, workers, stratum_host, stratum_port,
                 custom_stratum=None, custom_lp=None, custom_user=None, custom_password=''):
        Resource.__init__(self)
        self.job_registry = job_registry
        self.workers = workers
        self.stratum_host = stratum_host
        self.stratum_port = stratum_port
        self.custom_stratum = custom_stratum
        self.custom_lp = custom_lp
        self.custom_user = custom_user
        self.custom_password = custom_password
        
    def json_response(self, msg_id, result):
        resp = json.dumps({'id': msg_id, 'result': result, 'error': None})
        #print "RESPONSE", resp
        return resp
    
    def json_error(self, msg_id, code, message):
        resp = json.dumps({'id': msg_id, 'result': None, 'error': {'code': code, 'message': message}})
        #print "ERROR", resp
        return resp         
    
    def _on_submit(self, result, request, msg_id, blockheader, worker_name, start_time):
        response_time = (time.time() - start_time) * 1000
        if result == True:
            log.warning("[%dms] Share from '%s' accepted, diff %d" % (response_time, worker_name, self.job_registry.difficulty))
        else:
            log.warning("[%dms] Share from '%s' REJECTED" % (response_time, worker_name))
         
        try:   
            request.write(self.json_response(msg_id, result))
            request.finish()
        except RuntimeError:
            # RuntimeError is thrown by Request class when
            # client is disconnected already
            pass
        
    def _on_submit_failure(self, failure, request, msg_id, blockheader, worker_name, start_time):
        response_time = (time.time() - start_time) * 1000
        
        # Submit for some reason failed
        try:
            request.write(self.json_response(msg_id, False))
            request.finish()
        except RuntimeError:
            # RuntimeError is thrown by Request class when
            # client is disconnected already
            pass

        log.warning("[%dms] Share from '%s' REJECTED: %s" % \
                 (response_time, worker_name, failure.getErrorMessage()))
        
    def _on_authorized(self, is_authorized, request, worker_name):
        data = json.loads(request.content.read())
        
        if not is_authorized:
            request.write(self.json_error(data.get('id', 0), -1, "Bad worker credentials"))
            request.finish()
            return
                
        if not self.job_registry.last_job:
            log.warning('Getworkmaker is waiting for a job...')
            request.write(self.json_error(data.get('id', 0), -1, "Getworkmake is waiting for a job..."))
            request.finish()
            return

        if data['method'] == 'getwork':
            if 'params' not in data or not len(data['params']):
                                
                # getwork request
                log.info("Worker '%s' asks for new work" % worker_name)
                extensions = request.getHeader('x-mining-extensions')
                no_midstate =  extensions and 'midstate' in extensions
                request.write(self.json_response(data.get('id', 0), self.job_registry.getwork(no_midstate=no_midstate)))
                request.finish()
                return
            
            else:
                
                # submit
                d = defer.maybeDeferred(self.job_registry.submit, data['params'][0], worker_name)

                start_time = time.time()
                d.addCallback(self._on_submit, request, data.get('id', 0), data['params'][0][:160], worker_name, start_time)
                d.addErrback(self._on_submit_failure, request, data.get('id', 0), data['params'][0][:160], worker_name, start_time)
                return
            
        request.write(self.json_error(data.get('id'), -1, "Unsupported method '%s'" % data['method']))
        request.finish()
        
    def _on_failure(self, failure, request):
        request.write(self.json_error(0, -1, "Unexpected error during authorization"))
        request.finish()
        raise failure
        
    def _prepare_headers(self, request): 
        request.setHeader('content-type', 'application/json')
        
        if self.custom_stratum:
            request.setHeader('x-stratum', self.custom_stratum)    
        elif self.stratum_port:
            request.setHeader('x-stratum', 'stratum+tcp://%s:%d' % (request.getRequestHostname(), self.stratum_port))
        
        if self.custom_lp:
            request.setHeader('x-long-polling', self.custom_lp)
        else:
            request.setHeader('x-long-polling', '/lp')
            
        request.setHeader('x-roll-ntime', 1)
        
    def _on_lp_broadcast(self, _, request):        
        try:
            worker_name = request.getUser()
        except:
            worker_name = '<unknown>'
            
        log.info("LP broadcast for worker '%s'" % worker_name)
        extensions = request.getHeader('x-mining-extensions')
        no_midstate =  extensions and 'midstate' in extensions
        payload = self.json_response(0, self.job_registry.getwork(no_midstate=no_midstate))
        
        try:
            request.write(payload)
            request.finish()
        except RuntimeError:
            # RuntimeError is thrown by Request class when
            # client is disconnected already
            pass
        
    def render_POST(self, request):        
        self._prepare_headers(request)

        (worker_name, password) = (request.getUser(), request.getPassword())

        if self.custom_user:
            worker_name = self.custom_user
            password = self.custom_password
 
        if worker_name == '':
            log.warning("Authorization required")
            request.setResponseCode(401)
            request.setHeader('WWW-Authenticate', 'Basic realm="stratum-mining-proxy"')
            return "Authorization required"
        
        self._prepare_headers(request)
        
        if request.path.startswith('/lp'):
            log.info("Worker '%s' subscribed for LP" % worker_name)
            self.job_registry.on_block.addCallback(self._on_lp_broadcast, request)
            return NOT_DONE_YET
       
        d = defer.maybeDeferred(self.workers.authorize, worker_name, password)
        d.addCallback(self._on_authorized, request, worker_name)
        d.addErrback(self._on_failure, request)    
        return NOT_DONE_YET

    def render_GET(self, request):
        self._prepare_headers(request)
            
        try:
            worker_name = request.getUser()
        except:
            worker_name = '<unknown>'
                
        if self.custom_user:
            worker_name = self.custom_user
            password = self.custom_password                
                
        log.info("Worker '%s' subscribed for LP at %s" % (worker_name, request.path))
        self.job_registry.on_block.addCallback(self._on_lp_broadcast, request)
        return NOT_DONE_YET
