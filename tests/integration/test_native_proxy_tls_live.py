"""Opted-in public TLS channel only; no credentials, native CLI or model inference."""

import os

import pytest

from native_relay_support import client, relay_container
from panestria.sandbox.egress import EgressGateway


@pytest.mark.live
def test_actual_provider_tls_head_crosses_only_private_gateway_from_network_none(tmp_path, record_property):
    if os.environ.get("PANESTRIA_RUN_NATIVE_RELAY_TLS") != "1":
        pytest.skip("explicit public TLS channel opt-in absent")
    with EgressGateway(tmp_path / "gateway", frozenset({"api.anthropic.com"})) as gateway:
        with relay_container(gateway.path) as (identifier, actual):
            result = client(
                identifier,
                """
import socket,ssl,json
with socket.create_connection(('127.0.0.1',18080),timeout=10) as peer:
 peer.settimeout(10);peer.sendall(b'CONNECT api.anthropic.com:443 HTTP/1.1\\r\\n\\r\\n');header=bytearray()
 while not header.endswith(b'\\r\\n\\r\\n'):
  part=peer.recv(1)
  if not part or len(header)>8192:raise RuntimeError('public_gateway_unavailable')
  header.extend(part)
 assert header.startswith(b'HTTP/1.1 200')
 with ssl.create_default_context().wrap_socket(peer,server_hostname='api.anthropic.com') as secure:
  secure.sendall(b'HEAD / HTTP/1.1\\r\\nHost: api.anthropic.com\\r\\nConnection: close\\r\\n\\r\\n')
  reply=secure.recv(1024)
print(json.dumps({'tls':True,'http':reply.startswith(b'HTTP/'),'hostname_verified':True}))
""",
            )
            assert result == {"tls": True, "http": True, "hostname_verified": True}
            record_property("image_id", actual["Image"])
        assert ("api.anthropic.com:443", "ALLOWED") in gateway.server.audit
        record_property(
            "scope",
            "actual TLS HEAD via Docker network-none/loopback/private UDS/host gateway; "
            "no auth/inference/native certificate",
        )
