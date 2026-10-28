"""BrowserSecurity: every deny branch, header hygiene and the single replayed body."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from panestria.api.auth import MAX_BODY_BYTES, MAX_HEADER_LINE_BYTES
from panestria.api.security import BrowserSecurity

HOST = "127.0.0.1:8765"
ORIGIN = "http://127.0.0.1:8765"


def _run(
    *,
    method="GET",
    path="/v1/health",
    headers=None,
    query=b"",
    chunks=(b"",),
    scope_type="http",
    client="10.0.0.1",
    middleware=None,
):
    seen = {}

    async def app(scope, receive, send):
        message = await receive()
        seen["body"] = message["body"]
        seen["again"] = await receive()
        await send({"type": "http.response.start", "status": 200, "headers": [(b"x-frame-options", b"SAMEORIGIN")]})
        await send({"type": "http.response.body", "body": b"{}"})

    security = middleware or BrowserSecurity(app, SimpleNamespace(host=HOST, origin=ORIGIN))
    pending = [
        {"type": "http.request", "body": chunk, "more_body": i < len(chunks) - 1} for i, chunk in enumerate(chunks)
    ]
    pending.append({"type": "http.disconnect"})
    sent = []

    async def receive():
        return pending.pop(0)

    async def send(message):
        sent.append(message)

    scope = {
        "type": scope_type,
        "method": method,
        "path": path,
        "query_string": query,
        "client": (client, 5000),
        "headers": [(b"host", HOST.encode())] if headers is None else headers,
    }
    asyncio.run(security(scope, receive, send))
    start = next((m for m in sent if m["type"] == "http.response.start"), None)
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return start, body, seen, sent


def _code(body):
    return json.loads(body)["code"] if body else None


def test_allowed_request_replays_the_body_once_and_overrides_framing_headers():
    start, _, seen, _ = _run(
        method="POST",
        headers=[(b"host", HOST.encode()), (b"content-type", b"application/json")],
        chunks=(b'{"a"', b":1}"),
    )
    assert start["status"] == 200
    assert seen["body"] == b'{"a":1}' and seen["again"] == {"type": "http.disconnect"}
    headers = dict(start["headers"])
    assert headers[b"x-frame-options"] == b"DENY" and headers[b"cache-control"] == b"no-store"
    assert [name for name, _ in start["headers"]].count(b"x-frame-options") == 1


@pytest.mark.parametrize(
    ("kwargs", "status", "code"),
    [
        ({"headers": [(b"host", HOST.encode()), (b"x-big", b"v" * MAX_HEADER_LINE_BYTES)]}, 431, "headers_too_large"),
        (
            {"headers": [(b"host", HOST.encode())] + [(b"x-%d" % i, b"v" * 7000) for i in range(5)]},
            431,
            "headers_too_large",
        ),
        ({"headers": [(b"host", HOST.encode()), (b"Host", HOST.encode())]}, 400, "ambiguous_headers"),
        ({"headers": [(b"host", HOST.encode()), (b"cookie", b"a"), (b"cookie", b"b")]}, 400, "ambiguous_headers"),
        ({"headers": [(b"host", b"evil.example")]}, 403, "invalid_host"),
        ({"headers": []}, 403, "invalid_host"),
        ({"headers": [(b"host", HOST.encode()), (b"origin", b"http://evil.example")]}, 403, "origin_denied"),
        ({"query": b"a=\xff"}, 422, "invalid_query"),
        ({"query": b"&".join(b"k%d=v" % i for i in range(65))}, 422, "invalid_query"),
        ({"query": b"x=1&TOKEN=abc"}, 400, "credential_in_url_denied"),
        ({"query": b"pairing_code=1"}, 400, "credential_in_url_denied"),
        (
            {"method": "POST", "headers": [(b"host", HOST.encode()), (b"content-type", b"text/plain")]},
            415,
            "unsupported_media_type",
        ),
        ({"method": "DELETE"}, 415, "unsupported_media_type"),
        (
            {
                "method": "POST",
                "headers": [(b"host", HOST.encode()), (b"content-type", b"application/json")],
                "chunks": (b"x" * MAX_BODY_BYTES, b"x"),
            },
            413,
            "body_too_large",
        ),
        (
            {
                "method": "POST",
                "headers": [(b"host", HOST.encode()), (b"content-type", b"application/json")],
                "chunks": (b"\xff",),
            },
            422,
            "invalid_body",
        ),
    ],
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_each_deny_branch_returns_its_code_and_never_reaches_the_app(kwargs, status, code):
    start, body, seen, _ = _run(**kwargs)
    assert start["status"] == status and _code(body) == code
    assert seen == {}
    assert dict(start["headers"])[b"x-content-type-options"] == b"nosniff"


def test_websocket_is_closed_with_policy_violation():
    _, _, seen, sent = _run(scope_type="websocket")
    assert sent == [{"type": "websocket.close", "code": 1008}] and seen == {}


def test_pairing_is_limited_to_five_per_minute_per_client_and_separately_from_the_api():
    security = BrowserSecurity(None, SimpleNamespace(host=HOST, origin=ORIGIN))

    async def app(scope, receive, send):
        await receive()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    security.app = app
    statuses = [_run(path="/v1/session/pair", middleware=security)[0]["status"] for _ in range(6)]
    assert statuses == [200] * 5 + [429]
    assert _run(path="/v1/health", middleware=security)[0]["status"] == 200
    assert _run(path="/v1/session/pair", client="10.0.0.2", middleware=security)[0]["status"] == 200


def test_client_disconnect_before_the_body_ends_reaches_nothing():
    start, _, seen, sent = _run(
        method="POST", headers=[(b"host", HOST.encode()), (b"content-type", b"application/json")], chunks=()
    )
    assert start is None and sent == [] and seen == {}
