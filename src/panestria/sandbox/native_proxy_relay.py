"""Container loopback to one pinned private CONNECT socket; no direct egress or credentials.

Standalone standard-library entry point, mounted read-only by a trusted launcher.
This transports bytes only. Hostname admission stays in the host gateway, TLS
validation stays in the trusted client, and task/policy authority stays outside.
"""

from __future__ import annotations

import os
import selectors
import signal
import socket
import socketserver
import stat
import struct
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

ENDPOINT = Path("/gateway/connect.sock")
LISTEN = ("127.0.0.1", 18080)
BUFFER_BYTES = 64 * 1024


@dataclass(frozen=True)
class SocketIdentity:
    path: Path
    device: int
    inode: int

    def check(self) -> None:
        parent, target = self.path.parent.lstat(), self.path.lstat()
        if (
            not self.path.is_absolute()
            or self.path.resolve(strict=True) != self.path
            or not stat.S_ISDIR(parent.st_mode)
            or parent.st_uid != os.geteuid()
            or stat.S_IMODE(parent.st_mode) != 0o700
            or not stat.S_ISSOCK(target.st_mode)
            or target.st_uid != os.geteuid()
            or stat.S_IMODE(target.st_mode) != 0o600
            or target.st_nlink != 1
            or (target.st_dev, target.st_ino) != (self.device, self.inode)
        ):
            raise ValueError("native_proxy_endpoint_unconfirmed")

    def connect(self) -> socket.socket:
        self.check()
        peer = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            peer.settimeout(2)
            peer.connect(str(self.path))
            _pid, uid, _gid = struct.unpack("3i", peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            self.check()
            if uid != os.geteuid():
                raise ValueError("native_proxy_peer_unconfirmed")
            return peer
        except BaseException:
            peer.close()
            raise


class RelayBudget:
    def __init__(self, *, byte_cap: int = 16 * 1024 * 1024, connections: int = 16, live: int = 2) -> None:
        if (
            type(byte_cap) is not int
            or not 1024 <= byte_cap <= 16 * 1024 * 1024
            or type(connections) is not int
            or not 1 <= connections <= 16
            or type(live) is not int
            or not 1 <= live <= 2
        ):
            raise ValueError("invalid_native_proxy_budget")
        self.remaining = byte_cap
        self.maximum = connections
        self.attempts = 0
        self.admission = threading.BoundedSemaphore(live)
        self.lock = threading.Lock()
        self.sockets: set[socket.socket] = set()
        self.closing = threading.Event()

    def admit(self) -> bool:
        with self.lock:
            if self.closing.is_set() or self.attempts >= self.maximum:
                self.closing.set()
                return False
            self.attempts += 1
        return self.admission.acquire(blocking=False)

    def charge(self, amount: int) -> bool:
        with self.lock:
            if amount > self.remaining or self.closing.is_set():
                return False
            self.remaining -= amount
            return True

    def register(self, peer: socket.socket) -> None:
        with self.lock:
            if self.closing.is_set():
                raise OSError("native_proxy_stopping")
            self.sockets.add(peer)

    def stop(self) -> None:
        with self.lock:
            self.closing.set()
            peers = tuple(self.sockets)
        for peer in peers:
            try:
                peer.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            peer.close()


def pump(left: socket.socket, right: socket.socket, budget: RelayBudget, deadline: float) -> None:
    """Bound both directions, drain queued bytes and propagate half-close without blocking writes."""
    sockets = (left, right)
    other = {left: right, right: left}
    pending = {peer: bytearray() for peer in sockets}
    readable = {peer: True for peer in sockets}
    registered: set[socket.socket] = set()
    shut: set[socket.socket] = set()
    for peer in sockets:
        peer.setblocking(False)
    with selectors.DefaultSelector() as selector:
        while not budget.closing.is_set() and time.monotonic() < deadline:
            if budget.remaining == 0:
                readable = {peer: False for peer in sockets}
            if not any(readable.values()) and not any(pending.values()):
                return
            for peer in sockets:
                target = other[peer]
                if not readable[peer] and not pending[target] and target not in shut:
                    try:
                        target.shutdown(socket.SHUT_WR)
                    except OSError:
                        pass
                    shut.add(target)
                mask = selectors.EVENT_READ if readable[peer] and len(pending[target]) < BUFFER_BYTES else 0
                if pending[peer]:
                    mask |= selectors.EVENT_WRITE
                if mask:
                    if peer in registered:
                        selector.modify(peer, mask)
                    else:
                        selector.register(peer, mask)
                        registered.add(peer)
                elif peer in registered:
                    selector.unregister(peer)
                    registered.remove(peer)
            for key, mask in selector.select(min(0.05, max(0.0, deadline - time.monotonic()))):
                source = key.fileobj
                if not isinstance(source, socket.socket):
                    raise ValueError("invalid_native_proxy_channel")
                peer = source
                if mask & selectors.EVENT_READ:
                    amount = min(16 * 1024, BUFFER_BYTES - len(pending[other[peer]]), budget.remaining)
                    try:
                        data = peer.recv(amount)
                    except BlockingIOError:
                        data = None
                    if data == b"":
                        readable[peer] = False
                    elif data is not None:
                        if not budget.charge(len(data)):
                            return
                        pending[other[peer]].extend(data)
                if mask & selectors.EVENT_WRITE and pending[peer]:
                    try:
                        sent = peer.send(pending[peer])
                    except BlockingIOError:
                        sent = 0
                    del pending[peer][:sent]


class _Handler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        server = self.server
        if not isinstance(server, RelayServer):
            return
        upstream: socket.socket | None = None
        try:
            server.budget.register(self.request)
            upstream = server.identity.connect()
            server.budget.register(upstream)
            pump(self.request, upstream, server.budget, min(server.deadline, time.monotonic() + 60))
        except (OSError, ValueError):
            pass  # Neither request bytes, credential headers nor host paths enter logs.
        finally:
            with server.budget.lock:
                server.budget.sockets.discard(self.request)
                if upstream is not None:
                    server.budget.sockets.discard(upstream)
            if upstream is not None:
                upstream.close()
            server.budget.admission.release()


class RelayServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    block_on_close = False
    allow_reuse_address = False
    request_queue_size = 2

    def __init__(
        self,
        address: tuple[str, int],
        identity: SocketIdentity,
        *,
        budget: RelayBudget | None = None,
        lifetime_seconds: float = 90.0,
    ) -> None:
        if (
            address[0] != "127.0.0.1"
            or type(lifetime_seconds) not in {int, float}
            or not 0.1 <= lifetime_seconds <= 120
        ):
            raise ValueError("invalid_native_proxy_listener")
        identity.check()
        self.identity = identity
        self.budget = budget if budget is not None else RelayBudget()
        self.deadline = time.monotonic() + lifetime_seconds
        super().__init__(address, _Handler)
        self.timeout = 0.1

    def process_request(self, request: socket.socket | tuple[bytes, socket.socket], client_address: object) -> None:
        if not isinstance(request, socket.socket):
            raise ValueError("native_proxy_stream_required")
        if not self.budget.admit():
            request.close()
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.budget.admission.release()
            request.close()
            raise

    def handle_error(self, request: object, client_address: object) -> None:
        pass  # socketserver's default traceback could expose untrusted transport.


def main() -> None:
    stopped = [False]
    if sys.platform != "linux" or os.geteuid() == 0:
        raise SystemExit("native_proxy_platform_unavailable")
    if len(sys.argv) != 3 or any(not arg.isdecimal() or not 1 <= len(arg) <= 20 for arg in sys.argv[1:]):
        raise SystemExit("native_proxy_identity_required")
    identity = SocketIdentity(ENDPOINT, int(sys.argv[1]), int(sys.argv[2]))
    try:
        with RelayServer(LISTEN, identity) as server:
            # Signal handlers only set a flag; acquiring locks/shutdown here
            # could deadlock the serving thread. The accept timeout is bounded.
            for kind in (signal.SIGTERM, signal.SIGINT):
                signal.signal(kind, lambda _signal, _frame: stopped.__setitem__(0, True))
            print("NATIVE_PROXY_READY", flush=True)
            try:
                while not stopped[0] and not server.budget.closing.is_set() and time.monotonic() < server.deadline:
                    server.handle_request()
            finally:
                server.budget.stop()
    except (OSError, ValueError):
        raise SystemExit("native_proxy_unavailable") from None


if __name__ == "__main__":
    main()
