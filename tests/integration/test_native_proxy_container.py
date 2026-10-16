"""Actual Docker boundary with synthetic private upstream; no native login/model call."""

import hashlib
import json
import socket

from native_relay_support import client, docker, echo_gateway, relay_container
from panestria.sandbox.egress import EgressGateway


def test_actual_network_none_relay_transfers_only_through_the_mounted_private_socket(tmp_path, record_property):
    with echo_gateway(tmp_path / "echo") as (endpoint, _), relay_container(endpoint) as (identifier, actual):
        result = client(
            identifier,
            """
import socket,hashlib,json
body=b'PUBLIC_CONTAINER_RELAY_'*6000
with socket.create_connection(('127.0.0.1',18080),timeout=3) as peer:
 peer.settimeout(3);peer.sendall(body);peer.shutdown(socket.SHUT_WR);output=bytearray()
 while chunk:=peer.recv(16384):output.extend(chunk)
print(json.dumps({'size':len(output),'sha':hashlib.sha256(output).hexdigest()}))
""",
        )
        body = b"PUBLIC_CONTAINER_RELAY_" * 6000
        assert result == {"size": len(body), "sha": hashlib.sha256(body).hexdigest()}
        record_property(
            "scope", "actual nonroot/read-only/network-none Docker + pinned UDS identity; synthetic echo, no provider"
        )
        record_property("image_id", actual["Image"])


def test_actual_container_cannot_read_host_sentinel_write_mounts_or_inherit_provider_env(tmp_path, monkeypatch):
    sentinel = tmp_path / "unmounted-synthetic-credential"
    sentinel.write_text("SYNTHETIC_NOT_A_REAL_CREDENTIAL")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "SYNTHETIC_MUST_NOT_ENTER_CONTAINER")
    with echo_gateway(tmp_path / "echo") as (endpoint, _), relay_container(endpoint) as (identifier, _):
        result = client(
            identifier,
            """
import os,pathlib,json
denied=[]
for name in ('/runtime/native_proxy_relay.py','/gateway/unexpected-write'):
 try:
  with open(name,'wb') as file:file.write(b'synthetic')
 except OSError:denied.append(name)
print(json.dumps({'uid':os.getuid(),'sentinel':pathlib.Path("""
            + repr(str(sentinel))
            + """).exists(),
'unexpected_env':[k for k in os.environ if k.startswith(
 ('ANTHROPIC_','OPENAI_','CLAUDE_','PANESTRIA_DATABASE_URL','DBUS_'))],
'denied':denied,'cap_eff':next(line.strip() for line in pathlib.Path('/proc/self/status').read_text().splitlines()
 if line.startswith('CapEff:'))}))
""",
        )
        assert result["uid"] != 0 and not result["sentinel"] and result["unexpected_env"] == []
        assert set(result["denied"]) == {"/runtime/native_proxy_relay.py", "/gateway/unexpected-write"}
        assert result["cap_eff"].split()[1] == "0000000000000000"


def test_actual_namespace_blocks_host_loopback_and_direct_test_net_while_gateway_denies_unknown_target(tmp_path):
    with socket.socket() as host:
        host.bind(("127.0.0.1", 0))
        host.listen(1)
        port = host.getsockname()[1]
        with EgressGateway(tmp_path / "gateway", frozenset({"api.anthropic.com"})) as gateway:
            with relay_container(gateway.path) as (identifier, _):
                result = client(
                    identifier,
                    """
import socket,json
denied=[]
for address in [('127.0.0.1',"""
                    + str(port)
                    + """),('192.0.2.1',443)]:
 try:
  with socket.create_connection(address,timeout=0.3):pass
 except OSError:denied.append(address[0])
with socket.create_connection(('127.0.0.1',18080),timeout=2) as peer:
 peer.settimeout(2);peer.sendall(b'CONNECT forbidden.example:443 HTTP/1.1\\r\\n\\r\\n');reply=peer.recv(256)
print(json.dumps({'denied':denied,'gateway_denied':reply.startswith(b'HTTP/1.1 403')}))
""",
                )
                assert result == {"denied": ["127.0.0.1", "192.0.2.1"], "gateway_denied": True}
            assert gateway.server.audit and all(entry[1] == "DENIED" for entry in gateway.server.audit)


def test_actual_container_refuses_a_replaced_gateway_inode_and_stops_cleanly(tmp_path):
    with echo_gateway(tmp_path / "first") as (endpoint, first):
        with relay_container(endpoint) as (identifier, _):
            original = endpoint.stat().st_ino
            endpoint.unlink()
            with echo_gateway(tmp_path / "second") as (other, second):
                # Move the new socket pathname under the already-mounted directory;
                # the old listening socket remains open so its inode cannot be reused.
                other.rename(endpoint)
                assert endpoint.stat().st_ino != original
                result = client(
                    identifier,
                    """
import socket,json
with socket.create_connection(('127.0.0.1',18080),timeout=2) as peer:
 peer.settimeout(2);peer.sendall(b'PUBLIC_REPLACEMENT_TEST')
 try:closed=not peer.recv(1)
 except ConnectionResetError:closed=True
print(json.dumps({'closed':closed}))
""",
                )
                assert result["closed"] and first.accepted == second.accepted == 0
                endpoint.unlink()
            docker("kill", "--signal", "TERM", identifier)
            docker("wait", identifier, timeout=5)
            assert json.loads(docker("inspect", identifier))[0]["State"]["ExitCode"] == 0
