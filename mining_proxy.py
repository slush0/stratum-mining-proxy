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

import argparse
import time
import json
import base64
import weakref
import hashlib
import struct
import binascii

from twisted.internet import reactor
from twisted.internet import defer
from twisted.web.resource import Resource
from twisted.web.server import Site, NOT_DONE_YET

from stratum.socket_transport import SocketTransportClientFactory
from stratum.services import GenericService, ServiceEventHandler
from stratum.event_handler import GenericEventHandler
from stratum import settings

import stratum.logger
log = stratum.logger.get_logger('proxy')

try:
    from midstate import calculateMidstate
except ImportError:
    calculateMidstate = None
    log.warning("Midstate generator not found. Some old miners won't work properly.")

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
            
        else:
            '''Pool just asked us for something which we don't support...'''
            log.error("Unhandled method %s with params %s" % (method, params))

def uint256_from_str(s):
    r = 0L
    t = struct.unpack("<IIIIIIII", s[:32])
    for i in xrange(8):
        r += t[i] << (i * 32)
    return r

def uint256_to_str(u):
    rs = ""
    for i in xrange(8):
        rs += struct.pack("<I", u & 0xFFFFFFFFL)
        u >>= 32
    return rs  

def reverse_hash(h):
    if len(h) != 64:
        raise Exception('hash must have 64 hexa chars')    
    return ''.join([ h[56-i:64-i] for i in range(0, 64, 8) ])
        
def doublesha(b):
    return hashlib.sha256(hashlib.sha256(b).digest()).digest()

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

class Job(object):
    def __init__(self):
        self.job_id = None
        self.prevhash = ''
        self.coinb1_bin = ''
        self.coinb2_bin = ''
        self.merkle_branch = []
        self.version = 1
        self.nbits = 0
        self.ntime_delta = 0
        
        self.extranonce2 = 0
        self.merkle_to_extranonce2 = {} # Relation between merkle_hash and extranonce2

    @classmethod
    def build_from_broadcast(cls, job_id, prevhash, coinb1, coinb2, merkle_branch, version, nbits, ntime):
        '''Build job object from Stratum server broadcast'''
        job = Job()
        job.job_id = job_id
        job.prevhash = prevhash
        job.coinb1_bin = binascii.unhexlify(coinb1)
        job.coinb2_bin = binascii.unhexlify(coinb2)
        job.merkle_branch = [ binascii.unhexlify(tx) for tx in merkle_branch ]
        job.version = version
        job.nbits = nbits
        job.ntime_delta = int(ntime, 16) - int(time.time()) 
        return job

    def increase_extranonce2(self):
        self.extranonce2 += 1
        return self.extranonce2

    def build_coinbase(self, extranonce):
        return self.coinb1_bin + extranonce + self.coinb2_bin
    
    def build_merkle_root(self, coinbase_hash):
        merkle_root = coinbase_hash
        for h in self.merkle_branch:
            merkle_root = doublesha(merkle_root + h)
        return merkle_root
    
    def serialize_header(self, merkle_root, ntime, nonce):
        r =  self.version
        r += self.prevhash
        r += merkle_root
        r += binascii.hexlify(struct.pack(">I", ntime))
        r += self.nbits
        r += binascii.hexlify(struct.pack(">I", nonce))
        r += '000000800000000000000000000000000000000000000000000000000000000000000000000000000000000080020000' # padding    
        return r            
        
