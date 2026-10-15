"""One-session private Unix transport. Callback authority is not supplied by clients."""

from __future__ import annotations

import math
import os
import queue
import socket
import stat
import struct
import threading
import time
from pathlib import Path
from typing import Self

from panestria.brokers.harness.command_protocol import PreparedCheck, RegisteredCheckSession
from panestria.contracts.native_tools import MAX_PAYLOAD_BYTES

_FRAME_SECONDS = 5.0
_SHUTDOWN_SECONDS = 2.0


class CommandTransportUnavailable(ValueError):
    pass


class MessageFrames:
    def __init__(self) -> None:
        self.pending = bytearray()

    def feed(self, data: bytes) -> list[bytes]:
        self.pending.extend(data)
        frames = []
        while b"\n" in self.pending:
            end = self.pending.index(b"\n")
            if not 0 < end <= MAX_PAYLOAD_BYTES:
                raise CommandTransportUnavailable("invalid_message_frame")
            frame = bytes(self.pending[:end])
            try:
                frame.decode("utf-8", errors="strict")
            except UnicodeError:
                raise CommandTransportUnavailable("invalid_message_frame") from None
            frames.append(frame)
            del self.pending[: end + 1]
        if len(self.pending) > MAX_PAYLOAD_BYTES:
            raise CommandTransportUnavailable("message_frame_limit")
        return frames


def peer_identity(connection: socket.socket) -> tuple[int, int]:
    try:
        pid, uid, _gid = struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    except (OSError, AttributeError, struct.error):
        raise CommandTransportUnavailable("peer_identity_unavailable") from None
    return pid, uid


def private_endpoint(path: Path) -> tuple[int, int]:
    try:
        if not path.is_absolute() or path.resolve(strict=True) != path:
            raise CommandTransportUnavailable("unsafe_private_endpoint")
        parent, endpoint = path.parent.stat(), path.lstat()
        if (
            not stat.S_ISDIR(parent.st_mode)
            or parent.st_uid != os.getuid()
            or stat.S_IMODE(parent.st_mode) != 0o700
            or not stat.S_ISSOCK(endpoint.st_mode)
            or endpoint.st_uid != os.getuid()
            or stat.S_IMODE(endpoint.st_mode) != 0o600
        ):
            raise CommandTransportUnavailable("unsafe_private_endpoint")
        return endpoint.st_dev, endpoint.st_ino
    except (OSError, RuntimeError):
        raise CommandTransportUnavailable("private_endpoint_unavailable") from None


