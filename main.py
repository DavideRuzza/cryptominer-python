import os
import sys
import threading
import socket
import urllib.parse
import json
import time
from binascii import hexlify, unhexlify
from hashlib import sha256
import random

class LogStyle():
    '''Increase terminal legibility'''
    
    # HELP: https://stackoverflow.com/questions/287871/how-to-print-colored-text-to-the-terminal
    NONE = ["[-]", '']
    LOG = ["[LOG]", "0;30;47"]
    WARNING = ["[WARNING]", "0;30;43"]
    ERROR = ["[ERROR]", "0;30;41"]
    OK = ["[OK]", "6;30;42"]
    

def debug(*messages):
    ''' for debug purpose only

        Even if called it doesn't print nothing if global variable DEBUG is set to False
    '''
    global DEBUG
    if DEBUG:
        for msg in messages:
            print("\x1b[0;34;1m"+f"{msg}"+"\x1b[0m")
    

def log(*messages, style=["[-]", ''], date=True):
    '''logging message with colored style

        style parameter should be set equal to some Variable of 'LogStyle' class
    '''
    log_str = style[0]
    log_style = style[1]
    print(f'\x1b[{log_style}m{log_str:^9}\x1b[0m', end='')
    
    if date:
        print('\x1b[1;30;1m - '+time.strftime("%d/%m/%y %H:%M:%S", time.gmtime())+" - \x1b[0m", end='') 
    
    log_space = f"\x1b[{log_style}m"+ " "*9 + "\x1b[0m"
    date_space = ' '*23 if date else ''
    
    print(("\n"+log_space+date_space).join([f"{msg}" for msg in messages]))


class JsonRcpClient(object):
    ''' Simple Json RCP client'''
    
    def __init__(self):
        self._socket = None
        self._rcp_thread = None
        self._message_id = 1
        self._lock = threading.RLock()
        self._requests = dict()
    
    def rcp_thread_fun(self):
        data = ""
        
        while True:
            
            if '\n' in data:
                (line, data) = data.split('\n', 1)
            else:
                chunk = self._socket.recv(1024)
                data += chunk.decode()
                continue
            
            reply = json.loads(line)
            # Find if the reply was a response from a specific request 
            # or a simple notification from the server (response = None)
            request = None
            if reply.get('id'):
                # get the reply id which refer to the corresponding response
                request = self._requests[reply.get('id')]  
            
            self._handle_reply(request, reply)
            
        
    def connect(self, url: str):
        """Create socket and start the receiving process

        Args:
            url (str): server of mining pool
        """
        
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        parser = urllib.parse.urlparse(url)
        
        try:
            self._socket.connect((parser.hostname, parser.port))

            self._rcp_thread = threading.Thread(target=self.rcp_thread_fun)
            self._rcp_thread.daemon = True  # only for testing it should be not commented 
            self._rcp_thread.start()
        except Exception:
            log("Can't connect to server", style=LogStyle.WARNING)
            sys.exit()

    
    def send(self, method: str, params: list):
        """Send request to server

        Args:
            method (str): request method (ie. 'mining.subcribe', 'mining.authorize', ...)
            params (list): list of params required with the corresponding request method 
        """
        if not self._socket:
            log("No socket defined. First you need to connect to a server", style=LogStyle.WARNING)
            sys.exit()
            
        request = dict(id=self._message_id, method=method, params=params)
        self._requests[self._message_id] = request

        request = json.dumps(request)

        # print(request)
        with self._lock:
            # update message id that refer to a specific request
            self._message_id += 1
            self._socket.send((request+'\n').encode())

    def _handle_reply(self, request, reply):
        ''' override this function '''
        raise NotImplementedError("Override this function")


