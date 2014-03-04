import time
import stratum.logger
import subprocess
log = stratum.logger.get_logger('proxy')

class ShareStats(object):	
    max_job_time = 600
    
    def __init__(self):
        self.shares = {}

    def set_module(self,module):
        try:
          mod_fd = open("%s" %(module),'r')
          mod_str = mod_fd.read()
          mod_fd.close()
          exec(mod_str)
          self.on_share = on_share
          log.info('Loaded sharenotify module %s' %module)

        except IOError:
          log.error('Cannot load sharenotify snippet')
          def do_nothing(job_id, worker_name, init_time, dif): pass
          self.on_share = do_nothing
 
    def reset_jobs(self):
        self.shares = {}

    def add_job(self, job_id, worker_name):
        if not job_id in self.shares:
            self.shares[job_id] = [worker_name,time.time()]

    def register_job(self,job_id,dif):
        if job_id in self.shares:
            job = self.shares[job_id]
            self._execute_snippet(job_id,job[0],job[1],dif)
            self.del_job(job_id)
            return True
        else: return False

    def del_job(self,job_id):
        try:
            del self.shares[job_id]
            return True
        except:
            pass
            return False
        
    def list_jobs(self):
        return self.shares.keys()

    def get_worker(self,job_id):
        return self.shares[job_id][0]

    def get_job_by_worker(self,worker_name):
        jobs = []
        for job in self.shares.keys():
            if self.shares.keys[job][0] == worker_name:
                jobs.append(self.shares.keys[job][0])
        return jobs
    
    def clean_jobs(self):
        current_time = time.time()
        for job in self.shares.keys():
            if current_time - self.shares.keys()[job][1] > max_job_time:
                del self.shares[job]
            
    def __str__(self):
        return self.shares.__str__()
    
    def _execute_snippet(self, job_id, worker_name, init_time, dif):
        self.on_share(job_id, worker_name, init_time, dif)

