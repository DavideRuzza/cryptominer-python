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
        self._parent = parent

        self._finish_condition = finish_condition
        self._mine_thread = None
        
    def start_mining(self):
        # TODO: add parameter to handle job
        self._mine_thread = threading.Thread(target=self._mine)
        self._mine_thread.daemon = True
        self._mine_thread.start()

    def _mine(self):
        with self._lock:
            self._parent.set_result(f'Job finished by {self._workername}')
        
        with self._finish_condition:
            self._finish_condition.notifyAll()

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
        ''' used by a worker to return it's job'''
        self._worker_result = result

    def _handle_workers(self):
        ''' handle of worker notification'''
        while 1:
            with self._finish_condition:
                self._finish_condition.wait()
                # TODO: terminate all job 
                log(self._worker_result)   

    def _handle_reply(self, request, reply):
        debug(request, reply)

        if reply.get('error'): # minimum print error message 
            # TODO: handle specific code error
            log("An error occourred: ", reply.get('error'), style=LogStyle.ERROR)

        elif request:  # handle reply from a specific request
            if request.get('method') == 'mining.authorize':

                full_worker_name = request.get('params')[0]  # full name = 'username.worker_name'
                _ , worker_name = full_worker_name.split('.') 

                if reply.get('result') == True: # add worker only if authorized
                    log(f"Authorized Worker: '{worker_name}'", style=LogStyle.OK)
                    new_worker_obj = Worker(worker_name, self._finish_condition, self, random.randint(1, 3)) 
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
                for worker in self._workers:
                    worker.start_mining()
    
    @staticmethod
    def _as64(integer):
        return unhexlify(f'{integer:064x}')

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