class RegisteredCheckSocket:
    def __init__(
        self,
        directory: Path,
        session: RegisteredCheckSession,
        *,
        lifetime_seconds: float = 120.0,
    ) -> None:
        if (
            type(lifetime_seconds) not in (int, float)
            or not 0.1 <= lifetime_seconds <= 300
            or not math.isfinite(lifetime_seconds)
            or not isinstance(session, RegisteredCheckSession)
        ):
            raise CommandTransportUnavailable("invalid_transport_configuration")
        self.directory, self.path, self.session = directory, directory / "check.sock", session
        self._lifetime = lifetime_seconds
        self._deadline = 0.0
        self._listener: socket.socket | None = None
        self._client: socket.socket | None = None
        self._stop = threading.Event()
        self._state_lock, self._send_lock, self._close_lock = threading.Lock(), threading.Lock(), threading.Lock()
        self._jobs: queue.Queue[PreparedCheck] = queue.Queue(maxsize=4)
        self._threads: list[threading.Thread] = []
        self._dir_fd = -1
        self._dir_identity: tuple[int, int] | None = None
        self.identity: tuple[int, int] | None = None
        self.pid = os.getpid()
        self.reason = "not_started"
        self._started = False
        self._cleanup_ok = True

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(self, *_args: object) -> None:
        if not self.close():
            raise CommandTransportUnavailable("transport_shutdown_unconfirmed")

    def start(self) -> None:
        if self._started or self._stop.is_set():
            raise CommandTransportUnavailable("transport_already_started")
        try:
            if (
                not self.directory.is_absolute()
                or self.directory.parent.resolve(strict=True) != self.directory.parent
                or len(os.fsencode(self.path)) > 100
            ):
                raise CommandTransportUnavailable("unsafe_transport_directory")
            os.mkdir(self.directory, mode=0o700)
            created = self.directory.lstat()
            self._dir_identity = (created.st_dev, created.st_ino)
            self._dir_fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            info = os.fstat(self._dir_fd)
            self._dir_identity = (info.st_dev, info.st_ino)
            if stat.S_IMODE(info.st_mode) != 0o700 or info.st_uid != os.getuid():
                raise CommandTransportUnavailable("unsafe_transport_directory")
            self._listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._listener.bind(str(self.path))
            node = os.stat("check.sock", dir_fd=self._dir_fd, follow_symlinks=False)
            self.identity = (node.st_dev, node.st_ino)
            os.chmod("check.sock", 0o600, dir_fd=self._dir_fd)
            self._listener.listen(1)
            self._listener.settimeout(0.1)
            self._deadline, self._started, self.reason = time.monotonic() + self._lifetime, True, "listening"
            self._threads = [threading.Thread(target=self._work, daemon=True) for _ in range(2)]
            self._threads.append(threading.Thread(target=self._serve, daemon=True))
            for thread in self._threads:
                thread.start()
        except (OSError, RuntimeError, CommandTransportUnavailable):
            self.close()
            raise CommandTransportUnavailable("transport_start_unavailable") from None

    def _request_stop(self, reason: str) -> None:
        with self._state_lock:
            if not self._stop.is_set():
                self.reason = reason
            self._stop.set()
            for connection in (self._client, self._listener):
                if connection is not None:
                    try:
                        connection.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                    connection.close()
        self.session.close()

    def _serve(self) -> None:
        try:
            listener = self._listener
            assert listener is not None
            while not self._stop.is_set():
                if time.monotonic() >= self._deadline:
                    self._request_stop("transport_expired")
                    return
                try:
                    client, _ = listener.accept()
                    break
                except TimeoutError:
                    continue
            else:
                return
            with self._state_lock:
                self._client = client
            listener.close()  # One connection for this bound session, no reconnect/reinitialize.
            if peer_identity(client)[1] != os.getuid():
                raise CommandTransportUnavailable("peer_uid_denied")
            client.settimeout(0.2)
            self.reason = "connected"
            frames, partial_since = MessageFrames(), None
            while not self._stop.is_set() and not self.session.closed:
                now = time.monotonic()
                if now >= self._deadline or (partial_since is not None and now - partial_since >= _FRAME_SECONDS):
                    self._request_stop("transport_deadline")
                    return
                try:
                    data = client.recv(4096)
                except TimeoutError:
                    continue
                if not data:
                    self._request_stop("peer_eof")
                    return
                for message in frames.feed(data):
                    prepared = self.session.prepare(message)
                    if isinstance(prepared, PreparedCheck):
                        self._jobs.put_nowait(prepared)
                    else:
                        self._reply(prepared)
                partial_since = (partial_since or now) if frames.pending else None
            self._request_stop("session_closed")
        except (OSError, CommandTransportUnavailable, queue.Full):
            self._request_stop("transport_input_unavailable")

    def _work(self) -> None:
        while not self._stop.is_set():
            try:
                operation = self._jobs.get(timeout=0.05)
            except queue.Empty:
                continue
            if self._stop.is_set():
                return
            try:
                self._reply(self.session.run(operation))
            except Exception:
                self._request_stop("transport_worker_unavailable")

    def _reply(self, reply: bytes | None) -> None:
        if reply is not None:
            if len(reply) > MAX_PAYLOAD_BYTES:
                raise CommandTransportUnavailable("response_frame_limit")
            with self._send_lock:
                client = self._client
                if client is None or self._stop.is_set():
                    return
                client.sendall(reply + b"\n")

    def close(self) -> bool:
        with self._close_lock:
            self._request_stop("transport_closed")
            deadline = time.monotonic() + _SHUTDOWN_SECONDS
            for thread in self._threads:
                if thread is not threading.current_thread() and thread.ident is not None:
                    thread.join(timeout=max(0, deadline - time.monotonic()))
            stopped = not any(thread.is_alive() for thread in self._threads)
            if self._dir_fd >= 0:
                try:
                    try:
                        node = os.stat("check.sock", dir_fd=self._dir_fd, follow_symlinks=False)
                    except FileNotFoundError:
                        node = None
                    if node is not None:
                        if stat.S_ISSOCK(node.st_mode) and (node.st_dev, node.st_ino) == self.identity:
                            os.unlink("check.sock", dir_fd=self._dir_fd)
                        else:
                            self._cleanup_ok = False
                    current = self.directory.lstat()
                    if stat.S_ISDIR(current.st_mode) and (current.st_dev, current.st_ino) == self._dir_identity:
                        os.rmdir(self.directory)
                    else:
                        self._cleanup_ok = False
                except OSError:
                    self._cleanup_ok = False
                finally:
                    os.close(self._dir_fd)
                    self._dir_fd = -1
            elif self._dir_identity is not None:
                try:
                    current = self.directory.lstat()
                    if stat.S_ISDIR(current.st_mode) and (current.st_dev, current.st_ino) == self._dir_identity:
                        os.rmdir(self.directory)
                    else:
                        self._cleanup_ok = False
                except FileNotFoundError:
                    pass
                except OSError:
                    self._cleanup_ok = False
            return stopped and self._cleanup_ok
