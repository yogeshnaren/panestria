"""Actual local socket behavior; synthetic peer, no native program or public network."""

import hashlib
import os
import socket
import struct
import subprocess
import sys
import threading
import time
from contextlib import contextmanager

import pytest

from native_relay_support import PROGRAM, echo_gateway
from panestria.sandbox.native_proxy_relay import RelayBudget, RelayServer, SocketIdentity


@contextmanager
def server_for(endpoint, **kwargs):
    info = endpoint.stat()
    with RelayServer(("127.0.0.1", 0), SocketIdentity(endpoint, info.st_dev, info.st_ino), **kwargs) as server:

        def serve():
            try:
                while not server.budget.closing.is_set() and time.monotonic() < server.deadline:
                    server.handle_request()
            finally:
                server.budget.stop()

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        try:
            yield server
        finally:
            server.budget.stop()
            thread.join(timeout=3)


def test_large_bidirectional_half_close_is_drained_without_losing_the_last_buffer(tmp_path):
    payload = b"PUBLIC_RELAY_FIXTURE_" * 10000
    with echo_gateway(tmp_path / "echo") as (endpoint, _), server_for(endpoint) as server:
        with socket.create_connection(server.server_address, timeout=3) as peer:
            peer.settimeout(3)
            peer.sendall(payload)
            peer.shutdown(socket.SHUT_WR)
            received = bytearray()
            while part := peer.recv(4096):
                received.extend(part)
                time.sleep(0.0001)
        assert len(received) == len(payload) and hashlib.sha256(received).digest() == hashlib.sha256(payload).digest()
        assert server.budget.remaining == 16 * 1024 * 1024 - 2 * len(payload)


@pytest.mark.parametrize("mutation", ["inode", "device", "socket-mode", "directory-mode", "symlink", "regular-file"])
def test_endpoint_type_identity_private_modes_and_aliases_are_not_trusted(tmp_path, mutation):
    with echo_gateway(tmp_path / "echo") as (endpoint, _):
        info = endpoint.stat()
        path = endpoint
        device, inode = info.st_dev, info.st_ino
        if mutation == "inode":
            inode += 1
        elif mutation == "device":
            device += 1
        elif mutation == "socket-mode":
            endpoint.chmod(0o666)
        elif mutation == "directory-mode":
            endpoint.parent.chmod(0o755)
        elif mutation == "symlink":
            path = endpoint.parent / "alias"
            path.symlink_to(endpoint)
        elif mutation == "regular-file":
            path = endpoint.parent / "regular"
            path.write_text("synthetic")
        with pytest.raises((ValueError, OSError)):
            SocketIdentity(path, device, inode).check()


@pytest.mark.parametrize(
    "field,value", [("byte_cap", 0), ("byte_cap", True), ("byte_cap", 16777217), ("connections", 17), ("live", 3)]
)
def test_relay_resource_budgets_cannot_be_widened(field, value):
    with pytest.raises(ValueError):
        RelayBudget(**{field: value})


def test_global_byte_limit_stops_without_replenishment_and_deadline_closes_idle_peer(tmp_path):
    with echo_gateway(tmp_path / "echo") as (endpoint, _):
        with server_for(endpoint, budget=RelayBudget(byte_cap=1024)) as server:
            with socket.create_connection(server.server_address, timeout=2) as peer:
                peer.settimeout(2)
                peer.sendall(b"x" * 2048)
                peer.shutdown(socket.SHUT_WR)
                try:
                    data = peer.recv(4096)
                except ConnectionResetError:
                    data = b""
                assert not data and server.budget.remaining == 0
        with server_for(endpoint, lifetime_seconds=0.3) as server:
            with socket.create_connection(server.server_address, timeout=2) as peer:
                peer.settimeout(2)
                assert peer.recv(1) == b""
            assert server.budget.closing.wait(1)


def test_non_loopback_listener_is_rejected_before_accepting_clients(tmp_path):
    with echo_gateway(tmp_path / "echo") as (endpoint, _):
        info = endpoint.stat()
        with pytest.raises(ValueError, match="invalid_native_proxy_listener"):
            RelayServer(("0.0.0.0", 0), SocketIdentity(endpoint, info.st_dev, info.st_ino))


def test_cli_cannot_fall_back_to_a_host_with_external_network_interfaces():
    if {name for _index, name in socket.if_nameindex()} == {"lo"}:
        pytest.skip("already loopback-only namespace; host-interface refusal not exercised")
    result = subprocess.run([sys.executable, "-I", str(PROGRAM), "1", "1"], capture_output=True, timeout=3)
    assert result.returncode != 0 and result.stdout == b""
    assert b"native_proxy_network_unavailable" in result.stderr


def test_injected_wrong_peer_uid_is_closed_without_forwarding(tmp_path, monkeypatch):
    with echo_gateway(tmp_path / "echo") as (endpoint, upstream):
        info = endpoint.stat()

        class InjectedPeer:
            closed = False

            def settimeout(self, value):
                pass

            def connect(self, path):
                assert path == str(endpoint)

            def getsockopt(self, *args):
                return struct.pack("3i", 123, os.geteuid() + 1, os.getegid())

            def close(self):
                self.closed = True

        peer = InjectedPeer()
        with monkeypatch.context() as patch:
            patch.setattr(socket, "socket", lambda *_a, **_kw: peer)
            with pytest.raises(ValueError, match="native_proxy_peer_unconfirmed"):
                SocketIdentity(endpoint, info.st_dev, info.st_ino).connect()
        assert peer.closed and upstream.accepted == 0


def test_actual_socket_concurrency_and_attempt_caps_close_only_owned_channels(tmp_path):
    with echo_gateway(tmp_path / "echo") as (endpoint, upstream):
        with server_for(endpoint, budget=RelayBudget(connections=3)) as server:
            with socket.create_connection(server.server_address, timeout=2) as first:
                with socket.create_connection(server.server_address, timeout=2) as second:
                    deadline = time.monotonic() + 2
                    while (len(server.budget.sockets) < 4 or upstream.accepted < 2) and time.monotonic() < deadline:
                        time.sleep(0.005)
                    assert len(server.budget.sockets) == 4
                    with socket.create_connection(server.server_address, timeout=2) as third:
                        third.settimeout(2)
                        assert third.recv(1) == b""
                    assert upstream.accepted == 2
                    with socket.create_connection(server.server_address, timeout=2) as fourth:
                        fourth.settimeout(2)
                        assert fourth.recv(1) == b""
                    assert server.budget.closing.wait(1)
                    first.settimeout(2)
                    second.settimeout(2)
                    assert first.recv(1) == second.recv(1) == b""
