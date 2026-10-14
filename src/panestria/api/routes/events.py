"""Scoped JSON compatibility and revocation-aware canonical SSE replay."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from panestria.api.auth import GoalApi, LoopbackDenied, authorize, error_body, reauthorize_mutation
from panestria.api.db import DatabaseUnavailable, open_database
from panestria.api.views import EventPage
from panestria.kernel.errors import KernelDenied
from panestria.kernel.event_replay import parse_cursor
from panestria.kernel.goals import Actor, GoalService
from panestria.kernel.uow import UnitOfWork

router = APIRouter()
_SERVICE = GoalService()


def _json_events(request: Request, api: GoalApi, actor: Actor, goal_id: str, cursor: int, limit: int) -> JSONResponse:
    with open_database(api.database_url) as connection:
        reauthorize_mutation(request, api, connection)
        rows = _SERVICE.events(UnitOfWork(connection), actor, goal_id, cursor, limit)
    return JSONResponse(
        status_code=200,
        content={
            "events": [{"seq": str(seq), "kind": kind, "payload": payload} for seq, kind, payload in rows],
        },
    )


@router.get("/v1/goals/{goal_id}/events", response_model=None, responses={200: {"model": EventPage}})
async def read_events(
    goal_id: str, request: Request, after: str = "0", limit: int = 50
) -> JSONResponse | StreamingResponse:
    try:
        api = getattr(request.app.state, "goal_api", None)
        if not isinstance(api, GoalApi):
            raise LoopbackDenied("not_configured", 503)
        actor = await asyncio.to_thread(authorize, request, api)
        if request.headers.get("accept") == "text/event-stream":
            from panestria.api.event_stream import stream_events

            return await stream_events(request, api, goal_id, after)
        cursor = parse_cursor(after)
        if not 1 <= limit <= 100:
            raise KernelDenied("invalid_limit")
        return await asyncio.to_thread(_json_events, request, api, actor, goal_id, cursor, limit)
    except LoopbackDenied as exc:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code))
    except KernelDenied as exc:
        return JSONResponse(status_code=404 if exc.code == "not_found" else 422, content=error_body(exc.code))
    except DatabaseUnavailable:
        return JSONResponse(status_code=503, content=error_body("database_unavailable"))
