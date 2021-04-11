import socket, json, urllib.parse, threading
from time import sleep



class JsonRcpClient(object):
    ''' Simple Json RCP client'''
    
    def __init__(self):
        self._socket = None
        self._rcp_thread = None
        self._message_id = 1
        self._lock = threading.RLock()
    
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
            self.handle_reply(reply)
            
        
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
        request = json.dumps(request)
        print(request)
        with self._lock:
            self._message_id += 1
            self._socket.send((request+'\n').encode())
    
    def handle_reply(self, reply):
        print(reply)


# TEST (slush pool)
client = JsonRcpClient()
client.connect('stratum+tcp://stratum.slushpool.com:3333')
client.send("mining.subscribe", [])

