import socket, json, urllib.parse, threading
from time import sleep

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


class Miner(JsonRcpClient):
    def __init__(self, username, password):
        super().__init__()

    def handle_reply(self, request, reply):
        print(reply)



# TEST (slush pool)
client = Miner("DarkSteel98.asus", "pwd")  #Miner("Darksteel.worker1", 'pwd')
client.connect('stratum+tcp://stratum.slushpool.com:3333')

client.send("mining.authorize", ["DarkSteel98.asus", "pwd"])
client.send("mining.subscribe", [])

