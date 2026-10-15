"""Protocol/SSRF fixtures inject DNS and TLS; they do not certify external TLS."""

import hashlib
import io
import socket
import ssl
import threading
import time

import pytest

import panestria.brokers.research.fetch as module
from panestria.brokers.research.fetch import FetchDenied, PublicHttpsFetcher, https_target
from panestria.contracts.research import ResearchLimits


def limits(**kwargs):
    return ResearchLimits(max_source_bytes=64, max_total_bytes=64, **kwargs)


def answer(ip="93.184.216.34"):
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, 443))]


class InjectedWire:
    def __init__(self, response):
        self.response = io.BytesIO(response)
        self.sent = []
        self.connected = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True

    def settimeout(self, value):
        assert 0 < value <= 5

    def connect(self, address):
        self.connected.append(address)

    def getpeername(self):
        return ("93.184.216.34", 443)

    def getpeercert(self, **_):
        return b"EXPLICIT_SYNTHETIC_CERT_NOT_TLS_PROOF"

    def sendall(self, data):
        self.sent.append(data)

    def recv_into(self, buffer):
        return self.response.readinto(buffer)


@pytest.fixture
def wire(monkeypatch):
    created = []
    responses = []
    sni = []

    def factory(*_):
        result = InjectedWire(responses.pop(0))
        created.append(result)
        return result

    class Context:
        check_hostname = True
        verify_mode = ssl.CERT_REQUIRED

        def set_alpn_protocols(self, value):
            assert value == ["http/1.1"]

        def wrap_socket(self, raw, *, server_hostname):
            sni.append(server_hostname)
            return raw

    monkeypatch.setattr(module.socket, "getaddrinfo", lambda *_a, **_k: answer())
    monkeypatch.setattr(module.socket, "socket", factory)
    monkeypatch.setattr(module.ssl, "create_default_context", Context)
    return responses, created, sni


@pytest.mark.parametrize(
    "url",
    [
        "http://example.org/",
        "https://a:b@example.org/",
        "https://example.org/#fragment",
        "https://example.org:444/",
        "https://example.org/\r\nPRIVATE",
        "https://example.org\\evil/",
        "https://[fe80::1%25eth0]/",
        "https://localhost/",
        "https://example..org/",
        "https://-bad.example/",
        "https://example.org:0/",
        "https://example.org/" + "x" * 2048,
    ],
)
def test_unsafe_url_syntax_never_selects_target(url):
    with pytest.raises(FetchDenied, match="^url_denied$"):
        https_target(url)


def test_idna_unicode_paths_are_encoded_without_changing_query_delimiters():
    target = https_target("https://bücher.example/path/é?q=é%20x")
    assert target.host == "xn--bcher-kva.example"
    assert target.resource == "/path/%C3%A9?q=%C3%A9%20x"
    assert "q=" not in repr(target)


@pytest.mark.parametrize(
    "ip", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "192.168.1.1", "0.0.0.0", "224.0.0.1", "255.255.255.255"]
)
def test_private_special_or_mixed_dns_never_connects(wire, monkeypatch, ip):
    responses, created, _ = wire
    monkeypatch.setattr(module.socket, "getaddrinfo", lambda *_a, **_k: answer() + answer(ip))
    result = PublicHttpsFetcher().fetch("https://example.org/PRIVATE_QUERY", limits())
    assert result.reason == "private_destination_denied" and result.outcome == "ERROR" and created == []
    assert "PRIVATE_QUERY" not in repr(result)


