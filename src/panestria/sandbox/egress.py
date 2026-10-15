"""Allowlisted CONNECT over a private Unix socket; validate DNS once and pin its IP."""

from __future__ import annotations

import ipaddress
import os
import selectors
import socket
import socketserver
import threading
import time
from collections import deque
from pathlib import Path


class EgressDenied(Exception):
    pass


def resolve_destination(authority: str, allowed_hosts: frozenset[str]) -> tuple[str, int]:
    host, separator, port = authority.rpartition(":")
    if not separator or port != "443" or host.lower() not in allowed_hosts or host != host.lower():
        raise EgressDenied("destination_denied")
    try:
        answers = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError:
        raise EgressDenied("dns_unavailable") from None
    addresses = {str(answer[4][0]) for answer in answers}
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise EgressDenied("private_destination_denied")
    # Return an IP, not a hostname: connect cannot perform a second DNS lookup.
    return sorted(addresses)[0], 443


def tunnel(left: socket.socket, right: socket.socket, *, timeout: float = 120, byte_cap: int = 16 * 1024**2) -> None:
    selector = selectors.DefaultSelector()
    selector.register(left, selectors.EVENT_READ, right)
    selector.register(right, selectors.EVENT_READ, left)
    deadline = time.monotonic() + timeout
    remaining = byte_cap
    try:
        while time.monotonic() < deadline and remaining > 0:
            for key, _ in selector.select(min(0.5, max(0, deadline - time.monotonic()))):
                source = key.fileobj
                if not isinstance(source, socket.socket):
                    raise EgressDenied("invalid_tunnel")
                data = source.recv(min(16_384, remaining))
                if not data:
                    return
                remaining -= len(data)
                key.data.sendall(data)
    finally:
        selector.close()


class _Gateway(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    block_on_close = False
    allowed_hosts: frozenset[str]
    audit: deque[tuple[str, str]]
    admission: threading.BoundedSemaphore
    connections: set[socket.socket]
    connection_lock: threading.Lock
    closing: threading.Event

    def process_request(self, request: socket.socket | tuple[bytes, socket.socket], client_address: object) -> None:
        if not isinstance(request, socket.socket):
            raise EgressDenied("stream_socket_required")
        if self.closing.is_set() or not self.admission.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.admission.release()
            request.close()
            raise


class _Connect(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        gateway = self.server
        if not isinstance(gateway, _Gateway):
            return
        with gateway.connection_lock:
            gateway.connections.add(self.request)
        try:
            self.request.settimeout(5)
            header = bytearray()
            while not header.endswith(b"\r\n\r\n"):
                chunk = self.request.recv(1)
                if not chunk or len(header) >= 8192:
                    raise EgressDenied("invalid_connect")
                header.extend(chunk)
            method, authority, version = bytes(header).split(b"\r\n", 1)[0].decode("ascii").split(" ")
            if method != "CONNECT" or version != "HTTP/1.1":
                raise EgressDenied("connect_required")
            ip, port = resolve_destination(authority, gateway.allowed_hosts)
            if gateway.closing.is_set():
                raise EgressDenied("gateway_closed")
            with socket.create_connection((ip, port), timeout=5) as upstream:
                with gateway.connection_lock:
                    if gateway.closing.is_set():
                        raise EgressDenied("gateway_closed")
                    gateway.connections.add(upstream)
                if not ipaddress.ip_address(upstream.getpeername()[0]).is_global:
                    raise EgressDenied("private_peer_denied")
                gateway.audit.append((authority, "ALLOWED"))
                self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                self.request.settimeout(5)
                tunnel(self.request, upstream)
        except (OSError, ValueError, UnicodeError, EgressDenied):
            gateway.audit.append(("redacted", "DENIED"))
            try:
                self.request.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
            except OSError:
                pass
        finally:
            with gateway.connection_lock:
                gateway.connections.discard(self.request)
                gateway.connections = {peer for peer in gateway.connections if peer.fileno() != -1}
            gateway.admission.release()


class EgressGateway:
    def __init__(self, directory: Path, allowed_hosts: frozenset[str]) -> None:
        if not allowed_hosts or not allowed_hosts.issubset({"api.anthropic.com", "claude.ai", "platform.claude.com"}):
            raise EgressDenied("unknown_provider_allowlist")
        directory.mkdir(mode=0o700, parents=True, exist_ok=False)
        self.path = directory / "connect.sock"
        self.server = _Gateway(str(self.path), _Connect)
        self.server.allowed_hosts = allowed_hosts
        self.server.audit = deque(maxlen=256)
        self.server.admission = threading.BoundedSemaphore(8)
        self.server.connections = set()
        self.server.connection_lock = threading.Lock()
        self.server.closing = threading.Event()
        os.chmod(self.path, 0o600)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> EgressGateway:
        self.thread.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self.server.closing.set()
        self.server.shutdown()
        with self.server.connection_lock:
            peers = list(self.server.connections)
        for peer in peers:
            try:
                peer.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            peer.close()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.path.unlink(missing_ok=True)
        self.path.parent.rmdir()
