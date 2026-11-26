"""Run an app under the product uvicorn configuration on a real loopback socket.

Tests that care about transport behaviour (limits, deadlines, streaming) use
this instead of an in-process client, so they exercise the same parser,
protocol and middleware an owner's server does.
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import uvicorn

from panestria.api.local_protocol import LocalHttpProtocol
from panestria.api.serving import owned_socket, server_config


@contextmanager
def served(app: Any, *, http: type[LocalHttpProtocol] = LocalHttpProtocol) -> Iterator[int]:
    """Serve ``app`` on 127.0.0.1 with an ephemeral port; yield the port."""
    listener = owned_socket("127.0.0.1", 0)
    port = int(listener.getsockname()[1])
    server = uvicorn.Server(server_config(app, http=http))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline, "served_app_did_not_start"
            time.sleep(0.01)
        yield port
    finally:
        server.should_exit = True
        thread.join(10)
        listener.close()


def exchange(port: int, payload: bytes, *, shutdown_write: bool = False, timeout: float = 5) -> bytes:
    """Send raw bytes and read until the server closes the connection."""
    with socket.create_connection(("127.0.0.1", port), timeout=timeout) as sock:
        sock.sendall(payload)
        if shutdown_write:
            sock.shutdown(socket.SHUT_WR)
        chunks: list[bytes] = []
        while True:
            try:
                data = sock.recv(65536)
            except TimeoutError:
                break
            if not data:
                break
            chunks.append(data)
    return b"".join(chunks)