@pytest.mark.parametrize(
    "address",
    [
        ("ff0e::1", 443, 0, 0),
        ("fec0::1", 443, 0, 0),
        ("3fff::1", 443, 0, 0),
        ("::ffff:93.184.216.34", 443, 0, 0),
        ("2606:4700::1111", 443, 0, 9),
    ],
)
def test_ipv6_unsafe_answers_or_scope_denied(wire, monkeypatch, address):
    monkeypatch.setattr(
        module.socket,
        "getaddrinfo",
        lambda *_a, **_k: [(socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", address)],
    )
    result = PublicHttpsFetcher().fetch("https://example.org/", limits())
    assert result.reason == "private_destination_denied" and not wire[1]


def test_fixed_request_pinned_numeric_peer_sni_and_exact_retained_bytes(wire):
    responses, created, sni = wire
    responses.append(
        b"HTTP/1.1 200 OK\r\nContent-Length: 6\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nh\xc3\xa9llo"
    )
    result = PublicHttpsFetcher().fetch("https://example.org/path?q=public", limits())
    assert result.outcome == "COMPLETE" and result.reason == "retained_bytes_only" and result.body == b"h\xc3\xa9llo"
    assert result.retained_sha256 == hashlib.sha256(result.body).hexdigest()
    assert created[0].connected == [("93.184.216.34", 443)] and sni == ["example.org"] and created[0].closed
    sent = created[0].sent[0]
    assert b"Host: example.org\r\n" in sent and b"Accept-Encoding: identity" in sent
    assert b"Authorization" not in sent and b"Cookie" not in sent and b"Proxy" not in sent


@pytest.mark.parametrize("framing", [b"Transfer-Encoding: chunked\r\n\r\n3\r\nabc\r\n0\r\n\r\n", b"\r\nabc"])
def test_chunked_and_eof_body_preserve_bytes(wire, framing):
    wire[0].append(b"HTTP/1.1 200 OK\r\n" + framing)
    assert PublicHttpsFetcher().fetch("https://example.org/", limits()).body == b"abc"


@pytest.mark.parametrize(
    "headers",
    [
        b"Content-Length: 1000\r\n",
        b"Content-Length: 2\r\nContent-Length: 2\r\n",
        b"Transfer-Encoding: chunked\r\nContent-Length: 2\r\n",
        b"Content-Encoding: gzip\r\n",
        b"Transfer-Encoding: gzip\r\n",
        b"Content-Length: -1\r\n",
    ],
)
def test_oversize_ambiguous_or_encoded_body_never_complete(wire, headers):
    wire[0].append(b"HTTP/1.1 200 OK\r\n" + headers + b"\r\nxx")
    result = PublicHttpsFetcher().fetch("https://example.org/", limits())
    assert result.outcome == "ERROR" and result.body == b"" and wire[1][0].closed


def test_unknown_length_truncates_retained_bytes_explicitly(wire):
    wire[0].append(b"HTTP/1.1 200 OK\r\n\r\n" + b"x" * 100)
    result = PublicHttpsFetcher().fetch("https://example.org/", limits())
    assert result.outcome == "TRUNCATED" and len(result.body) == 64 and result.reason == "body_byte_limit"


def test_short_fixed_length_and_incomplete_chunk_cannot_complete(wire):
    wire[0].extend(
        [
            b"HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\nshort",
            b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n4\r\nab",
        ]
    )
    fetch = PublicHttpsFetcher()
    assert fetch.fetch("https://example.org/", limits()).outcome == "ERROR"
    assert fetch.fetch("https://example.org/", limits()).outcome == "ERROR"


def test_redirect_revalidates_each_url_dns_and_pins_separate_connections(wire, monkeypatch):
    seen = []

    def dns(host, *_a, **_k):
        seen.append(host)
        return answer()

    monkeypatch.setattr(module.socket, "getaddrinfo", dns)
    wire[0].extend(
        [
            b"HTTP/1.1 302 Found\r\nLocation: https://other.example/path\r\n\r\n",
            b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok",
        ]
    )
    result = PublicHttpsFetcher().fetch("https://example.org/", limits())
    assert result.outcome == "COMPLETE" and len(result.hops) == 2 and seen == ["example.org", "other.example"]
    assert wire[2] == ["example.org", "other.example"] and all(item.closed for item in wire[1])


@pytest.mark.parametrize(
    "location",
    [
        "https://127.0.0.1/private",
        "https://169.254.169.254/credentials",
        "http://example.org/",
        "https://user:password@example.org/",
        "/same#fragment",
    ],
)
def test_redirect_never_connects_to_denied_target(wire, monkeypatch, location):
    def dns(host, *_a, **_k):
        return answer(host) if host in ("127.0.0.1", "169.254.169.254") else answer()

    monkeypatch.setattr(module.socket, "getaddrinfo", dns)
    wire[0].append(b"HTTP/1.1 302 Found\r\nLocation: " + location.encode() + b"\r\n\r\n")
    result = PublicHttpsFetcher().fetch("https://example.org/", limits())
    assert result.outcome == "ERROR" and len(wire[1]) == 1


def test_relative_redirect_and_cycle_budget(wire):
    wire[0].extend([b"HTTP/1.1 302 Found\r\nLocation: /next\r\n\r\n", b"HTTP/1.1 302 Found\r\nLocation: /\r\n\r\n"])
    result = PublicHttpsFetcher().fetch("https://example.org/", limits())
    assert result.reason == "redirect_cycle" and len(result.hops) == 2


def test_zero_redirect_budget_never_follows(wire):
    wire[0].append(b"HTTP/1.1 302 Found\r\nLocation: /next\r\n\r\n")
    assert PublicHttpsFetcher().fetch("https://example.org/", limits(max_redirects=0)).reason == "redirect_denied"
    assert len(wire[1]) == 1


def test_header_framing_cap_applies_before_any_body(wire):
    wire[0].append(b"HTTP/1.1 200 OK\r\nX-Long: " + b"x" * (32 * 1024) + b"\r\n\r\n")
    assert PublicHttpsFetcher().fetch("https://example.org/", limits()).reason == "framing_byte_limit"


def test_pinned_peer_drift_denied_before_sending_request(wire, monkeypatch):
    monkeypatch.setattr(InjectedWire, "getpeername", lambda _self: ("127.0.0.1", 443))
    wire[0].append(b"HTTP/1.1 200 OK\r\n\r\n")
    assert PublicHttpsFetcher().fetch("https://example.org/", limits()).outcome == "ERROR"
    assert not wire[1][0].sent


def test_disabled_tls_verification_is_refused(wire, monkeypatch):
    context = module.ssl.create_default_context()
    context.check_hostname = False
    monkeypatch.setattr(module.ssl, "create_default_context", lambda: context)
    wire[0].append(b"HTTP/1.1 200 OK\r\n\r\n")
    assert PublicHttpsFetcher().fetch("https://example.org/", limits()).reason == "tls_verification_required"
    assert not wire[1][0].sent


def test_hung_resolvers_keep_bounded_slots_until_they_really_return(monkeypatch):
    fetch = PublicHttpsFetcher()
    release = threading.Event()

    def dns(*_a, **_k):
        release.wait(3)
        return answer()

    monkeypatch.setattr(module.socket, "getaddrinfo", dns)
    try:
        for _ in range(4):
            with pytest.raises(FetchDenied, match="fetch_deadline"):
                fetch._resolve("example.org", time.monotonic() + 0.02, threading.Event())
        with pytest.raises(FetchDenied, match="resolver_busy"):
            fetch._resolve("example.org", time.monotonic() + 1, threading.Event())
    finally:
        release.set()


def test_cancelled_or_busy_fetch_never_connects(wire):
    event = threading.Event()
    event.set()
    fetch = PublicHttpsFetcher()
    assert fetch.fetch("https://example.org/", limits(), cancel=event).reason == "fetch_cancelled"
    for _ in range(4):
        assert fetch._admission.acquire(blocking=False)
    try:
        assert fetch.fetch("https://example.org/", limits()).reason == "fetch_busy"
    finally:
        for _ in range(4):
            fetch._admission.release()
    assert not wire[1]


def test_actual_slow_socket_trickle_obeys_overall_deadline_and_cancellation():
    # Actual local socket proves per-receive deadline, not public TLS or private
    # destination admission. This low-level reader has no connection authority.
    left, right = socket.socketpair()
    stop = threading.Event()

    def trickle():
        while not stop.wait(0.01):
            try:
                right.sendall(b"x")
            except OSError:
                return

    worker = threading.Thread(target=trickle, daemon=True)
    worker.start()
    try:
        reader = module._FramingRead(left, time.monotonic() + 0.08, threading.Event())
        with pytest.raises(FetchDenied, match="fetch_deadline"):
            reader.readline()
        reader.close()
        cancel = threading.Event()
        cancel.set()
        with module._FramingRead(left, time.monotonic() + 1, cancel) as reader:
            with pytest.raises(FetchDenied, match="fetch_cancelled"):
                reader.read(1)
    finally:
        stop.set()
        left.close()
        right.close()
        worker.join(timeout=1)
