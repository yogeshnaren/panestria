"""Serve an ASGI application with uvicorn on a socket bound before startup.

Every product server shares one uvicorn configuration (``server_config``) and
the same pinned HTTP/1.1 parser (``LocalHttpProtocol``). ``TransportLimits`` adds
the request bounds that the hand-rolled R0 server used to enforce itself, so any
app can keep them under uvicorn:

- a request line or header line over ``MAX_HEADER_LINE_BYTES``, headers over
  ``MAX_HEADER_BYTES`` in total, or any ``Transfer-Encoding`` header is refused
  with ``400 invalid_request``, echoing nothing back;
- a declared ``Content-Length`` over ``MAX_BODY_BYTES`` is refused with ``413
  body_too_large`` before any body byte is read;
- the request body must arrive within ``REQUEST_DEADLINE_SECONDS`` or the
  client gets ``408 request_deadline_exceeded``. The deadline stops once the
  body is complete, so a long-lived response such as an event stream, which
  waits on ``receive`` for a disconnect, is not cut short.

Header-phase stalls and malformed HTTP are handled by the protocol itself; see
``local_protocol.py``. ``GOAL_API_PROTOCOL`` is the one that answers a stalled
header block with 408, as the goal API always has.
"""

from __future__ import annotations

import asyncio
import json
import socket
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

import uvicorn

from panestria.api.auth import MAX_BODY_BYTES, MAX_HEADER_BYTES, MAX_HEADER_LINE_BYTES, error_body
from panestria.api.local_protocol import AnsweringHttpProtocol, LocalHttpProtocol
from panestria.config_local import LocalApplicationRejected

REQUEST_DEADLINE_SECONDS = 10.0
GOAL_API_PROTOCOL = AnsweringHttpProtocol

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


def owned_socket(host: str, port: int) -> socket.socket:
    """Bind and listen before startup, so no other process can take the port meanwhile."""
    listener = socket.socket(socket.AF_INET6 if host == "::1" else socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if host == "::1":
            listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        listener.bind((host, port))
        # Reserve the port exclusively throughout startup. Two SO_REUSEADDR
        # sockets may otherwise bind the same address before either listens.
        listener.listen(16)
        listener.setblocking(False)
        return listener
    except OSError:
        listener.close()
        raise LocalApplicationRejected("local_bind_unavailable") from None


def server_config(app: Any, *, http: type[LocalHttpProtocol] = LocalHttpProtocol) -> uvicorn.Config:
    # Installed source confirms TRACE wraps ASGI messages and access logs include
    # query strings. Fixed NullHandlers prevent accidental exception/body output.
    logging = {
        "version": 1,
        "disable_existing_loggers": False,
        "handlers": {"discard": {"class": "logging.NullHandler"}},
        "loggers": {
            name: {"handlers": ["discard"], "level": "CRITICAL", "propagate": False}
            for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "uvicorn.asgi")
        },
    }
    return uvicorn.Config(
        app,
        host="127.0.0.1",
        workers=1,
        reload=False,
        proxy_headers=False,
        http=http,
        ws="none",
        interface="asgi3",
        lifespan="on",
        access_log=False,
        log_config=logging,
        log_level="critical",
        server_header=False,
        limit_concurrency=16,
        backlog=16,
        timeout_keep_alive=2,
        timeout_graceful_shutdown=5,
        h11_max_incomplete_event_size=MAX_HEADER_BYTES,
    )


def _refusal(scope: Scope) -> tuple[int, str] | None:
    headers: list[tuple[bytes, bytes]] = list(scope.get("headers") or [])
    query = scope.get("query_string") or b""
    request_line = len(scope.get("method", "")) + len(scope.get("raw_path") or b"") + len(query) + 12
    if request_line > MAX_HEADER_LINE_BYTES:
        return 400, "invalid_request"
    if sum(len(k) + len(v) + 4 for k, v in headers) > MAX_HEADER_BYTES or any(
        len(k) + len(v) + 4 > MAX_HEADER_LINE_BYTES for k, v in headers
    ):
        return 400, "invalid_request"
    if any(name.lower() == b"transfer-encoding" for name, _ in headers):
        return 400, "invalid_request"
    for name, value in headers:
        # The parser already refused a malformed, negative or conflicting length.
        if name.lower() == b"content-length" and value.isdigit() and int(value) > MAX_BODY_BYTES:
            return 413, "body_too_large"
    return None


async def _respond(send: Send, status: int, code: str) -> None:
    payload = json.dumps(error_body(code), separators=(",", ":")).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode()),
                (b"connection", b"close"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": payload, "more_body": False})


class TransportLimits:
    """ASGI middleware enforcing the request bounds above. Add it as the outermost app middleware."""

    def __init__(self, app: ASGIApp, deadline_seconds: float = REQUEST_DEADLINE_SECONDS) -> None:
        self.app, self.deadline_seconds = app, deadline_seconds

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        refusal = _refusal(scope)
        if refusal is not None:
            await _respond(send, *refusal)
            return
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.deadline_seconds
        body_complete = False
        answered = False

        async def bounded_receive() -> Message:
            nonlocal body_complete, answered
            if answered:
                return {"type": "http.disconnect"}
            if body_complete:
                return await receive()
            try:
                message = await asyncio.wait_for(receive(), max(deadline - loop.time(), 0.0))
            except TimeoutError:
                # Answer here rather than raise into the app, so no route-level
                # exception handling can turn a stalled body into another reply.
                answered = True
                await _respond(send, 408, "request_deadline_exceeded")
                return {"type": "http.disconnect"}
            if message["type"] != "http.request" or not message.get("more_body", False):
                body_complete = True
            return message

        async def guarded_send(message: Message) -> None:
            if not answered:
                await send(message)

        try:
            await self.app(scope, bounded_receive, guarded_send)
        except Exception:
            # After a 408 the app only sees a client disconnect; its reaction is moot.
            if not answered:
                raise
