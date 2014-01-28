import time
import stratum.logger
import subprocess

log = stratum.logger.get_logger('proxy')

class ShareStats(object):
    max_job_time = 600
    
    def __init__(self,register_cmd='echo [%t] %w %j/%d >> /tmp/sharestats.log'):
        self.shares = {}
        self.register_cmd = register_cmd
    
    def setCMD(self,cmd):
        self.register_cmd = cmd
    
    def resetJobs(self):
        self.shares = {}

    def addJob(self, job_id, worker_name):
        if not job_id in self.shares:
            self.shares[job_id] = [worker_name,time.time()]

    def registerJob(self,job_id,dif):
        if job_id in self.shares:
            job = self.shares[job_id]
            self._execute_cmd(job_id,job[0],job[1],dif)
            self.delJob(job_id)
            return True
        else: return False

    def delJob(self,job_id):
        try:
            del self.shares[job_id]
            return True
        except:
            pass
            return False
        
    def listJobs(self):
        return self.shares.keys()

    def getWorker(self,job_id):
        return self.shares[job_id][0]

    def getJobByWorker(self,worker_name):
        jobs = []
        for job in self.shares.keys():
            if self.shares.keys[job][0] == worker_name:
                jobs.append(self.shares.keys[job][0])
        return jobs
    
    def cleanJobs(self):
        current_time = time.time()
        for job in self.shares.keys():
            if current_time - self.shares.keys()[job][1] > max_job_time:
                del self.shares[job]
            
    def __str__(self):
        return self.shares.__str__()
    
    def _execute_cmd(self, job_id, worker_name, init_time,dif):
        if self.register_cmd:
            cmd = self.register_cmd.replace('%j', job_id)
            cmd = cmd.replace('%w', worker_name)
            cmd = cmd.replace('%t', str(init_time))
            cmd = cmd.replace('%d', str(dif))
            log.info("Executing sharenotify command: %s" %cmd)
            subprocess.Popen(cmd, shell=True)
        
        