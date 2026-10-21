"""Authenticated content-free project activity, without model or mutation routes."""

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from panestria.api.auth import LoopbackDenied, authorize, error_body
from panestria.api.db import open_database, run_database
from panestria.api.routes.goals import _api
from panestria.contracts.activity import ProjectActivity
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
        return await run_database(_page, api.database_url, actor, before, limit)
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