class JobRegistry(object):   
    def __init__(self, f):
        self.f = f
        self.jobs = []        
        self.last_job = None
        self.extranonce1 = None
        self.extranonce1_bin = None
        self.extranonce2_size = None
        
        self.target = 0
        self.target_hex = ''
        self.set_difficulty(1)
        
        # Relation between merkle and job
        self.merkle_to_job= weakref.WeakValueDictionary()
        
        # Hook for LP broadcasts
        self.on_block = defer.Deferred()

    def set_extranonce(self, extranonce1, extranonce2_size):
        self.extranonce2_size = extranonce2_size
        self.extranonce1_bin = binascii.unhexlify(extranonce1)
        
    def set_difficulty(self, new_difficulty):
        dif1 = 0x00000000ffff0000000000000000000000000000000000000000000000000000 
        self.target = dif1 / new_difficulty
        self.target_hex = binascii.hexlify(uint256_to_str(self.target))
        
    def build_full_extranonce(self, extranonce2):
        '''Join extranonce1 and extranonce2 together while padding
        extranonce2 length to extranonce2_size (provided by server).'''        
        return self.extranonce1_bin + self.extranonce2_padding(extranonce2)

    def extranonce2_padding(self, extranonce2):
        '''Return extranonce2 with padding bytes'''

        if not self.extranonce2_size:
            raise Exception("Extranonce2_size isn't set yet")
        
        extranonce2_bin = struct.pack('>I', extranonce2)
        missing_len = self.extranonce2_size - len(extranonce2_bin)
        
        if missing_len < 0:
            # extranonce2 is too long, we should print warning on console,
            # but try to shorten extranonce2 
            log.info("Extranonce size mismatch. Please report this error to pool operator!")
            return extranonce2_bin[abs(missing_len):]

        # This is probably more common situation, but it is perfectly
        # safe to add whitespaces
        return '\x00' * missing_len + extranonce2_bin 
    
    def add_template(self, template, clean_jobs):
        if clean_jobs:
            # Pool asked us to stop submitting shares from previous jobs
            self.jobs = []
            
        self.jobs.append(template)
        self.last_job = template
        
        log.info("New job for prevhash %s" % template.prevhash) #''.join([ template.prevhash[56-i:64-i] for i in range(0, 64, 8) ]))
        
        if clean_jobs:
            # Force miners to reload jobs
            on_block = self.on_block
            self.on_block = defer.Deferred()
            on_block.callback(True)
          
    def register_merkle(self, job, merkle_hash, extranonce2):
        # merkle_to_job is weak-ref, so it is cleaned up automatically
        # when job is dropped
        self.merkle_to_job[merkle_hash] = job
        job.merkle_to_extranonce2[merkle_hash] = extranonce2
        
    def get_job_from_header(self, header):
        '''Lookup for job and extranonce2 used for given blockheader (in hex)'''
        merkle_hash = header[72:136].lower()
        job = self.merkle_to_job[merkle_hash]
        extranonce2 = job.merkle_to_extranonce2[merkle_hash]
        return (job, extranonce2)
    
    '''
    def add_job(self, job):
        ''Reference to self.jobs is weak, so after block template is dropped,
        relevant jobs are removed automatically. Circular reference between block
        template and job is ugly, but necessary.''
        
        self.jobs[job.parse_merkle_hash()] = job
        b = job.block()
        if b == None:
            return
        
        b.jobs.append(job)
    '''
        
    def getwork(self):
        '''Miner requests for new getwork'''
        
        job = self.last_job # Pick the latest job from pool

        # 1. Increase extranonce2
        extranonce2 = job.increase_extranonce2()
        
        # 2. Build final extranonce
        extranonce = self.build_full_extranonce(extranonce2)
        
        # 3. Put coinbase transaction together
        coinbase_bin = job.build_coinbase(extranonce)
        
        # 4. Calculate coinbase hash
        coinbase_hash = doublesha(coinbase_bin)
        
        # 5. Calculate merkle root
        merkle_root = reverse_hash("%064x" % uint256_from_str(job.build_merkle_root(coinbase_hash)))
        
        # 6. Generate current ntime
        ntime = int(time.time()) + job.ntime_delta
        
        # 7. Serialize header
        block_header = job.serialize_header(merkle_root, ntime, 0)

        # 8. Register job params
        self.register_merkle(job, merkle_root, extranonce2)
        
        # 9. Prepare hash1, calculate midstate and fill the response object
        header_bin = binascii.unhexlify(block_header)[:64]
        hash1 = "00000000000000000000000000000000000000000000000000000000000000000000008000000000000000000000000000000000000000000000000000010000"

        result = {'data': block_header,
                'hash1': hash1,
                'target': self.target_hex}
    
        if calculateMidstate:
            # Midstate module not found or disabled
            result['midstate'] = binascii.hexlify(calculateMidstate(header_bin))

        return result            

    def submit(self, header, worker_name):
        # Drop unused padding
        header = header[:160]

        # 1. Check if blockheader meets requested difficulty
        header_bin = binascii.unhexlify(header[:160])
        rev = ''.join([ header_bin[i*4:i*4+4][::-1] for i in range(0, 20) ])
        hash_bin = doublesha(rev)
        block_hash = ''.join([ hash_bin[i*4:i*4+4][::-1] for i in range(0, 8) ])
        
        #log.info('!!! %s' % header[:160])
        log.info("Submitting %s" % binascii.hexlify(block_hash))
        
        if uint256_from_str(hash_bin) > self.target:
            log.error("Share is below expected target")
            return False
        
        # 2. Lookup for job and extranonce used for creating given block header
        try:
            (job, extranonce2) = self.get_job_from_header(header)
        except KeyError:
            log.info("Job not found")
            return False

        # 3. Format extranonce2 to hex string
        extranonce2_hex = binascii.hexlify(self.extranonce2_padding(extranonce2))

        # 4. Parse ntime and nonce from header
        ntimepos = 17*8 # 17th integer in datastring
        noncepos = 19*8 # 19th integer in datastring       
        ntime = header[ntimepos:ntimepos+8] 
        nonce = header[noncepos:noncepos+8]
            
        # 5. Submit share to the pool
        return self.f.rpc('mining.submit', [worker_name, job.job_id, extranonce2_hex, ntime, nonce])

