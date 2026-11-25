"""Loopback HTTP server for the scoped goal API.

Start with ``python -m panestria.api.serve``. The process binds the configured
loopback address and probes PostgreSQL from ``/readyz``. It does not listen on
any other interface. Accepted goals are continued only by a journey passed to
``main``; ``python -m panestria_devkit.api.serve`` passes the synthetic R0 one.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

import psycopg

from panestria.api.auth import MAX_BODY_BYTES, MAX_HEADER_BYTES, MAX_HEADER_LINE_BYTES, GoalApi, error_body
from panestria.api.health import default_readiness_probe
from panestria.api.main import create_app, mount_goal_api
from panestria.config import ProfileRejected, load_settings

# A peer must deliver the whole request within this bound; a slow or stalled
# sender cannot hold one of the loopback connections open indefinitely.
REQUEST_DEADLINE_SECONDS = 10
SYNTHETIC_OWNER = "00000000-0000-4000-8000-000000000002"
SYNTHETIC_PROJECT = "00000000-0000-4000-8000-000000000003"


class Journey(Protocol):
    """Continues accepted goals off the request path. HTTP handlers only submit the goal id."""

    def start(self) -> None: ...

    def submit(self, goal_id: str) -> None: ...

    def stop(self) -> None: ...


# (database_url, owner_id, project_id, sandbox) -> journey. The product server
# registers none; the dev-only R0 server (panestria_devkit.api.serve) passes the
# synthetic one.
JourneyFactory = Callable[[str, str, str, Path], Journey]


def _seed(database_url: str, owner_id: str, project_id: str) -> None:
    with psycopg.connect(database_url, connect_timeout=2) as connection:
        connection.execute(
            "INSERT INTO panestria.principal (id, display_name) VALUES (%s, 'synthetic-owner')"
            " ON CONFLICT (id) DO NOTHING",
            (owner_id,),
        )
        connection.execute(
            "INSERT INTO panestria.project (id, owner_id) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING",
            (project_id, owner_id),
        )
        connection.commit()


async def _read_line(reader: asyncio.StreamReader) -> bytes | None:
    """Read one header line. None means the line exceeded the cap."""
    try:
        line = await reader.readline()
    except (asyncio.LimitOverrunError, ValueError):
        return None
    if len(line) > MAX_HEADER_LINE_BYTES:
        return None
    return line


async def _read_request(reader: asyncio.StreamReader) -> tuple[str, str, list[tuple[bytes, bytes]], bytes] | bytes:
    request_line = await _read_line(reader)
    if request_line is None:
        return _plain(400, "invalid_request")
    if not request_line:
        return b""
    try:
        method, target, _version = request_line.decode("ascii").strip().split(" ", 2)
    except ValueError:
        return _plain(400, "invalid_request")
    headers: list[tuple[bytes, bytes]] = []
    length: int | None = None
    total = len(request_line)
    while True:
        line = await _read_line(reader)
        if line is None or total + len(line) > MAX_HEADER_BYTES:
            return _plain(400, "invalid_request")
        total += len(line)
        if line in (b"\r\n", b"\n", b""):
            break
        if b":" not in line:
            return _plain(400, "invalid_request")
        name, value = line.decode("latin-1").split(":", 1)
        encoded_name = name.strip().lower().encode("latin-1")
        encoded_value = value.strip().encode("latin-1")
        if encoded_name == b"transfer-encoding":
            return _plain(400, "invalid_request")
        headers.append((encoded_name, encoded_value))
        if encoded_name == b"content-length":
            try:
                parsed = int(encoded_value)
            except ValueError:
                return _plain(400, "invalid_request")
            if parsed < 0 or (length is not None and parsed != length):
                return _plain(400, "invalid_request")
            length = parsed
    if length is None:
        length = 0
    if length > MAX_BODY_BYTES:
        return _plain(413, "body_too_large")
    body = await reader.readexactly(length) if length else b""
    return method, target, headers, body


def _plain(status: int, code: str) -> bytes:
    payload = json.dumps(error_body(code), separators=(",", ":")).encode()
    reason = {400: "Bad Request", 408: "Request Timeout", 413: "Payload Too Large"}.get(status, "Error")
    header = (
        f"HTTP/1.1 {status} {reason}\r\nContent-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\nConnection: close\r\n\r\n"
    )
    return header.encode() + payload


async def _invoke(
    app: object,
    method: str,
    target: str,
    headers: list[tuple[bytes, bytes]],
    body: bytes,
    client: tuple[str, int],
    server: tuple[str, int],
) -> tuple[int, list[tuple[bytes, bytes]], bytes]:
    parts = urlsplit(target)
    scope = {
        "type": "http",
        "asgi": {"spec_version": "2.3", "version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": parts.path or "/",
        "raw_path": (parts.path or "/").encode(),
        "query_string": parts.query.encode(),
        "headers": headers,
        "client": client,
        "server": server,
    }
    delivered = False

    async def receive() -> dict[str, object]:
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    status = 500
    response_headers: list[tuple[bytes, bytes]] = []
    chunks: list[bytes] = []

    async def send(message: dict[str, object]) -> None:
        nonlocal status, response_headers
        if message["type"] == "http.response.start":
            raw_status = message.get("status")
            raw_headers = message.get("headers")
            if isinstance(raw_status, int):
                status = raw_status
            if isinstance(raw_headers, list):
                response_headers = [item for item in raw_headers if isinstance(item, tuple)]
        elif message["type"] == "http.response.body":
            payload = message.get("body", b"")
            if isinstance(payload, bytes):
                chunks.append(payload)

    await app(scope, receive, send)  # type: ignore[operator]
    return status, response_headers, b"".join(chunks)


async def _handle(
    app: object,
    server: tuple[str, int],
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    try:
        try:
            parsed = await asyncio.wait_for(_read_request(reader), REQUEST_DEADLINE_SECONDS)
        except TimeoutError:
            parsed = _plain(408, "request_deadline_exceeded")
        except asyncio.IncompleteReadError:
            return  # The peer closed before sending the declared body.
        if isinstance(parsed, bytes):
            if parsed:
                writer.write(parsed)
                await writer.drain()
            return
        method, target, headers, body = parsed
        peer = writer.get_extra_info("peername")
        client = peer if isinstance(peer, tuple) else ("127.0.0.1", 0)
        status, response_headers, payload = await _invoke(app, method, target, headers, body, client, server)
        skipped = {b"content-length", b"transfer-encoding"}
        kept = [(name, value) for name, value in response_headers if name.lower() not in skipped]
        kept.append((b"content-length", str(len(payload)).encode()))
        kept.append((b"connection", b"close"))
        head = b"".join(b"%s: %s\r\n" % item for item in kept)
        writer.write(f"HTTP/1.1 {status} OK\r\n".encode() + head + b"\r\n" + payload)
        await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


async def _listen(app: object, host: str, port: int) -> None:
    server_name = (host, port)

    async def connection(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await _handle(app, server_name, reader, writer)

    lifespan = getattr(getattr(app, "router", None), "lifespan_context", None)
    if lifespan is None:
        raise RuntimeError("application has no lifespan")
    async with lifespan(app):
        tcp = await asyncio.start_server(connection, host, port, limit=MAX_HEADER_LINE_BYTES)
        async with tcp:
            await tcp.serve_forever()


def main(journey: JourneyFactory | None = None) -> None:
    token = os.environ.pop("PANESTRIA_TOKEN", "")
    owner = os.environ.pop("PANESTRIA_OWNER_ID", SYNTHETIC_OWNER)
    project = os.environ.pop("PANESTRIA_PROJECT_ID", SYNTHETIC_PROJECT)
    sandbox = Path(os.environ.pop("PANESTRIA_SANDBOX", "/tmp/panestria-r0")).resolve()
    try:
        settings = load_settings()
    except ProfileRejected as exc:
        sys.stderr.write(f"{exc.code}\n")
        raise SystemExit(2) from None
    if len(token) < 16:
        sys.stderr.write("missing_token\n")
        raise SystemExit(2)
    sandbox.mkdir(parents=True, exist_ok=True)
    database_url = settings.database_url.get_secret_value()
    try:
        _seed(database_url, owner, project)
    except psycopg.Error:
        sys.stderr.write("database_unavailable\n")
        raise SystemExit(2) from None
    application = create_app(settings, default_readiness_probe)
    mount_goal_api(application, GoalApi(token, owner, project, database_url))
    # The artifact route reads evidence from this root, with or without a journey.
    application.state.sandbox = sandbox
    driver = None if journey is None else journey(database_url, owner, project, sandbox)
    application.state.journey = driver
    if driver is not None:
        driver.start()
    try:
        asyncio.run(_listen(application, settings.bind_host, settings.bind_port))
    finally:
        if driver is not None:
            driver.stop()


if __name__ == "__main__":
    main()
