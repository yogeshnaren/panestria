"""DNS/transport fixtures, with actual Unix-socket gateway denial; no internet."""

import socket

import pytest

from panestria.sandbox.egress import EgressDenied, EgressGateway, _public_unicast, _verify_peer, resolve_destination

UNSAFE = (
    "224.0.0.1",
    "239.255.255.255",
    "ff0e::1",
    "ff02::1",
    "240.0.0.1",
    "0.0.0.0",
    "::",
    "127.0.0.1",
    "::1",
    "10.0.0.1",
    "172.16.0.1",
    "192.168.0.1",
    "169.254.169.254",
    "fe80::1",
    "100.64.0.1",
    "fc00::1",
    "fec0::1",
    "3fff::1",
    "3fff:fff::1",
    "2001:db8::1",
    "192.0.2.1",
    "198.51.100.1",
    "203.0.113.1",
    "::ffff:8.8.8.8",
    "::ffff:127.0.0.1",
    "2002:0808:0808::1",
    "2001:0:4136:e378:8000:63bf:3fff:fdd2",
    "2606:4700:4700::1111%eth0",
    "8.8.8.8%1",
    "garbage",
    "2130706433",
    "0177.0.0.1",
)
ALLOWED = frozenset({"api.anthropic.com"})


def answers(*addresses):
    return [
        (socket.AF_INET6 if ":" in value else socket.AF_INET, socket.SOCK_STREAM, 6, "", (value, 443))
        for value in addresses
    ]


@pytest.mark.parametrize("address", UNSAFE)
def test_unsafe_and_mixed_dns_answers_deny_before_returning_a_destination(monkeypatch, address):
    assert _public_unicast(address) is None
    for values in ((address,), ("104.18.0.1", address)):
        monkeypatch.setattr(socket, "getaddrinfo", lambda *args, values=values, **kwargs: answers(*values))
        with pytest.raises(EgressDenied, match="private_destination_denied"):
            resolve_destination("api.anthropic.com:443", ALLOWED)


@pytest.mark.parametrize("address", ["104.18.0.1", "1.1.1.1", "2606:4700:4700::1111", "2001:4860:4860::8888"])
def test_native_public_unicast_remains_pinned_with_one_dns_resolution(monkeypatch, address):
    calls = []

    def resolve(host, port, **kwargs):
        calls.append((host, port))
        return answers(address)

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    assert resolve_destination("api.anthropic.com:443", ALLOWED) == (address, 443)
    assert calls == [("api.anthropic.com", 443)]
    _verify_peer((address, 443), address, 443)


@pytest.mark.parametrize(
    "peer", [("224.0.0.1", 443), ("ff0e::1", 443), ("104.18.0.2", 443), ("104.18.0.1", 444), ("::ffff:104.18.0.1", 443)]
)
def test_connected_peer_must_be_exact_pinned_native_unicast(peer):
    with pytest.raises(EgressDenied, match="private_or_unpinned_peer_denied"):
        _verify_peer(peer, "104.18.0.1", 443)


def test_equivalent_ipv6_spelling_is_the_same_pinned_address():
    _verify_peer(("2606:4700:4700:0:0:0:0:1111", 443), "2606:4700:4700::1111", 443)


def test_numeric_ipv6_socket_scope_is_not_discarded(monkeypatch):
    address = "2606:4700:4700::1111"
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", (address, 443, 0, 2))],
    )
    with pytest.raises(EgressDenied, match="private_destination_denied"):
        resolve_destination("api.anthropic.com:443", ALLOWED)
    with pytest.raises(EgressDenied, match="private_or_unpinned_peer_denied"):
        _verify_peer((address, 443, 0, 2), address, 443)
    _verify_peer((address, 443, 0, 0), address, 443)


def test_actual_unix_gateway_never_calls_connector_for_multicast_or_scoped_dns(tmp_path, monkeypatch):
    current = ["224.0.0.1"]
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: answers(current[0]))
    connected = []

    def forbidden(*args, **kwargs):
        connected.append(True)
        raise AssertionError("unsafe destination reached connector")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    with EgressGateway(tmp_path / "gateway", ALLOWED) as gateway:
        for address in ("224.0.0.1", "ff0e::1", "2606:4700:4700::1111%eth0"):
            current[0] = address
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(2)
                client.connect(str(gateway.path))
                client.sendall(b"CONNECT api.anthropic.com:443 HTTP/1.1\r\n\r\n")
                assert client.recv(256).startswith(b"HTTP/1.1 403")
        assert not connected
        assert all(result == "DENIED" for _, result in gateway.server.audit)