class WorkerRegistry(object):
    def __init__(self, f):
        self.f = f # Factory of Stratum client
        self.clear_authorizations()
        
    def clear_authorizations(self):
        self.authorized = []
        self.unauthorized = []
        self.last_check = time.time()
    
    def _on_authorized(self, result, worker_name):
        if result == True:
            self.authorized.append(worker_name)
        else:
            self.unauthorized.append(worker_name)
        return result
    
    def _on_failure(self, failure, worker_name):
        log.exception("Cannot authorize worker '%s'" % worker_name)
    
    def parse_basic_challenge(self, data):
        if not data:
            raise Exception("Basic challenge failed, no data")
        
        return base64.decodestring(data.split(' ')[1]).split(':')
                    
    def authorize(self, worker_name, password):
        if worker_name in self.authorized:
            return True
            
        if worker_name in self.unauthorized and time.time() - self.last_check < 60:
            # Prevent flooding of mining.authorize() requests 
            log.info("Authentication of worker '%s' with password '%s' failed, next attempt in few seconds..." % \
                    (worker_name, password))
            return False
        
        self.last_check = time.time()
        
        d = self.f.rpc('mining.authorize', [worker_name, password])
        d.addCallback(self._on_authorized, worker_name)
        d.addErrback(self._on_failure, worker_name)
        return d
         
    def is_authorized(self, worker_name):
        return (worker_name in self.authorized)
    
    def is_unauthorized(self, worker_name):
        return (worker_name in self.unauthorized)
    
class Root(Resource):
    isLeaf = True
    
    def __init__(self, job_registry, workers, stratum_host, stratum_port):
        Resource.__init__(self)
        self.job_registry = job_registry
        self.workers = workers
        self.stratum_host = stratum_host
        self.stratum_port = stratum_port
        
    def json_response(self, msg_id, result):
        resp = json.dumps({'id': msg_id, 'result': result, 'error': None})
        #print "RESPONSE", resp
        return resp
    
    def json_error(self, msg_id, code, message):
        resp = json.dumps({'id': msg_id, 'result': None, 'error': {'code': code, 'message': message}})
        #print "ERROR", resp
        return resp         
    
    def _on_submit(self, result, request, msg_id, worker_name):
        if result == True:
            log.info("Share from '%s' has been accepted by the pool" % worker_name)
        else:
            log.info("Share from '%s' has been REJECTED by the pool" % worker_name)
            
        request.write(self.json_response(msg_id, result))
        request.finish()
        
    def _on_submit_failure(self, failure, request, msg_id, worker_name):
        # Submit for some reason failed
        request.write(self.json_response(msg_id, False))
        request.finish()

        log.info("Share from '%s' has been REJECTED by the pool: %s" % (worker_name, failure.getErrorMessage()))
        
    def _on_authorized(self, is_authorized, request, worker_name):
        data = json.loads(request.content.read())
        
        if not is_authorized:
            request.write(self.json_error(data['id'], -1, "Bad worker credentials"))
            request.finish()
            return
                
        if not self.job_registry.last_job:
            log.info('Getworkmaker is waiting for a job...')
            request.write(self.json_error(data['id'], -1, "Getworkmake is waiting for a job..."))
            request.finish()
            return

        if data['method'] == 'getwork':
            if not len(data['params']):
                                
                # getwork request
                log.debug("Worker '%s' asks for new work" % worker_name)
                request.write(self.json_response(data['id'], self.job_registry.getwork()))
                request.finish()
                return
            
            else:
                
                # submit
                d = defer.maybeDeferred(self.job_registry.submit, data['params'][0], worker_name)
                d.addCallback(self._on_submit, request, data['id'], worker_name)
                d.addErrback(self._on_submit_failure, request, data['id'], worker_name)
                return
            
        request.write(self.json_error(data['id'], -1, "Unsupported method '%s'" % data['method']))
        request.finish()
        
    def _on_failure(self, failure, request):
        request.write(self.json_error(0, -1, "Unexpected error during authorization"))
        request.finish()
        raise failure
        
    def _on_lp_broadcast(self, _, request):
        if request._disconnected:
            # Miner disconnected before longpoll
            return
        
        try:
            (worker_name, _) = self.workers.parse_basic_challenge(request.getHeader('Authorization'))
        except:
            worker_name = '<unknown>'
            
        log.info("LP broadcast for worker '%s'" % worker_name)
        request.write(self.json_response(0, self.job_registry.getwork()))
        request.finish()
        
    def render_POST(self, request):
        request.setHeader('content-type', 'application/json')
        request.setHeader('x-stratum', 'stratum+tcp://%s:%d' % (self.stratum_host, self.stratum_port))
        request.setHeader('x-long-polling', '/lp')
        request.setHeader('x-roll-ntime', 1)
        
        (worker_name, password) = self.workers.parse_basic_challenge(request.getHeader('Authorization'))
        
        if request.path == '/lp':
            log.info("Worker '%s' subscribed for LP" % worker_name)
            self.job_registry.on_block.addCallback(self._on_lp_broadcast, request)
            return NOT_DONE_YET
                
        d = defer.maybeDeferred(self.workers.authorize, worker_name, password)
        d.addCallback(self._on_authorized, request, worker_name)
        d.addErrback(self._on_failure, request)
        return NOT_DONE_YET

    def render_GET(self, request):
        if request.path == '/lp':
            request.setHeader('content-type', 'application/json')
            request.setHeader('x-stratum', 'http://%s:%d' % (self.stratum_host, self.stratum_port))
            request.setHeader('x-long-polling', '/lp')
            request.setHeader('x-roll-ntime', 1)
            
            try:
                (worker_name, _) = self.workers.parse_basic_challenge(request.getHeader('Authorization'))
            except:
                worker_name = '<unknown>'
                
            log.info("Worker '%s' subscribed for LP" % worker_name)
            
            self.job_registry.on_block.addCallback(self._on_lp_broadcast, request)
            return NOT_DONE_YET
        
        return "This is Stratum mining proxy. It is used for providing work to getwork-compatible miners "\
            "from modern Stratum-based bitcoin mining pools."

