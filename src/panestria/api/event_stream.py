"""Scoped, revocation-aware SSE with bounded polling and no in-memory truth store."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator

import psycopg
from fastapi import Request
from fastapi.responses import StreamingResponse

from panestria.api.auth import GoalApi, LoopbackDenied, authorize, error_body, reauthorize_mutation
from panestria.api.db import DatabaseUnavailable, open_database
from panestria.kernel.errors import KernelDenied
from panestria.kernel.event_replay import EventReplay, ReplayPage, parse_cursor, sse_event
from panestria.kernel.goals import Actor
from panestria.kernel.uow import UnitOfWork

_REPLAY = EventReplay()


def _page(
    request: Request, api: GoalApi, actor: Actor, goal_id: str, after: int, *, metadata_only: bool = False
) -> ReplayPage:
    try:
        if metadata_only:
            authorize(request, api)
        with open_database(api.database_url) as connection:
            if metadata_only:
                connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            else:
                reauthorize_mutation(request, api, connection)  # GET: expiry/revocation, no mutation CSRF.
            return _REPLAY.read(UnitOfWork(connection), actor, goal_id, after, metadata_only=metadata_only)
    except psycopg.Error:
        raise DatabaseUnavailable from None


async def stream_events(
    request: Request, api: GoalApi, goal_id: str, after: str, *, metadata_only: bool = False
) -> StreamingResponse:
    actor = await asyncio.to_thread(authorize, request, api)
    header = request.headers.get("last-event-id")
    if header is not None and after != "0" and header != after:
        raise KernelDenied("cursor_conflict")
    cursor = parse_cursor(header if header is not None else after)
    first = await asyncio.to_thread(_page, request, api, actor, goal_id, cursor, metadata_only=metadata_only)

    async def frames() -> AsyncIterator[bytes]:
        nonlocal cursor
        page = first
        began, heartbeat = time.monotonic(), time.monotonic()
        try:
            while time.monotonic() - began < 30:
                if await request.is_disconnected():
                    return
                if page.resync:
                    # The initial page can predate revocation. A retained-event
                    # snapshot is private data just like an ordinary event.
                    await asyncio.to_thread(authorize, request, api)
                    yield f"event: resync\ndata: {json.dumps(page.snapshot, separators=(',', ':'))}\n\n".encode()
                    return
                for event in page.events:
                    # Check again between deliveries; revocation cannot turn into a
                    # long-lived private stream under an expired browser session.
                    await asyncio.to_thread(authorize, request, api)
                    yield sse_event(event)
                    cursor = int(str(event["seq"]))
                if not page.events:
                    if time.monotonic() - heartbeat >= 5:
                        yield b": keepalive\n\n"
                        heartbeat = time.monotonic()
                    await asyncio.sleep(0.1)
                page = await asyncio.to_thread(_page, request, api, actor, goal_id, cursor, metadata_only=metadata_only)
        except (KernelDenied, LoopbackDenied) as exc:
            yield f"event: error\ndata: {json.dumps(error_body(exc.code))}\n\n".encode()
        except DatabaseUnavailable:
            yield f"event: error\ndata: {json.dumps(error_body('database_unavailable'))}\n\n".encode()

    return StreamingResponse(
        frames(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff",
        },
    )
