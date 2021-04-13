import socket, json, urllib.parse, threading
import time
import sys
# from time import sleep



class LogStyle():
    '''Increase terminal legibility'''
    
    # HELP: https://stackoverflow.com/questions/287871/how-to-print-colored-text-to-the-terminal
    LOG = ["[LOG]", "0;30;47"]
    WARNING = ["[WARNING]", "0;30;43"]
    ERROR = ["[ERROR]", "0;30;41"]
    OK = ["[OK]", "6;30;42"]
    
    
    
def log(*message, style=["[-]", ''], date=True):
    '''logging message with colored style

        style parameter should be set equal to ՝LogStyle.LOG՝, ՝LogStyle.WARNING՝ or ՝LogStyle.ERROR՝
    '''
    log_str = style[0]
    log_style = style[1]
    print(f'\x1b[{log_style}m{log_str:^9}\x1b[0m', end='')
    
    if date:
        print('\x1b[1;30;1m - '+time.strftime("%d/%m/%y %H:%M:%S", time.gmtime())+" - \x1b[0m", end='') 
    
    log_space = f"\x1b[{log_style}m"+ " "*9 + "\x1b[0m"
    date_space = ' '*23 if date else ''
    
    print(("\n"+log_space+date_space).join([f"{msg}" for msg in message]))
    
     
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
        # self._rcp_thread.daemon = True  # only for testing it should be not commented 
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
    
    # ONLY FOR DEBUG
    # def send_raw(self, request):
    #     with self._lock:
    #         self._message_id += 1
    #         self._socket.send((request+'\n').encode())

    def handle_reply(self, request, reply):
        raise NotImplementedError("Override this function")


class Subscription(object):
    def __init__(self):
        self._id = None
        self._extranounce1 = None
        self._extranounce2_size = None
        self._difficulty = None
        self._target = None
        
        
    id = property(lambda s: self._id)
    extranounce1 = property(lambda s: self._extranounce1)
    extranounce2_size = property(lambda s: self._extranounce2_size)
    
    def set_subscription():
        pass
   
    
class Miner(JsonRcpClient):
    
    class AuthorizationException(Exception): pass
    
    def __init__(self, username: str, password: str):
        super().__init__()
        self._username = username
        self._password = password
        self._subscription = Subscription()

    def handle_reply(self, request, reply):
        if reply.get("error") != None and reply.get("result") == None:
            error = reply.get('error')
            log("Bad request message.", 
                f"Code Error:{error[0]}", 
                f"Cause of the problem: '{error[1]}'",
                style=LogStyle.WARNING)
            sys.exit()
        elif request:
            if request.get("method") == "mining.authorize":
                if reply.get("result") == True:
                    log("Authorization Accepted", style=LogStyle.OK)
                else:
                    log("Authorization Failed. check username or password", style=LogStyle.ERROR)
                    sys.exit()

        # else:       
        #     if reply.get("method") == "mining.set_difficulty":
        #         pass
        

# TEST (slush pool)
client = Miner("DarkSteel98.asus", "pwd")
client.connect('stratum+tcp://stratum.slushpool.com:3333')

client.send("mining.authorize", ["DarkSteel98.asus", "pwd"])
client.send("mining.subscribe", [])

