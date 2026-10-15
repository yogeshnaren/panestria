"""Bounded public HTTPS bytes, not policy authorization or usable source evidence."""

from __future__ import annotations

import hashlib
import http.client
import io
import ipaddress
import queue
import re
import socket
import ssl
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, cast
from urllib.parse import quote, urljoin, urlsplit

from pydantic import SecretStr

from panestria.contracts.research import ResearchLimits
from panestria.sandbox.egress import EgressDenied, _public_unicast, _verify_peer

_FRAMING_BYTES = 32 * 1024


class FetchDenied(ValueError):
    pass


@dataclass(frozen=True)
class HttpsTarget:
    host: str
    authority: str
    resource: str = field(repr=False)


@dataclass(frozen=True)
class FetchHop:
    url_sha256: str
    address: str
    status: int
    certificate_sha256: str


@dataclass(frozen=True)
class FetchObservation:
    requested_url: SecretStr
    terminal_url: SecretStr | None
    observed_at: datetime
    outcome: Literal["COMPLETE", "TRUNCATED", "ERROR", "UNSUPPORTED"]
    reason: str
    hops: tuple[FetchHop, ...]
    content_type: str | None
    body: bytes = field(repr=False)

    @property
    def retained_sha256(self) -> str:
        return hashlib.sha256(self.body).hexdigest()


def https_target(url: str) -> HttpsTarget:
    try:
        if (
            type(url) is not str
            or not 1 <= len(url.encode()) <= 2048
            or any(ord(char) <= 32 or ord(char) == 127 or char == "\\" for char in url)
        ):
            raise ValueError
        parts = urlsplit(url)
        if (
            parts.scheme != "https"
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or parts.fragment
            or parts.port not in (None, 443)
            or "%" in parts.hostname
        ):
            raise ValueError
        host = parts.hostname.encode("idna").decode("ascii").lower()
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if (
                not 1 <= len(host) <= 253
                or "." not in host
                or any(
                    re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) is None for label in host.split(".")
                )
            ):
                raise ValueError from None
        authority = "[" + host + "]" if ":" in host else host
        resource = quote(parts.path or "/", safe="/%:@!$&'()*+,;=-._~")
        if parts.query:
            resource += "?" + quote(parts.query, safe="/?%:@!$&'()*+,;=-._~")
        return HttpsTarget(host, authority, resource)
    except (ValueError, UnicodeError):
        raise FetchDenied("url_denied") from None


def _remaining(deadline: float, cancel: threading.Event) -> float:
    if cancel.is_set():
        raise FetchDenied("fetch_cancelled")
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise FetchDenied("fetch_deadline")
    return remaining


class _DeadlineRead(io.RawIOBase):
    def __init__(self, connection: ssl.SSLSocket, deadline: float, cancel: threading.Event) -> None:
        super().__init__()
        self.connection, self.deadline, self.cancel = connection, deadline, cancel

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: Any) -> int:
        while True:
            self.connection.settimeout(min(0.2, _remaining(self.deadline, self.cancel)))
            try:
                return self.connection.recv_into(buffer)
            except TimeoutError:
                continue  # The overall deadline and cancellation still advance.


class _FramingRead(io.BufferedReader):
    def __init__(self, connection: ssl.SSLSocket, deadline: float, cancel: threading.Event) -> None:
        super().__init__(_DeadlineRead(connection, deadline, cancel), buffer_size=4096)
        self.framing_bytes = 0

    def readline(self, size: int | None = -1) -> bytes:
        remaining = _FRAMING_BYTES - self.framing_bytes
        line = super().readline(min(size, remaining + 1) if size is not None and size >= 0 else remaining + 1)
        self.framing_bytes += len(line)
        if self.framing_bytes > _FRAMING_BYTES:
            raise FetchDenied("framing_byte_limit")
        return line


class _HttpSocket:
    def __init__(self, connection: ssl.SSLSocket, deadline: float, cancel: threading.Event) -> None:
        self.connection, self.deadline, self.cancel = connection, deadline, cancel

    def makefile(self, mode: str) -> _FramingRead:
        if mode != "rb":
            raise FetchDenied("unsupported_http_stream")
        return _FramingRead(self.connection, self.deadline, self.cancel)


