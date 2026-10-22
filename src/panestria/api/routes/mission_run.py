"""Explicit foreground start/status/withdrawal, fenced by the committing session."""

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from panestria.api.auth import LoopbackDenied, authorize, error_body, read_capped_body, reauthorize_mutation
from panestria.api.db import open_database
from panestria.api.routes.goals import _api
from panestria.contracts.plan_run import PlanRunCancellation, PlanRunIntent, PlanRunView
from panestria.execution.mission_run import MissionRunService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.plan_lifecycle import PlanLifecycle
from panestria.kernel.repositories.policy import lock_project
from panestria.kernel.scheduler import FLEET_LOCK
from panestria.kernel.uow import UnitOfWork

router = APIRouter()


@router.get("/v1/mission/build/plans/{plan_id}/run", responses={200: {"model": PlanRunView}})
async def inspect_run(plan_id: str, request: Request) -> JSONResponse:
    return await asyncio.to_thread(_operation, request, plan_id, None)


@router.post(
    "/v1/mission/build/plans/{plan_id}/run",
    responses={200: {"model": PlanRunView}},
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": PlanRunIntent.model_json_schema()}},
        }
    },
)
async def start_run(plan_id: str, request: Request) -> JSONResponse:
    return await _body(request, plan_id, PlanRunIntent)


@router.post(
    "/v1/mission/build/plans/{plan_id}/run/cancel",
    responses={200: {"model": PlanRunView}},
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": PlanRunCancellation.model_json_schema()}},
        }
    },
)
async def cancel_run(plan_id: str, request: Request) -> JSONResponse:
    return await _body(request, plan_id, PlanRunCancellation)


async def _body(request: Request, plan_id: str, model: type[PlanRunIntent] | type[PlanRunCancellation]) -> JSONResponse:
    raw = await read_capped_body(request)
    if isinstance(raw, JSONResponse):
        return raw
    try:
        body = model.model_validate_json(raw)
    except ValidationError:
        return JSONResponse(status_code=422, content=error_body("invalid_run_intent"))
    return await asyncio.to_thread(_operation, request, plan_id, body)


def _operation(request: Request, plan_id: str, body: PlanRunIntent | PlanRunCancellation | None) -> JSONResponse:
    try:
        service = getattr(request.app.state, "mission_run", None)
        if not isinstance(service, MissionRunService):
            raise KernelDenied("not_found")
        api = _api(request)
        actor = authorize(request, api)
        with open_database(api.database_url) as c:
            uow = UnitOfWork(c)
            if body is None:
                uow.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            if body is not None:
                # Match the canonical scheduler/cancellation lock order.
                if isinstance(body, PlanRunCancellation):
                    uow.execute("SELECT pg_advisory_xact_lock(%s,%s)", FLEET_LOCK)
                lock_project(uow, actor)
                reauthorize_mutation(request, api, c)
            if isinstance(body, PlanRunIntent):
                view = service.store.request(uow, actor, plan_id, body, service.configuration)
            else:
                view = service.store.inspect(uow, actor, plan_id, service.configuration)
                if isinstance(body, PlanRunCancellation):
                    if (
                        view.record is None
                        or view.record.intent.request_id != body.request_id
                        or view.plan_sha256 != body.plan_sha256
                    ):
                        raise KernelDenied("original_run_request_required")
                    PlanLifecycle().cancel(uow, actor, plan_id, body.plan_sha256)
            if body is not None:
                reauthorize_mutation(request, api, c)
            else:
                c.rollback()
        # Only an acknowledged request commit may wake the finite controller.
        # Reads, startup, acceptance, polling and other modes never wake it.
        if isinstance(body, PlanRunIntent) and view.state == "REQUESTED":
            service.wake(plan_id, body.request_id)
        elif isinstance(body, PlanRunCancellation):
            service.signal_cancel(plan_id)
        with open_database(api.database_url) as c:
            view = service.store.inspect(UnitOfWork(c), actor, plan_id, service.configuration)
            c.rollback()
        authorize(request, api)
        return JSONResponse(service.observe(view).model_dump(mode="json"), headers={"Cache-Control": "no-store"})
    except KernelDenied as exc:
        status = (
            404
            if exc.code == "not_found"
            else 401
            if exc.code == "unauthorized"
            else (403 if exc.code in {"csrf_denied", "origin_denied", "origin_required"} else 409)
        )
        return JSONResponse(status_code=status, content=error_body("run_unconfirmed"))
    except LoopbackDenied as exc:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code))
    except Exception:
        return JSONResponse(status_code=503, content=error_body("run_unavailable"))
