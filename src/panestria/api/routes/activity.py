"""Authenticated content-free project activity, without model or mutation routes."""

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from panestria.api.auth import LoopbackDenied, authorize, error_body
from panestria.api.db import open_database, run_database
from panestria.api.routes.goals import _api
from panestria.contracts.activity import ActivityTimeline, ProjectActivity
from panestria.kernel.activity import project_activity
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.uow import UnitOfWork

router = APIRouter()


@router.get("/v1/activity", responses={200: {"model": ProjectActivity}})
async def activity(
    request: Request, before: str | None = Query(None, max_length=41), limit: int = Query(16, ge=1, le=32)
) -> JSONResponse:
    try:
        api = _api(request)
        actor = authorize(request, api)
        response = await run_database(_page, api.database_url, actor, before, limit)
        await asyncio.to_thread(authorize, request, api)
        return response
    except LoopbackDenied as exc:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code))


def _page(dsn: str, actor: Actor, before: str | None, limit: int) -> JSONResponse:
    try:
        with open_database(dsn) as c:
            c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            view = project_activity(UnitOfWork(c), actor, before=before, limit=limit)
        return JSONResponse(content=view.model_dump(mode="json"), headers={"Cache-Control": "no-store"})
    except KernelDenied as exc:
        return JSONResponse(status_code=404 if exc.code == "not_found" else 422, content=error_body(exc.code))
    except Exception:
        return JSONResponse(status_code=503, content=error_body("activity_unavailable"))


@router.get("/v1/activity/goals/{goal_id}/events", response_model=None, responses={200: {"model": ActivityTimeline}})
async def timeline(
    goal_id: str, request: Request, after: str = Query("0", max_length=19)
) -> JSONResponse | StreamingResponse:

    from panestria.api.db import DatabaseUnavailable
    from panestria.api.event_stream import _page, stream_events
    from panestria.kernel.event_replay import parse_cursor

    try:
        if str(UUID(goal_id)) != goal_id:
            raise KernelDenied("invalid_goal_id")
        api = _api(request)
        actor = authorize(request, api)
        cursor = parse_cursor(after)
        if request.headers.get("accept") == "text/event-stream":
            return await stream_events(request, api, goal_id, after, metadata_only=True)
        page = await asyncio.to_thread(_page, request, api, actor, goal_id, cursor, metadata_only=True)
        # A browser session may have been revoked after the read-only snapshot.
        await asyncio.to_thread(authorize, request, api)
        next_cursor = str(page.events[-1]["seq"]) if page.events else str(cursor)
        if page.resync:
            next_cursor = str(page.snapshot["cursor"])
        body = ActivityTimeline.model_validate_json(
            json.dumps(
                {
                    "owner_id": actor.owner_id,
                    "project_id": actor.project_id,
                    "events": page.events,
                    "snapshot": page.snapshot,
                    "resync": page.resync,
                    "next_cursor": next_cursor,
                }
            )
        )
        return JSONResponse(content=body.model_dump(mode="json"), headers={"Cache-Control": "no-store"})
    except LoopbackDenied as exc:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code))
    except KernelDenied as exc:
        return JSONResponse(status_code=404 if exc.code == "not_found" else 422, content=error_body(exc.code))
    except (ValueError, TypeError):
        return JSONResponse(status_code=422, content=error_body("invalid_timeline_request"))
    except DatabaseUnavailable:
        return JSONResponse(status_code=503, content=error_body("activity_unavailable"))
