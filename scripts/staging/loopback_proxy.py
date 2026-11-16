"""Runner loopback access to verified containers on an internal Docker bridge."""

import ipaddress
import select
import socket
import socketserver
import threading


def validate_target(address, subnet, listen_port, target_port):
    ip = ipaddress.IPv4Address(address)
    network = ipaddress.IPv4Network(subnet)
    private = [ipaddress.IPv4Network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")]
    if ip not in network or not any(network.subnet_of(n) for n in private):
        raise ValueError("Forwarding target must be in the verified private staging network")
    if (listen_port, target_port) not in {(8000, 8000), (5173, 80)}:
        raise ValueError("Only the fixed staging API and frontend ports are permitted")
    return str(ip)


def start(address, subnet, listen_port, target_port):
    target = validate_target(address, subnet, listen_port, target_port)

    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            try:
                with socket.create_connection((target, target_port), timeout=10) as upstream:
                    self.request.settimeout(30)
                    upstream.settimeout(30)
                    while True:
                        readable, _, _ = select.select([self.request, upstream], [], [], 30)
                        if not readable:
                            return
                        for source in readable:
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
        block_on_close = False

    server = Server(("127.0.0.1", listen_port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
