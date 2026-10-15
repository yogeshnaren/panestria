"""Bounded same-origin HTTP envelope; no wildcard CORS or credential URLs."""

from __future__ import annotations

import asyncio
import threading
import time
from collections import OrderedDict
from urllib.parse import parse_qsl

from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from panestria.api.auth import MAX_BODY_BYTES, MAX_HEADER_BYTES, MAX_HEADER_LINE_BYTES, error_body
from panestria.api.sessions import BrowserAccess

_SECURITY_HEADERS = {
    "cache-control": "no-store",
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "cross-origin-resource-policy": "same-origin",
    "x-frame-options": "DENY",
    "content-security-policy": "default-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
    "base-uri 'none'; object-src 'none'; form-action 'self'",
}


class RequestLimits:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buckets: OrderedDict[str, tuple[float, int]] = OrderedDict()

    def admit(self, key: str, maximum: int) -> bool:
        now = time.monotonic()
        with self._lock:
            began, count = self._buckets.pop(key, (now, 0))
            if now - began >= 60:
                began, count = now, 0
            self._buckets[key] = began, count + 1
            while len(self._buckets) > 128:
                self._buckets.popitem(last=False)
            return count < maximum


class BrowserSecurity:
    def __init__(self, app: ASGIApp, access: BrowserAccess) -> None:
        self.app, self.access, self.limits = app, access, RequestLimits()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def secured(message: Message) -> None:
            if message["type"] == "http.response.start":
                original = message.get("headers", [])
                names = {key.encode() for key in _SECURITY_HEADERS}
                message["headers"] = [(name, value) for name, value in original if name.lower() not in names]
                message["headers"] += [(key.encode(), value.encode()) for key, value in _SECURITY_HEADERS.items()]
            await send(message)

        async def deny(code: str, status: int) -> None:
            await JSONResponse(status_code=status, content=error_body(code))(scope, receive, secured)

        headers = scope.get("headers", [])
        if sum(len(k) + len(v) + 4 for k, v in headers) > MAX_HEADER_BYTES or any(
            len(k) + len(v) + 2 > MAX_HEADER_LINE_BYTES for k, v in headers
        ):
            await deny("headers_too_large", 431)
            return
        sensitive = {
            b"host",
            b"origin",
            b"authorization",
            b"cookie",
            b"content-length",
            b"content-type",
            b"x-panestria-csrf",
        }
        for name in sensitive:
            if sum(key.lower() == name for key, _ in headers) > 1:
                await deny("ambiguous_headers", 400)
                return
        values = {key.lower(): value.decode("latin-1") for key, value in headers}
        if values.get(b"host", "").lower() != self.access.host:
            await deny("invalid_host", 403)
            return
        if b"origin" in values and values[b"origin"] != self.access.origin:
            await deny("origin_denied", 403)
            return
        try:
            query = parse_qsl(scope.get("query_string", b"").decode("ascii"), max_num_fields=64)
        except (ValueError, UnicodeDecodeError):
            await deny("invalid_query", 422)
            return
        if any(key.lower() in {"token", "api_key", "session", "csrf", "pairing_code"} for key, _ in query):
            await deny("credential_in_url_denied", 400)
            return
        client = str(scope.get("client", ("local",))[0])
        path = str(scope.get("path", ""))
        pairing = path == "/v1/session/pair"
        if not self.limits.admit(f"{client}:{'pair' if pairing else 'api'}", 5 if pairing else 120):
            await deny("rate_limited", 429)
            return
        if scope.get("method") in {"POST", "PUT", "PATCH", "DELETE"}:
            media = values.get(b"content-type", "").split(";", 1)[0].strip().lower()
            if media != "application/json":
                await deny("unsupported_media_type", 415)
                return
        body = bytearray()
        try:
            while True:
                message = await asyncio.wait_for(receive(), timeout=5)
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                if len(body) + len(chunk) > MAX_BODY_BYTES:
                    await deny("body_too_large", 413)
                    return
                body.extend(chunk)
                if not message.get("more_body", False):
                    break
            body.decode("utf-8")
        except TimeoutError:
            await deny("request_deadline_exceeded", 408)
            return
        except UnicodeDecodeError:
            await deny("invalid_body", 422)
            return
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, replay, secured)