@defer.inlineCallbacks
def main(args):
    log.info("Trying to connect to Stratum pool at %s:%d" % (args.host, args.port))    
    
    #if args.verbose:
    #    settings.LOGLEVEL = 'DEBUG'
    #else:
    #    settings.LOGLEVEL = 'INFO'
        
    # Connect to Stratum pool
    f = SocketTransportClientFactory(args.host, args.port,
                debug=args.verbose,
                event_handler=ClientMiningService)
    
    job_registry = JobRegistry(f)
    ClientMiningService.job_registry = job_registry
    
    workers = WorkerRegistry(f)
    f.on_connect.addCallback(on_connect, workers, job_registry)
    f.on_disconnect.addCallback(on_disconnect, workers, job_registry)
    
    # Cleanup properly on shutdown
    reactor.addSystemEventTrigger('before', 'shutdown', on_shutdown, f)

    # Block until proxy connect to the pool
    yield f.on_connect
        
    reactor.listenTCP(args.getwork_port, Site(Root(job_registry, workers, stratum_host=args.host, stratum_port=args.port)),
                      interface=args.getwork_host)
    log.info("------------------------------------------------")
    if args.getwork_host == '0.0.0.0':
        log.info("PROXY IS LISTENING ON ALL IPs ON PORT %d" % args.getwork_port)
    else:
        log.info("LISTENING FOR MINERS ON http://%s:%s" % (args.getwork_host, args.getwork_port))
    log.info("------------------------------------------------")
    # And now just sit down and wait for miners and new mining jobs

def parse_args():
    parser = argparse.ArgumentParser(description='This proxy allows you to run getwork-based miners against Stratum mining pool.')
    parser.add_argument('-o', '--host', dest='host', type=str, default='api-stratum.bitcoin.cz', help='Hostname of Stratum mining pool')
    parser.add_argument('-p', '--port', dest='port', type=int, default=3333, help='Port of Stratum mining pool')
    parser.add_argument('-oh', '--getwork-host', dest='getwork_host', type=str, default='0.0.0.0', help='On which network interface listen for getwork miners. Use "localhost" for listening on internal IP only.')
    parser.add_argument('-gp', '--getwork-port', dest='getwork_port', type=int, default=8332, help='Port on which port listen for getwork miners. Use another port if you have bitcoind RPC running on this machine already.')
    parser.add_argument('--blocknotify', dest='blocknotify_cmd', type=str, default='', help='Execute command when the best block changes (%s in cmd is replaced by block hash)')
    parser.add_argument('-v', '--verbose', dest='verbose', action='store_true', help='Enable low-level debugging messages')
    return parser.parse_args()

if __name__ == '__main__':
    args = parse_args()
    main(args)
    reactor.run()
