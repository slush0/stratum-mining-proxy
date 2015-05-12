import binascii
import time
import struct
import subprocess
import weakref

from twisted.internet import defer

import utils

import stratum.logger
log = stratum.logger.get_logger('proxy')

# This fix py2exe issue with packaging the midstate module
from midstate import calculateMidstate as __unusedimport

try:
    from midstatec import test as midstateTest, midstate as calculateMidstate
    if not midstateTest():
        log.warning("midstate library didn't passed self test!")
        raise ImportError("midstatec not usable")
    log.info("Using C extension for midstate speedup. Good!")
except ImportError:
    log.info("C extension for midstate not available. Using default implementation instead.")
    try:    
        from midstate import calculateMidstate
    except ImportError:
        calculateMidstate = None
        log.exception("No midstate generator available. Some old miners won't work properly.")

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
            merkle_root = utils.doublesha(merkle_root + h)
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
    def __init__(self, f, cmd, no_midstate, real_target, use_old_target=False, scrypt_target=False):
        self.f = f
        self.cmd = cmd # execute this command on new block
        self.scrypt_target = scrypt_target # calculate target for scrypt algorithm instead of sha256
        self.no_midstate = no_midstate # Indicates if calculate midstate for getwork
        self.real_target = real_target # Indicates if real stratum target will be propagated to miners
        self.use_old_target = use_old_target # Use 00000000fffffff...f instead of correct 00000000ffffffff...0 target for really old miners
        self.jobs = []        
        self.last_job = None
        self.extranonce1 = None
        self.extranonce1_bin = None
        self.extranonce2_size = None
        
        self.target = 0
        self.target_hex = ''
        self.difficulty = 1
        self.set_difficulty(1)
        self.target1_hex = self.target_hex
        
        # Relation between merkle and job
        self.merkle_to_job= weakref.WeakValueDictionary()
        
        # Hook for LP broadcasts
        self.on_block = defer.Deferred()

    def execute_cmd(self, prevhash):
        if self.cmd:
            return subprocess.Popen(self.cmd.replace('%s', prevhash), shell=True)

    def set_extranonce(self, extranonce1, extranonce2_size):
        self.extranonce2_size = extranonce2_size
        self.extranonce1_bin = binascii.unhexlify(extranonce1)
        
    def set_difficulty(self, new_difficulty):
        if self.scrypt_target:
            dif1 = 0x0000ffff00000000000000000000000000000000000000000000000000000000
        else:
            dif1 = 0x00000000ffff0000000000000000000000000000000000000000000000000000
        self.target = int(dif1 / new_difficulty)
        self.target_hex = binascii.hexlify(utils.uint256_to_str(self.target))
        self.difficulty = new_difficulty
        
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
                
        if clean_jobs:
            # Force miners to reload jobs
            on_block = self.on_block
            self.on_block = defer.Deferred()
            on_block.callback(True)
    
            # blocknotify-compatible call
            self.execute_cmd(template.prevhash)
          
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
        
    def getwork(self, no_midstate=True):
        '''Miner requests for new getwork'''
        
        job = self.last_job # Pick the latest job from pool

        # 1. Increase extranonce2
        extranonce2 = job.increase_extranonce2()
        
        # 2. Build final extranonce
        extranonce = self.build_full_extranonce(extranonce2)
        
        # 3. Put coinbase transaction together
        coinbase_bin = job.build_coinbase(extranonce)
        
        # 4. Calculate coinbase hash
        coinbase_hash = utils.doublesha(coinbase_bin)
        
        # 5. Calculate merkle root
        merkle_root = binascii.hexlify(utils.reverse_hash(job.build_merkle_root(coinbase_hash)))
                
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
                'hash1': hash1}
        
        if self.use_old_target:
            result['target'] = 'ffffffffffffffffffffffffffffffffffffffffffffffffffffffff00000000'
        elif self.real_target:
            result['target'] = self.target_hex
        else:
            result['target'] = self.target1_hex
    
        if calculateMidstate and not (no_midstate or self.no_midstate):
            # Midstate module not found or disabled
            result['midstate'] = binascii.hexlify(calculateMidstate(header_bin))
            
        return result            
        
    def submit(self, header, worker_name):            
        # Drop unused padding
        header = header[:160]

        # 1. Check if blockheader meets requested difficulty
        header_bin = binascii.unhexlify(header[:160])
        rev = ''.join([ header_bin[i*4:i*4+4][::-1] for i in range(0, 20) ])
        hash_bin = utils.doublesha(rev)
        block_hash = ''.join([ hash_bin[i*4:i*4+4][::-1] for i in range(0, 8) ])
        
        #log.info('!!! %s' % header[:160])
        log.info("Submitting %s" % utils.format_hash(binascii.hexlify(block_hash)))
        
        if utils.uint256_from_str(hash_bin) > self.target:
            log.debug("Share is below expected target")
            return True
        
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
