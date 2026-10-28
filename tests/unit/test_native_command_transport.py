"""Actual private sockets and subprocess pipes; controller callbacks remain fixtures."""

import json
import os
import selectors
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

import panestria.brokers.harness.command_stdio as shim
import panestria.brokers.harness.command_transport as transport
from panestria.brokers.harness.command_protocol import PreparedCheck, RegisteredCheckSession
from panestria.brokers.harness.command_transport import (
    CommandTransportUnavailable,
    MessageFrames,
    RegisteredCheckSocket,
    private_endpoint,
)
from panestria.contracts.native_command import RegisteredCheckReceipt
from panestria.contracts.native_tools import MAX_PAYLOAD_BYTES


def frame(method, identity=None, **params):
    body = {"jsonrpc": "2.0", "method": method, "params": params}
    if identity is not None:
        body["id"] = identity
    return json.dumps(body).encode() + b"\n"


INIT = frame(
    "initialize", "init", protocolVersion="2025-06-18", capabilities={}, clientInfo={"name": "fixture", "version": "1"}
)
READY = frame("notifications/initialized")
CALL = frame(
    "tools/call",
    "check",
    name="run_registered_check",
    arguments={"command_ref": "unit-check", "candidate_ref": "candidate:fixed"},
)
RECEIPT = RegisteredCheckReceipt(outcome="COMPLETED", exit_code=0, report_sha256="ab" * 32)


def session(executor=None, **kwargs):
    return RegisteredCheckSession(("unit-check",), "candidate:fixed", executor or (lambda *_: RECEIPT), **kwargs)


def line(fd, timeout=3):
    data = bytearray()
    with selectors.DefaultSelector() as selector:
        selector.register(fd, selectors.EVENT_READ)
        deadline = time.monotonic() + timeout
        while b"\n" not in data:
            assert selector.select(max(0, deadline - time.monotonic())), "fixture reply deadline"
            chunk = os.read(fd, 1)
            assert chunk, "unexpected fixture stream EOF"
            data.extend(chunk)
    return json.loads(data)


def until(predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline
        time.sleep(0.01)


@pytest.fixture
def root():
    # Linux AF_UNIX has a short path limit: use an owned short actual temporary root.
    with tempfile.TemporaryDirectory(prefix="pns-mcp-", dir="/tmp") as directory:
        yield Path(directory)


def connect(server):
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(3)
    client.connect(str(server.path))
    return client


def start_shim(server, *, identity=None, pid=None, lifetime=2):
    dev, ino = identity or server.identity
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "panestria.brokers.harness.command_stdio",
            "--endpoint",
            str(server.path),
            "--device",
            str(dev),
            "--inode",
            str(ino),
            "--controller-pid",
            str(pid or server.pid),
            "--lifetime-seconds",
            str(lifetime),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src")},
        start_new_session=True,
    )


def stop_child(child):
    if child.poll() is None:
        child.kill()
    child.wait(timeout=3)
    for pipe in (child.stdin, child.stdout, child.stderr):
        pipe.close()


def test_frames_preserve_complete_bytes_and_split_utf8():
    frames = MessageFrames()
    assert frames.feed(b'{"x":"\xc3') == []
    assert frames.feed(b'\xa9"}\n{}\nrest') == [b'{"x":"\xc3\xa9"}', b"{}"]
    assert frames.pending == b"rest"


@pytest.mark.parametrize(
    "data", [b"\n", b"\xff\n", b"x" * (MAX_PAYLOAD_BYTES + 1), b"x" * (MAX_PAYLOAD_BYTES + 1) + b"\n"]
)
def test_frames_reject_invalid_or_oversized(data):
    with pytest.raises(CommandTransportUnavailable):
        MessageFrames().feed(data)


def test_wire_order_cached_completion_private_modes_and_owned_cleanup(root):
    calls = []
    server = RegisteredCheckSocket(root / "attempt", session(lambda *args: calls.append(args) or RECEIPT))
    with server, connect(server) as client:
        assert stat.S_IMODE(server.directory.stat().st_mode) == 0o700
        assert stat.S_IMODE(server.path.stat().st_mode) == 0o600
        assert private_endpoint(server.path) == server.identity
        assert transport.peer_identity(client) == (os.getpid(), os.getuid())
        # All lifecycle messages arrive in one write; acceptance must remain in wire order.
        client.sendall(INIT + READY + frame("tools/list", "list"))
        assert line(client.fileno())["id"] == "init"
        assert line(client.fileno())["result"]["tools"][0]["name"] == "run_registered_check"
        client.sendall(CALL)
        result = line(client.fileno())
        assert result["result"]["structuredContent"]["outcome"] == "COMPLETED"
        client.sendall(CALL)
        assert line(client.fileno()) == result
        assert len(calls) == 1
    assert server.session.closed and not server.directory.exists()