class PublicHttpsFetcher:
    """Controller-only, already-authorized PUBLIC URL input. No cookies, proxies or retries."""

    def __init__(self) -> None:
        self._admission = threading.BoundedSemaphore(4)
        self._resolvers = threading.BoundedSemaphore(4)

    def _resolve(self, host: str, deadline: float, cancel: threading.Event) -> tuple[int, str]:
        if not self._resolvers.acquire(blocking=False):
            raise FetchDenied("resolver_busy")
        result: queue.Queue[list[tuple[Any, ...]] | None] = queue.Queue(maxsize=1)

        def lookup() -> None:
            try:
                try:
                    result.put(socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP))
                except OSError:
                    result.put(None)
            finally:
                self._resolvers.release()  # A timed-out OS resolver keeps its own slot until it actually ends.

        try:
            threading.Thread(target=lookup, daemon=True, name="panestria-public-fetch-dns").start()
        except RuntimeError:
            self._resolvers.release()
            raise FetchDenied("resolver_unavailable") from None
        while True:
            try:
                answers = result.get(timeout=min(0.05, _remaining(deadline, cancel)))
                break
            except queue.Empty:
                continue
        if not answers or len(answers) > 32:
            raise FetchDenied("dns_unavailable")
        addresses: set[tuple[int, str]] = set()
        for family, kind, proto, _canonical, address in answers:
            if (
                family not in (socket.AF_INET, socket.AF_INET6)
                or kind != socket.SOCK_STREAM
                or proto != socket.IPPROTO_TCP
                or _public_unicast(address[0]) is None
                or address[1] != 443
                or (len(address) == 4 and address[3] != 0)
            ):
                raise FetchDenied("private_destination_denied")
            addresses.add((family, str(ipaddress.ip_address(address[0]))))
        return sorted(addresses)[0]  # Numeric connect only, no second name lookup.

    def _one(
        self, target: HttpsTarget, url: str, cap: int, deadline: float, cancel: threading.Event
    ) -> tuple[FetchHop, str | None, str | None, bytes, bool]:
        family, address = self._resolve(target.host, deadline, cancel)
        with socket.socket(family, socket.SOCK_STREAM, socket.IPPROTO_TCP) as raw:
            raw.settimeout(min(5.0, _remaining(deadline, cancel)))
            raw.connect((address, 443) if family == socket.AF_INET else (address, 443, 0, 0))
            _verify_peer(raw.getpeername(), address, 443)
            context = ssl.create_default_context()
            if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
                raise FetchDenied("tls_verification_required")
            context.set_alpn_protocols(["http/1.1"])
            raw.settimeout(min(5.0, _remaining(deadline, cancel)))
            with context.wrap_socket(raw, server_hostname=target.host) as connection:
                _verify_peer(connection.getpeername(), address, 443)
                certificate = connection.getpeercert(binary_form=True)
                if not certificate:
                    raise FetchDenied("tls_certificate_unavailable")
                request = (
                    "GET "
                    + target.resource
                    + " HTTP/1.1\r\nHost: "
                    + target.authority
                    + "\r\nUser-Agent: Panestria-Research/0.6.1\r\nAccept: text/plain,text/html,application/pdf"
                    + "\r\nAccept-Encoding: identity\r\nConnection: close\r\n\r\n"
                ).encode("ascii")
                connection.settimeout(min(5.0, _remaining(deadline, cancel)))
                connection.sendall(request)
                # HTTPResponse only needs makefile(). Its reader checks every underlying receive,
                # including slow status/header/chunk framing; it never opens another connection.
                with http.client.HTTPResponse(
                    cast(socket.socket, _HttpSocket(connection, deadline, cancel)), method="GET"
                ) as response:
                    response.begin()
                    if response.headers.defects or any(
                        re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name) is None
                        or any(ord(char) < 32 or ord(char) == 127 for char in value)
                        for name, value in response.getheaders()
                    ):
                        raise FetchDenied("invalid_http_headers")
                    hop = FetchHop(
                        hashlib.sha256(url.encode()).hexdigest(),
                        address,
                        response.status,
                        hashlib.sha256(certificate).hexdigest(),
                    )
                    location = response.getheader("Location")
                    if response.status in {301, 302, 303, 307, 308}:
                        if len(response.headers.get_all("Location", [])) != 1:
                            raise FetchDenied("redirect_denied")
                        return hop, location, None, b"", False
                    encoding = response.getheader("Content-Encoding", "identity")
                    transfer = response.getheader("Transfer-Encoding")
                    lengths = response.headers.get_all("Content-Length", [])
                    if (
                        encoding.lower().strip() != "identity"
                        or transfer not in (None, "chunked")
                        or (len(lengths) > 1 or (transfer is not None and lengths))
                    ):
                        raise FetchDenied("unsupported_http_encoding")
                    if lengths and (not re.fullmatch(r"[0-9]{1,16}", lengths[0]) or int(lengths[0]) > cap):
                        raise FetchDenied("declared_body_limit")
                    content_type = (
                        response.getheader("Content-Type", "application/octet-stream").split(";", 1)[0].lower().strip()
                    )
                    if len(content_type) > 128:
                        raise FetchDenied("invalid_content_type")
                    body = bytearray()
                    while len(body) <= cap:
                        _remaining(deadline, cancel)
                        chunk = response.read(min(16384, cap + 1 - len(body)))
                        if not chunk:
                            break
                        body.extend(chunk)
                    truncated = len(body) > cap
                    if lengths and not truncated and len(body) != int(lengths[0]):
                        raise FetchDenied("incomplete_http_body")
                    return hop, None, content_type, bytes(body[:cap]), truncated

    def fetch(self, url: str, limits: ResearchLimits, *, cancel: threading.Event | None = None) -> FetchObservation:
        cancel = cancel if cancel is not None else threading.Event()
        limits = ResearchLimits.model_validate(limits)
        observed_at = datetime.now(UTC)
        hops: list[FetchHop] = []
        current: str | None = None

        def observation(
            outcome: Literal["COMPLETE", "TRUNCATED", "ERROR", "UNSUPPORTED"],
            reason: str,
            content_type: str | None = None,
            body: bytes = b"",
        ) -> FetchObservation:
            return FetchObservation(
                SecretStr(url),
                None if current is None else SecretStr(current),
                observed_at,
                outcome,
                reason,
                tuple(hops),
                content_type,
                body,
            )

        if not self._admission.acquire(blocking=False):
            return observation("ERROR", "fetch_busy")
        deadline = time.monotonic() + limits.deadline_seconds
        try:
            current = url
            visited: set[str] = set()
            for index in range(limits.max_redirects + 1):
                target = https_target(current)
                if current in visited:
                    raise FetchDenied("redirect_cycle")
                visited.add(current)
                _remaining(deadline, cancel)
                hop, location, content_type, body, truncated = self._one(
                    target, current, limits.max_source_bytes, deadline, cancel
                )
                hops.append(hop)
                if hop.status in {301, 302, 303, 307, 308}:
                    if (
                        index >= limits.max_redirects
                        or location is None
                        or not 1 <= len(location.encode()) <= 2048
                        or any(ord(char) <= 32 or ord(char) == 127 or char == "\\" for char in location)
                    ):
                        raise FetchDenied("redirect_denied")
                    current = urljoin(current, location)
                    continue
                if truncated:
                    return observation("TRUNCATED", "body_byte_limit", content_type, body)
                if not 200 <= hop.status < 300:
                    return observation("ERROR", "http_error", content_type, body)
                return observation("COMPLETE", "retained_bytes_only", content_type, body)
            raise FetchDenied("redirect_denied")
        except FetchDenied as error:
            return observation("ERROR", str(error))
        except (OSError, ValueError, UnicodeError, EgressDenied, http.client.HTTPException):
            return observation("ERROR", "network_or_protocol_error")
        finally:
            self._admission.release()