class Worker(object):
    
    def __init__(self, worker_name: str, finish_condition: threading.Condition, parent):
        self._workername = worker_name
        self._lock = threading.RLock()
        self._parent = parent # class: 'Miner'

        self._finish_condition = finish_condition # condition to notify Miner the job is finished
        self._worker_thread = None

        self._cleaned_flag = False # used to clean all jobs
        self._stop_flag = False    # used to stop current job
        self._current_job_id = None
        self._jobs_queue = dict()

        
        self._mine_thread = threading.Thread(target=self._work)
        self._mine_thread.daemon = True
        self._mine_thread.start()

    def clean_job(self):
        debug("cleaning jobs")
        with self._lock:
            self._cleaned =  True

    def _stop(self):
        with self._lock:
            self._stop_flag = True
    
    def remove_job(self, job_id):
        ''' remove job from worker jobs queue '''

        if job_id in self._jobs_queue:
            del self._jobs_queue[job_id]
        elif job_id == self._current_job_id:
            # if the job_id is the one currently processed stop it.
            self._stop_flag = True
        else:
            pass

    def stack_job(self, job_id, prev_hash, coinb1, coinb2, merkle_tree, 
                    version, nbits, ntime, extranonce1, extranonce2_size, target, start=0, stride=1):
        ''' ad job to worker queue '''
        new_job = dict(prev_hash=prev_hash,
                        coinb1=coinb1,
                        coinb2=coinb2,
                        merkle_tree=merkle_tree,
                        version=version,
                        nbits=nbits,
                        ntime=ntime,
                        extranonce1=extranonce1,
                        extranonce2_size=extranonce2_size,
                        target=target,
                        start=start, 
                        stride=stride)
        self._jobs_queue[job_id] = new_job

    def _work(self):
        
        while 1:
            
            if not len(self._jobs_queue) > 0:
                # if there is any work to do
                continue
            
            # reset flags
            self._cleaned_flag = False
            self._stop_flag = False

            # INIT
            self._current_job_id = next(iter(self._jobs_queue))  # take the next job in list
            job = self._jobs_queue.pop(self._current_job_id)
            
            # PROCESSING JOB
            for i in range(40):
                if self._cleaned_flag or self._stop_flag:
                    break
                time.sleep(1)

            # FINISHING
            if self._cleaned_flag:
                with self._lock:
                    self._cleaned_flag = False
                    self._jobs_queue = dict()
                    debug("cleaned jobs")
            
            with self._lock:
                self._parent.set_result(f'Job {job_id} finished by {self._workername}') # write result to parent
                self._finish_condition.notifyAll() # notify that job is done
    
    def calc_merkle_root_bin(extranonce2: str, extranonce1:str, merkle_tree:str, coinb1: str, coinb2: str):

        coinbase = unhexlify(coinb1) + unhexlify(extranonce1) + unhexlify(extranonce2) + unhexlify(coinb2)

        merkle_root = coinbase
        for branch in merkle_tree:
            merkle_root = self.dbl_sha256(merkle_root + unhexlify(branch))
        
        return merkle_root
    
    @staticmethod
    def dbl_sha256(data: bytearray):
        ''' return double sha256 of the imput data '''
        return sha256(sha256(data).digest()).digest()

    def __str__(self):
        return f'WorkerName:{self._workername}'

