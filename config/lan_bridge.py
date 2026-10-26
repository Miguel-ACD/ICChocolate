"""Forward the ESP32 LAN endpoint to Docker Desktop's loopback port.

Run this on Windows alongside `docker compose up -d web`. The Windows firewall
rule for ICChocolate limits inbound TCP 8000 to the local 192.168.18.0/24 LAN.
"""

import ipaddress
import select
import socket
import socketserver

LISTEN = ("192.168.18.244", 8000)
UPSTREAM = ("127.0.0.1", 8001)
ALLOWED = ipaddress.ip_network("192.168.18.0/24")


class Forwarder(socketserver.BaseRequestHandler):
    def handle(self):
        if ipaddress.ip_address(self.client_address[0]) not in ALLOWED:
            return
        try:
            with socket.create_connection(UPSTREAM, timeout=5) as upstream:
                endpoints = (self.request, upstream)
                while True:
                    ready, _, _ = select.select(endpoints, [], [], 90)
                    if not ready:
                        return
                    for source in ready:
                        data = source.recv(65536)
                        if not data:
                            return
                        destination = upstream if source is self.request else self.request
                        destination.sendall(data)
        except OSError:
            return


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    with Server(LISTEN, Forwarder) as server:
        server.serve_forever()