def test_cancel_before_worker_dispatch_never_calls_executor():
    calls = []
    state = session(lambda *args: calls.append(args) or RECEIPT)
    state.handle(INIT.rstrip(b"\n"))
    state.handle(READY.rstrip(b"\n"))
    operation = state.prepare(CALL.rstrip(b"\n"))
    assert isinstance(operation, PreparedCheck)
    state.prepare(frame("notifications/cancelled", requestId="check").rstrip(b"\n"))
    assert state.run(operation) is None and not calls
    assert b"invalid_or_consumed_dispatch" in state.run(operation)


def test_forged_dispatch_is_not_authority():
    calls = []
    state = session(lambda *args: calls.append(args) or RECEIPT)
    state.handle(INIT.rstrip())
    state.handle(READY.rstrip())
    operation = state.prepare(CALL.rstrip())
    forged = PreparedCheck(operation.identity, operation.key, operation.digest, operation.command_ref, operation.cancel)
    assert b"invalid_or_consumed_dispatch" in state.run(forged) and not calls
    assert json.loads(state.run(operation))["result"]["structuredContent"]["outcome"] == "COMPLETED"
    assert len(calls) == 1


def test_cancellation_remains_responsive_during_callback(root):
    entered, cancelled, release = threading.Event(), threading.Event(), threading.Event()

    def execute(_command, _candidate, signal):
        entered.set()
        if signal.wait(2):
            cancelled.set()
        release.wait(2)
        return RECEIPT

    server = RegisteredCheckSocket(root / "attempt", session(execute))
    try:
        with server, connect(server) as client:
            client.sendall(INIT + READY)
            line(client.fileno())
            client.sendall(CALL)
            assert entered.wait(2)
            client.sendall(frame("notifications/cancelled", requestId="check") + frame("ping", "ping"))
            assert cancelled.wait(2)
            assert line(client.fileno()) == {"jsonrpc": "2.0", "id": "ping", "result": {}}
            release.set()
    finally:
        release.set()
        server.close()


def test_peer_eof_requests_callback_cancellation(root):
    entered, cancelled = threading.Event(), threading.Event()

    def execute(_command, _candidate, signal):
        entered.set()
        if signal.wait(2):
            cancelled.set()
        return RegisteredCheckReceipt(outcome="CANCELLED")

    with RegisteredCheckSocket(root / "attempt", session(execute)) as server:
        with connect(server) as client:
            client.sendall(INIT + READY)
            line(client.fileno())
            client.sendall(CALL)
            assert entered.wait(2)
        assert cancelled.wait(2)
        until(lambda: server.session.closed)
        assert server.reason == "peer_eof"


def test_uncooperative_callback_reports_unconfirmed_shutdown(root, monkeypatch):
    monkeypatch.setattr(transport, "_SHUTDOWN_SECONDS", 0.05)
    entered, release = threading.Event(), threading.Event()

    def execute(*_):
        entered.set()
        release.wait(3)
        return RECEIPT

    server = RegisteredCheckSocket(root / "attempt", session(execute))
    server.start()
    try:
        with connect(server) as client:
            client.sendall(INIT + READY)
            line(client.fileno())
            client.sendall(CALL)
            assert entered.wait(2)
            assert server.close() is False
            assert server.session.closed
            assert not server.directory.exists()
    finally:
        release.set()
        until(lambda: not any(t.is_alive() for t in server._threads))
        assert server.close()


def test_transport_lifetime_without_peer_and_single_connection(root):
    with RegisteredCheckSocket(root / "expired", session(), lifetime_seconds=0.1) as server:
        until(lambda: server.session.closed)
        assert server.reason == "transport_expired"
    with RegisteredCheckSocket(root / "single", session()) as server, connect(server) as client:
        client.sendall(INIT)
        line(client.fileno())
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as another:
            with pytest.raises(OSError):
                another.connect(str(server.path))


@pytest.mark.parametrize(
    "data",
    [b"PRIVATE_SENTINEL", b"x" * (MAX_PAYLOAD_BYTES + 1), b"\xff\n", b"\n"],
    ids=["unterminated", "oversize", "invalid-utf8", "empty-frame"],
)
def test_bad_or_partial_frames_close_private_session(root, monkeypatch, data):
    monkeypatch.setattr(transport, "_FRAME_SECONDS", 0.05)
    with RegisteredCheckSocket(root / "attempt", session()) as server, connect(server) as client:
        client.sendall(data)
        until(lambda: server.session.closed)
        assert "PRIVATE_SENTINEL" not in server.reason


