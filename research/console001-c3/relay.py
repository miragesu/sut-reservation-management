"""Loopback-only fault injector; killing it drops its one mock SSH TCP transport."""
import selectors
import socket

listener = socket.socket()
listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
listener.bind(('127.0.0.1', 2223))
listener.listen(1)
print('READY', flush=True)
client, _ = listener.accept()
server = socket.create_connection(('127.0.0.1', 2222))
selector = selectors.DefaultSelector()
selector.register(client, selectors.EVENT_READ, server)
selector.register(server, selectors.EVENT_READ, client)
while True:
    for key, _ in selector.select():
        data = key.fileobj.recv(65536)
        if not data:
            raise SystemExit(0)
        key.data.sendall(data)
