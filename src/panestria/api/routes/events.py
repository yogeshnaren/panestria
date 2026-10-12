"""Scoped event replay. Sequence values are decimal strings."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from panestria.api.auth import GoalApi, LoopbackDenied, authorize, error_body
from panestria.api.db import DatabaseUnavailable, open_database
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import GoalService
from panestria.kernel.uow import UnitOfWork

router = APIRouter()
_SERVICE = GoalService()


def _parse_seq(value: str) -> int:
    if value == "0" or (value.isdigit() and not value.startswith("0")):
        return int(value)
    raise ValueError(value)


@router.get("/v1/goals/{goal_id}/events")
def read_events(goal_id: str, request: Request, after: str = "0", limit: int = 50) -> JSONResponse:
    try:
        api = getattr(request.app.state, "goal_api", None)
        if not isinstance(api, GoalApi):
            raise LoopbackDenied("not_configured", 503)
        actor = authorize(request, api)
        cursor = _parse_seq(after)
    except LoopbackDenied as exc:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code))
    except ValueError:
        return JSONResponse(status_code=422, content=error_body("invalid_cursor"))
    if not 1 <= limit <= 100:
        return JSONResponse(status_code=422, content=error_body("invalid_limit"))
    try:
        connection = open_database(api.database_url)
    except DatabaseUnavailable:
        return JSONResponse(status_code=503, content=error_body("database_unavailable"))
    try:
        try:
            rows = _SERVICE.events(UnitOfWork(connection), actor, goal_id, cursor, limit)
        except KernelDenied as exc:
            connection.rollback()
            status = 404 if exc.code == "not_found" else 422
            return JSONResponse(status_code=status, content=error_body(exc.code))
        connection.rollback()
    finally:
        connection.close()
    return JSONResponse(
        status_code=200,
        content={"events": [{"seq": str(seq), "kind": kind, "payload": payload} for seq, kind, payload in rows]},
    )