@pytest.mark.parametrize("kind", ["directory", "file", "symlink"])
def test_existing_path_never_removed(root, kind):
    path = root / "attempt"
    if kind == "directory":
        path.mkdir()
    elif kind == "file":
        path.write_text("owner data")
    else:
        path.symlink_to(root)
    with pytest.raises(CommandTransportUnavailable):
        RegisteredCheckSocket(path, session()).start()
    assert path.exists() or path.is_symlink()


def test_replacement_socket_and_unrelated_files_are_preserved(root):
    server = RegisteredCheckSocket(root / "attempt", session())
    server.start()
    server.path.unlink()
    server.path.write_text("owner replacement")
    (server.directory / "owner.txt").write_text("owner data")
    assert server.close() is False
    assert server.path.read_text() == "owner replacement"
    assert (server.directory / "owner.txt").read_text() == "owner data"


def test_replacement_directory_is_preserved(root):
    server = RegisteredCheckSocket(root / "attempt", session())
    server.start()
    moved = root / "moved"
    server.directory.rename(moved)
    server.directory.mkdir()
    (server.directory / "owner.txt").write_text("owner data")
    assert server.close() is False
    assert (server.directory / "owner.txt").read_text() == "owner data"
    assert not (moved / "check.sock").exists()


def test_closed_session_has_no_transport(root):
    state = session()
    state.close()
    with pytest.raises(CommandTransportUnavailable):
        RegisteredCheckSocket(root / "attempt", state).start()
    assert not (root / "attempt").exists()


@pytest.mark.parametrize("lifetime", [True, 0, 301, float("nan"), float("inf")])
def test_invalid_transport_lifetime_does_not_create_paths(root, lifetime):
    with pytest.raises(CommandTransportUnavailable):
        RegisteredCheckSocket(root / "attempt", session(), lifetime_seconds=lifetime)
    assert not (root / "attempt").exists()


@pytest.mark.parametrize("target", ["mode", "parent_mode", "symlink", "not_socket"])
def test_endpoint_rejects_unsafe_path(root, target):
    with RegisteredCheckSocket(root / "attempt", session()) as server:
        path = server.path
        if target == "mode":
            path.chmod(0o666)
        elif target == "parent_mode":
            path.parent.chmod(0o755)
        elif target == "symlink":
            path = root / "link"
            path.symlink_to(server.path)
        else:
            path = root / "ordinary"
            path.write_text("private")
        try:
            with pytest.raises(CommandTransportUnavailable):
                private_endpoint(path)
        finally:
            server.path.chmod(0o600)
            server.directory.chmod(0o700)


def test_actual_stdio_child_roundtrip_and_no_execution_replay(root):
    calls = []
    with RegisteredCheckSocket(root / "attempt", session(lambda *args: calls.append(args) or RECEIPT)) as server:
        child = start_shim(server)
        try:
            child.stdin.write(INIT + READY + frame("tools/list", "list"))
            child.stdin.flush()
            assert line(child.stdout.fileno())["id"] == "init"
            assert line(child.stdout.fileno())["id"] == "list"
            child.stdin.write(CALL)
            child.stdin.flush()
            response = line(child.stdout.fileno())
            assert response["result"]["structuredContent"]["report_sha256"] == "ab" * 32
            child.stdin.write(CALL)
            child.stdin.flush()
            assert line(child.stdout.fileno()) == response and len(calls) == 1
            child.stdin.close()
            child.wait(timeout=3)
            assert child.returncode == 0 and child.stderr.read() == b""
        finally:
            stop_child(child)


@pytest.mark.parametrize("mismatch", ["inode", "pid"])
def test_stdio_child_denies_controller_identity_mismatch(root, mismatch):
    calls = []
    with RegisteredCheckSocket(root / "attempt", session(lambda *args: calls.append(args) or RECEIPT)) as server:
        identity = (server.identity[0], server.identity[1] + 1) if mismatch == "inode" else None
        child = start_shim(server, identity=identity, pid=server.pid + 1 if mismatch == "pid" else None)
        try:
            output, error = child.communicate(INIT, timeout=3)
            assert child.returncode == 2 and output == b""
            assert error == b"panestria_check_transport_unavailable\n" and not calls
        finally:
            stop_child(child)


@pytest.mark.parametrize(
    "data",
    [b"PRIVATE_SENTINEL", b"\xff\n", b"x" * (MAX_PAYLOAD_BYTES + 1) + b"\n"],
    ids=["unterminated", "invalid-utf8", "oversize"],
)
def test_stdio_child_bad_input_is_bounded_and_redacted(root, data):
    with RegisteredCheckSocket(root / "attempt", session()) as server:
        child = start_shim(server)
        try:
            output, error = child.communicate(data, timeout=3)
            assert child.returncode == 2 and output == b""
            assert error == b"panestria_check_transport_unavailable\n"
        finally:
            stop_child(child)


