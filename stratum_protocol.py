import socket, json, urllib.parse, threading
from binascii import hexlify, unhexlify
from hashlib import sha256
import time
import sys
import struct
# from time import sleep




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
            
            self.handle_reply(request, reply)
            
        
    def connect(self, url: str):
        """Create socket and start the receiving process

        Args:
            url (str): server of mining pool
        """
        
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        parser = urllib.parse.urlparse(url)
        
        self._socket.connect((parser.hostname, parser.port))

        self._rcp_thread = threading.Thread(target=self.rcp_thread_fun)
        self._rcp_thread.daemon = True  # only for testing it should be not commented 
        self._rcp_thread.start()
    
    def send(self, method: str, params: list):
        """Send request to server

        Args:
            method (str): request method (ie. 'mining.subcribe', 'mining.authorize', ...)
            params (list): list of params required with the corresponding request method 
        """
        
        request = dict(id=self._message_id, method=method, params=params)
        self._requests[self._message_id] = request

        request = json.dumps(request)

        # print(request)
        with self._lock:
            self._message_id += 1
            self._socket.send((request+'\n').encode())

    def handle_reply(self, request, reply):
        ''' override this function '''
        raise NotImplementedError("Override this function")

class Job(object):
    def __init__(self, job_id, coinb1, coinb2, extranonce1, extranonce2_size, version, prev_hash, bits, ntime, merkle_tree):

        # job finsh flag
        self._done = False

        # job parameters
        self._job_id = job_id
        self._conib1 = coinb1
        self._coinb2 = coinb2
        self._extranonce1 = extranonce1
        self._extranonce2_size = extranonce2_size
        self._version = version
        self._bits = bits
        self._perv_hash = prev_hash
        self._ntime = ntime
        self._merkle_tree = merkle_tree
        
        # miner metrics
        self._dt = 0.0
        self._hash_count = 0

    @property
    def hashrate(self):
        '''The current hashrate, or if stopped hashrate for the job's lifetime.'''

        if self._dt == 0: return 0.0
        return self._hash_count / self._dt

    def stop(self):
        ''' request to stop the job'''
        self._done = True

    def dbl_sha256(self, data):
        ''' double sha256'''
        return sha256(sha256(data).digest()).digest()

    def calc_merkle_root_bin(self, merkle_tree, extranonce2_bin):
        ''' calculate merkle root from merkle_tree and etranonce2'''
        coinbase = unhexlify(self._coinb1) + unhexlify(self._extranonce1) + extranonce2_bin + unhexlify(self._coinb2)
        coinbase_hash_bin = self.dbl_sha256(coinbase)

        merkle_root = coinbase_hash_bin
        for branch in merkle_tree:
            merkle_root = self.dbl_sha256(merkle_root + unhexlify(branch))
        
        return merkle_root

    def swap_endian(self, word):
        ''' swap endianess of hex word'''
        word_bin = unhexlify(word)
        return word_bin[::-1]
    
    def swap_endian_4(self, word):
        ''' swap every 4 byte and endianess too'''

        word_bin = unhexlify(word)
        
        if len(word_bin)%8 != 0:
            log("Word length not divisible by 8", style=LogStyle.WARNING)
            sys.exit()
        else:
            return b''.join([word_bin[4 * (i+1): 4*(i+2)]+word_bin[4 * i: 4*(i+1)] for i in range(len(word_bin)//8)])[::-1]

    def calc_extranonce2_bin(self, extranonce):
        ''' format extranonce2 as requested from server '''
        if self.extranonce2_size == 8:
            return struct.pack("<Q", extranonce)
        elif self.extranonce2_size == 4:
            return struct.pack("<I", extranonce)
        elif self.extranonce2_size == 2:
            return struct.pack("<H", extranonce)
        else:
            return None

    def mine(self):
        ''' mining function as generator '''
        t0 = time.time()
        for extranonce2 in range(0, 2**(4*self._extranonce2_size)-1):

            extranonce2_bin = self.calc_extranonce2_bin(extranonce2)

            merkle_root_bin = self.calc_merkle_root_bin(self.merkle_tree, extranonce2_bin)

            header_bin_prefix = self.swap_endian(self._version) + self.swap_endian_4(self._prev_hash) + \
                                merkle_root_bin + self.swap_endian(self._ntime) + self.swap_endian(self._bits)
            
            for nonce in range(0, 0xffffff):

                if self._done:
                    self._dt += (time.time() - t0)
                    raise StopIteration()

                nonce_bin = struct.pack('<I', nonce)
                hash = self.dbl_sha256(header_bin_prefix+nounce_bin)[::-1]

                if hash < self._target:
                    log("Found nonce!", style=LogStyle.LOG)

                    result = dict(
                        job_id = self._job_id,
                        extranounce2 = hexlify(extranounce2_bin),
                        ntime = self._ntime,
                        nounce = hexlify(nounce_bin[::-1])
                    )
                    
                    yield result

                    t0 = time.time()

                self._hash_count += 1   


class Subscription(object):
    ''' Subscription class that manage and spawn new jobs'''
    def __init__(self):
        self._id = None
        self._extranonce1 = None
        self._extranonce2_size = None
        self._difficulty = None
        self._target = None

        self._username = None
        self._password = None

        self._mining_thread = None        
        
    id = property(lambda s: s._id)
    extranonce1 = property(lambda s: s._extranonce1)
    extranonce2_size = property(lambda s: s._extranonce2_size)
    
    def set_subscription(self, sub_id, ext1, ext2_size):
        id = sub_id
        extranonce1 = ext1
        extranonce2_size = ext2_size

    def set_difficulty(self, difficulty):
        
        max_target = 0x00ffff * 2 ** (8 * (0x1d-3))
        if difficulty == 0:
            self._set_target(2**256-1)
        else:
            self._set_target( min(int(max_target/difficulty), 2**256-1) )
    
    def _set_target(self, target):
        self._target = unhexlify(f'{target:064x}')


    def spawn_new_job(self, job_id, prev_hash, coinb1, coinb2, merkle_tree, version, bits, ntime, clean_job):
        # debug(f'{job_id=}', f'{version=}', f'{nbits=}', f'{ntime=}')
        if clean_job:
            log("Received Job is not clean. Waiting for clean job", style=LogStyle.WARNING)
            return None
        else:
            log("Job Accepted", style=LogStyle.LOG)
            new_job = Job(job_id, 
                        coinb1, coinb2, 
                        self.extranonce1, 
                        self.extranonce2_size, 
                        version, 
                        prev_hash, 
                        bits, ntime, 
                        merkle_tree
                        )
            return new_job

        
class Miner(JsonRcpClient):
    
    class AuthorizationException(Exception): pass
    
    def __init__(self, username: str, password: str):
        super().__init__()
        self._username = username
        self._password = password
        self._subscription = Subscription()

        self._job = None

    def handle_reply(self, request, reply):
        ''' Server response handling '''

        debug(request, reply) # for debug purpose. it should be commmented
        if reply.get("error") != None and reply.get("result") == None:
            # catch error and terminate process
            # TODO: bad error handling. need to check on code error and handle each one differently
            # for now minimun message is printed
            error = reply.get('error')
            log("Bad request message.", 
                f"Code Error:{error[0]}", 
                f"Cause of the problem: '{error[1]}'",
                style=LogStyle.WARNING)
            sys.exit()

        elif request:  # if reply refer to some request
            
            if request.get("method") == "mining.authorize":
                if reply.get("result") == True:
                    log("Authorization Accepted", style=LogStyle.OK)
                else:
                    log("Authorization Failed. check username or password", style=LogStyle.ERROR)
                    sys.exit()

            if request.get("method") == "mining.subscribe":
                # server std reply to mining.authorize
                # {"id": 1,"result":[[["mining.set_difficulty", "-"], ["mining.notify", subscription_id]], extranonce1, extranonce2_size]}
                params = reply.get("result")
                subscription_id = params[0][1][0] # is there a more clever way to take this values?
                extranonce1 = params[1]
                extranonce2_size = params[2]
                self._subscription.set_subscription(subscription_id, extranonce1, extranonce2_size)
        else:
            if reply.get("method") == "mining.set_difficulty":
                difficulty = reply.get("params")[0]
                self._subscription.set_difficulty(difficulty)
                log(f"Setted difficulty to {difficulty}", style=LogStyle.LOG)

            if reply.get("method") == "mining.notify":
                
                job_params = reply.get("params")
                if not job_params or len(job_params) != 9:
                    log("Bad job received", style=LogStyle.WARNING)
                else:
                    log("Got new Job!", style=LogStyle.LOG)
                    self._job = self._subscription.spawn_new_job(*job_params)

    def start_mining(self):
        pass

            
DEBUG = False

# TEST (slush pool)
client = Miner("DarkSteel98.asus", "pwd")
client.connect('stratum+tcp://stratum.slushpool.com:3333')

client.send("mining.authorize", ["DarkSteel98.asus", "pwd"])
client.send("mining.subscribe", [])

try:
    while 1:
        pass
except KeyboardInterrupt:
    sys.exit()
    
     