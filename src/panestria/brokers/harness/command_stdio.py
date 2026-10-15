"""Internal stdio relay for a controller-bound private registered-check socket."""

from __future__ import annotations

import argparse
import json
import math
import os
import selectors
import socket
import sys
import time
from pathlib import Path

from panestria.brokers.harness.command_transport import (
    CommandTransportUnavailable,
    MessageFrames,
    peer_identity,
    private_endpoint,
)
from panestria.contracts.native_tools import MAX_PAYLOAD_BYTES, canonical_payload

_BUFFER_BYTES = 2 * (MAX_PAYLOAD_BYTES + 1)
_CHUNK_BYTES = 4096
_FRAME_SECONDS = 5.0


def relay(
    endpoint: Path,
    *,
    expected_device: int,
    expected_inode: int,
    expected_pid: int,
    lifetime_seconds: float = 120.0,
    input_fd: int = 0,
    output_fd: int = 1,
) -> None:
    """Forward bounded frames only; tool authority remains entirely in the controller."""
    if (
        any(type(value) is not int or value < 0 for value in (expected_device, expected_inode))
        or type(expected_pid) is not int
        or expected_pid <= 0
        or type(lifetime_seconds) not in (int, float)
        or not math.isfinite(lifetime_seconds)
        or not 0.1 <= lifetime_seconds <= 300
        or input_fd == output_fd
    ):
        raise CommandTransportUnavailable("invalid_shim_configuration")
    identity = (expected_device, expected_inode)
    if private_endpoint(endpoint) != identity:
        raise CommandTransportUnavailable("endpoint_identity_changed")
    deadline = time.monotonic() + lifetime_seconds
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(min(1.0, lifetime_seconds))
        connection.connect(str(endpoint))
        if peer_identity(connection) != (expected_pid, os.getuid()) or private_endpoint(endpoint) != identity:
            raise CommandTransportUnavailable("controller_identity_changed")
        connection.setblocking(False)
        original: dict[int, bool] = {}
        try:
            for fd in (input_fd, output_fd):
                original[fd] = os.get_blocking(fd)
                os.set_blocking(fd, False)
            _pump(connection, input_fd, output_fd, deadline)
        finally:
            for fd, blocking in original.items():
                os.set_blocking(fd, blocking)


def _pump(connection: socket.socket, input_fd: int, output_fd: int, deadline: float) -> None:
    inbound, outbound = bytearray(), bytearray()
    input_frames, output_frames = MessageFrames(), MessageFrames()
    input_partial: float | None = None
    output_partial: float | None = None
    input_eof = socket_eof = write_shutdown = False
    socket_fd = connection.fileno()
    with selectors.DefaultSelector() as selector:
        registered: dict[int, int] = {}
        while True:
            now = time.monotonic()
            if now >= deadline or any(
                stamp is not None and now - stamp >= _FRAME_SECONDS for stamp in (input_partial, output_partial)
            ):
                raise CommandTransportUnavailable("shim_deadline")
            if input_eof and not inbound and not write_shutdown and not socket_eof:
                connection.shutdown(socket.SHUT_WR)
                write_shutdown = True
            if socket_eof and not outbound:
                return
            desired: dict[int, int] = {}
            if not input_eof and not socket_eof and len(inbound) <= _BUFFER_BYTES - _CHUNK_BYTES:
                desired[input_fd] = selectors.EVENT_READ
            if not socket_eof:
                socket_events = 0
                if len(outbound) <= _BUFFER_BYTES - _CHUNK_BYTES:
                    socket_events |= selectors.EVENT_READ
                if inbound:
                    socket_events |= selectors.EVENT_WRITE
                if socket_events:
                    desired[socket_fd] = socket_events
            if outbound:
                desired[output_fd] = selectors.EVENT_WRITE
            for fd in registered.keys() - desired.keys():
                selector.unregister(fd)
            for fd, flags in desired.items():
                if fd not in registered:
                    selector.register(fd, flags)
                elif registered[fd] != flags:
                    selector.modify(fd, flags)
            registered = desired
            for key, flags in selector.select(timeout=min(0.1, deadline - now)):
                fd = key.fd
                try:
                    if fd == output_fd:
                        del outbound[: os.write(output_fd, outbound)]
                    elif fd == input_fd:
                        data = os.read(input_fd, _CHUNK_BYTES)
                        if not data:
                            if input_frames.pending:
                                raise CommandTransportUnavailable("incomplete_input_frame")
                            input_eof = True
                        else:
                            for frame in input_frames.feed(data):
                                if len(inbound) + len(frame) + 1 > _BUFFER_BYTES:
                                    raise CommandTransportUnavailable("shim_buffer_limit")
                                inbound.extend(frame + b"\n")
                            input_partial = (input_partial or now) if input_frames.pending else None
                    else:
                        if flags & selectors.EVENT_WRITE:
                            del inbound[: connection.send(inbound)]
                        if flags & selectors.EVENT_READ:
                            data = connection.recv(_CHUNK_BYTES)
                            if not data:
                                if output_frames.pending or inbound:
                                    raise CommandTransportUnavailable("incomplete_controller_stream")
                                socket_eof = True
                            else:
                                for frame in output_frames.feed(data):
                                    body = json.loads(canonical_payload(frame.decode("utf-8")))
                                    if body.get("jsonrpc") != "2.0":
                                        raise CommandTransportUnavailable("invalid_controller_frame")
                                    if len(outbound) + len(frame) + 1 > _BUFFER_BYTES:
                                        raise CommandTransportUnavailable("shim_buffer_limit")
                                    outbound.extend(frame + b"\n")
                                output_partial = (output_partial or now) if output_frames.pending else None
                except BlockingIOError:
                    continue
                if len(inbound) > _BUFFER_BYTES or len(outbound) > _BUFFER_BYTES:
                    raise CommandTransportUnavailable("shim_buffer_limit")


def main() -> None:
    parser = argparse.ArgumentParser(description="Internal Panestria registered-check stdio relay")
    parser.add_argument("--endpoint", type=Path, required=True)
    parser.add_argument("--device", type=int, required=True)
    parser.add_argument("--inode", type=int, required=True)
    parser.add_argument("--controller-pid", type=int, required=True)
    parser.add_argument("--lifetime-seconds", type=float, default=120.0)
    args = parser.parse_args()
    try:
        relay(
            args.endpoint,
            expected_device=args.device,
            expected_inode=args.inode,
            expected_pid=args.controller_pid,
            lifetime_seconds=args.lifetime_seconds,
        )
    except (OSError, ValueError, RuntimeError, RecursionError):
        print("panestria_check_transport_unavailable", file=sys.stderr)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