def test_stdio_restores_actual_pipe_flags(root):
    input_read, input_write = os.pipe()
    output_read, output_write = os.pipe()
    try:
        os.close(input_write)
        with RegisteredCheckSocket(root / "attempt", session()) as server:
            shim.relay(
                server.path,
                expected_device=server.identity[0],
                expected_inode=server.identity[1],
                expected_pid=server.pid,
                input_fd=input_read,
                output_fd=output_write,
            )
        assert os.get_blocking(input_read) and os.get_blocking(output_write)
    finally:
        for fd in (input_read, output_read, output_write):
            os.close(fd)


def test_closed_before_run_never_dispatches():
    calls = []
    state = session(lambda *args: calls.append(args) or RECEIPT)
    state.handle(INIT.rstrip())
    state.handle(READY.rstrip())
    operation = state.prepare(CALL.rstrip())
    state.close()
    assert state.run(operation) is None and not calls


def test_socket_uid_mismatch_denied_before_frame_dispatch(root, monkeypatch):
    calls = []
    monkeypatch.setattr(transport, "peer_identity", lambda _connection: (os.getpid(), os.getuid() + 1))
    with RegisteredCheckSocket(root / "attempt", session(lambda *args: calls.append(args) or RECEIPT)) as server:
        with connect(server):
            until(lambda: server.session.closed)
        assert not calls
    # This injects the UID predicate, not a claim of execution as another OS user.


def test_failure_opening_owned_directory_cleans_only_its_empty_path(root, monkeypatch):
    original = transport.os.open

    def failing(path, *args, **kwargs):
        if path == root / "attempt":
            raise OSError("PRIVATE_SENTINEL")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(transport.os, "open", failing)
    with pytest.raises(CommandTransportUnavailable, match="^transport_start_unavailable$"):
        RegisteredCheckSocket(root / "attempt", session()).start()
    assert not (root / "attempt").exists()


def test_stdio_partial_input_expires_without_eof(root):
    with RegisteredCheckSocket(root / "attempt", session()) as server:
        child = start_shim(server, lifetime=0.15)
        try:
            child.stdin.write(b"PRIVATE_SENTINEL")
            child.stdin.flush()
            child.wait(timeout=3)
            assert child.returncode == 2 and child.stdout.read() == b""
            assert child.stderr.read() == b"panestria_check_transport_unavailable\n"
        finally:
            stop_child(child)


def test_stdio_no_reader_pressure_finishes_by_deadline(root):
    # Fill actual stdout/socket buffers without a reading consumer. No thread or
    # blocking write may retain the shim beyond its total deadline.
    commands = tuple("check-" + str(index) + "-" + "a" * 48 for index in range(16))
    state = RegisteredCheckSession(commands, "candidate:fixed", lambda *_: RECEIPT, max_frames=128)
    with RegisteredCheckSocket(root / "attempt", state) as server:
        child = start_shim(server, lifetime=0.3)
        try:
            child.stdin.write(INIT + READY + b"".join(frame("tools/list", str(i)) for i in range(120)))
            child.stdin.flush()
            child.wait(timeout=3)
            assert child.returncode == 2
            assert child.stderr.read() == b"panestria_check_transport_unavailable\n"
        finally:
            stop_child(child)


@pytest.mark.parametrize("reply", [b"PRIVATE_SENTINEL\n", b'{"jsonrpc":"1.0"}\n', b"\xff\n", b'{"jsonrpc":"2.0"'])
def test_shim_never_emits_invalid_controller_frames(root, reply):
    directory = root / "raw"
    directory.mkdir(mode=0o700)
    endpoint = directory / "check.sock"
    release = threading.Event()

    def serve(listener):
        with listener.accept()[0] as client:
            client.sendall(reply)
            if not reply.endswith(b"\n"):
                client.shutdown(socket.SHUT_WR)
            release.wait(2)

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind(str(endpoint))
        endpoint.chmod(0o600)
        listener.listen(1)
        worker = threading.Thread(target=serve, args=(listener,), daemon=True)
        worker.start()
        input_read, input_write = os.pipe()
        output_read, output_write = os.pipe()
        try:
            with pytest.raises((ValueError, OSError)):
                shim.relay(
                    endpoint,
                    expected_device=endpoint.stat().st_dev,
                    expected_inode=endpoint.stat().st_ino,
                    expected_pid=os.getpid(),
                    input_fd=input_read,
                    output_fd=output_write,
                    lifetime_seconds=0.5,
                )
            os.set_blocking(output_read, False)
            with pytest.raises(BlockingIOError):
                os.read(output_read, 1)
            assert os.get_blocking(input_read) and os.get_blocking(output_write)
        finally:
            release.set()
            worker.join(timeout=3)
            for fd in (input_read, input_write, output_read, output_write):
                os.close(fd)
