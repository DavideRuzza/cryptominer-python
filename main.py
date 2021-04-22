import os
import sys
import threading

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
            self._message_id += 1
            self._socket.send((request+'\n').encode())

    def handle_reply(self, request, reply):
        ''' override this function '''
        raise NotImplementedError("Override this function")


if __name__ == "__main__":
    os.system('color')
    DEBUG = True
    
    try:
        while 1:
            pass
    except KeyboardInterrupt:
        sys.exit()