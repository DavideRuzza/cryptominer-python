import socket

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect(("eu.stratum.slushpool.com", 3333))

sock.close()