class Miner(JsonRcpClient):
    ''' Miner Class to handle server and workers '''
    def __init__(self, username):
        super().__init__()
        self._username = username
        self._workers = []

        self._extranonce1 = None
        self._extranonce2_size = None

        # use condition as notification when a worker find a share
        self._finish_condition = threading.Condition()
        # use this variable to set the result of the job done by the corresponding worker 
        self._worker_result = None

        # this way we can handle multiple worker splitting the job
        self._worker_handler = threading.Thread(target=self._handle_workers)
        self._worker_handler.daemon = True
        self._worker_handler.start()


    def set_result(self, result):
        ''' used by a worker to return it's job to the parent Miner'''
        self._worker_result = result

    def _handle_workers(self):
        ''' handle of worker notification'''
        while 1:
            with self._finish_condition:
                self._finish_condition.wait()
                # self.clean_workers_jobs()
                # TODO: terminate all job , send server notification of job finished
                log(self._worker_result)
                   
    def _handle_reply(self, request, reply):
        debug(request, reply)

        if reply.get('error'): # minimum print error message 
            # TODO: handle specific code error
            log("An error occourred: ", reply.get('error'), style=LogStyle.ERROR)

        elif request:  # handle reply from a specific request
            if request.get('method') == 'mining.authorize':

                full_worker_name = request.get('params')[0]  # fullname = 'username.worker_name'
                _ , worker_name = full_worker_name.split('.') 

                if reply.get('result') == True: # add worker only if authorized
                    log(f"Authorized Worker: '{worker_name}'", style=LogStyle.OK)
                    # new_worker_obj = Worker(worker_name, self._finish_condition, self, random.randint(1, 3))
                    new_worker_obj = Worker(worker_name, self._finish_condition, parent=self) 
                    self._workers.append(new_worker_obj) # add worker
                    # debug(new_worker_obj)
                else:
                    log(f"Failed to authorize {full_worker_name}", style=LogStyle.ERROR) # something went wrong 

            if request.get('method') == 'mining.subscribe':
                # result be like:
                # [[["mining.set_difficulty", "subscription id 1"], ["mining.notify", "subscription id 2"]], "extranonce1", extranonce2_size]
                result = reply.get('result')
                self._extranonce1 = unhexlify(result[1]) # as byte in hex
                self._extranonce2_size = result[2]
        else:
            # finally handle request from server without any request
            if reply.get('method') == 'mining.set_difficulty':
                self._difficulty = reply.get('params')[0]
                self._calc_target()
                log(f"Setted difficulty to {self._difficulty}", f"New Target: {hexlify(self._target).decode()}")
            if reply.get('method') == 'mining.notify':
                job_params = reply.get('params')
                self.queue_new_job(*job_params)

    def _calc_target(self):
        ''' calculate target from difficulty given by pool'''

        # formula taken from https://en.bitcoin.it/wiki/Difficulty
        max_target = 0x00ffff*2**(8*(0x1d-3))

        target = int(max_target/self._difficulty)

        self._target = self._as64(target)

    def authorize_worker(self, worker_name, password):
        full_name = self._username + '.' + worker_name
        self.send(method='mining.authorize', params=[full_name, password])

    def subscrime_mining(self):
        # if len(self._workers) == 0:
        #     log("Authorize some worker oterwise you will get no reward", style=LogStyle.WARNING)
        self.send(method='mining.subscribe', params=[])

    def queue_new_job(self, *job_params):
        job_id, prev_hash, coinb1, coinb2, merkle_tree, version, nbits, ntime, clean_job = job_params

        if clean_job:
            self.clean_workers_jobs()
        for worker_index, worker in enumerate(self._workers):
            
            worker.stack_job(job_id=job_id,
                    prev_hash=prev_hash,
                    coinb1=coinb1,
                    coinb2=coinb2,
                    merkle_tree=merkle_tree,
                    version=version,
                    nbits=nbits,
                    ntime=ntime,
                    extranonce1=self._extranonce1,
                    extranonce2_size=self._extranonce2_size,
                    target=self._target,
                    start=worker_index, 
                    stride=len(self._workers))

    def clean_workers_jobs(self):
        ''' notify all workers to stop the mining process '''
        for worker in self._workers:
            worker.clean_job()

    @staticmethod
    def _as64(integer):
        ''' return integer as 64 hex digit format '''
        return unhexlify(f'{integer:064x}')


if __name__ == "__main__":
    os.system('color')
    DEBUG = True
    
    miner = Miner("DarkSteel98")
    miner.connect("stratum+tcp://stratum.slushpool.com:3333")
    miner.authorize_worker("worker1", "pass")
    # miner.authorize_worker("worker2", "pass")
    # miner.authorize_worker("asus", "pass")
    miner.subscrime_mining()
    
    try:
        while 1:
            pass
    except KeyboardInterrupt:
        sys.exit()