"""Opt-in local plan staging; same-transaction session, project and policy fences."""

import asyncio

import psycopg
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from panestria.api.auth import GoalApi, LoopbackDenied, authorize, error_body, read_capped_body, reauthorize_mutation
from panestria.api.db import DatabaseUnavailable, open_database
from panestria.contracts.build_intake import BuildPlanAcceptance, BuildPlanStagingView, BuildPlanSubmission
from panestria.execution.build_intake import BuildIntakeService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.repositories.policy import lock_project
from panestria.kernel.uow import UnitOfWork

router = APIRouter()


@router.post(
    "/v1/mission/build/plans",
    responses={200: {"model": BuildPlanStagingView}},
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": BuildPlanSubmission.model_json_schema()}},
        }
    },
)
async def stage_plan(request: Request) -> JSONResponse:
    raw = await read_capped_body(request)
    if isinstance(raw, JSONResponse):
        return raw
    try:
        body = BuildPlanSubmission.model_validate_json(raw)
    except ValidationError:
        return JSONResponse(status_code=422, content=error_body("invalid_public_plan"))
    return await asyncio.to_thread(_operation, request, None, body)


@router.get("/v1/mission/build/plans/{plan_id}", responses={200: {"model": BuildPlanStagingView}})
async def inspect_plan(plan_id: str, request: Request) -> JSONResponse:
    return await asyncio.to_thread(_operation, request, plan_id, None)


@router.post(
    "/v1/mission/build/plans/{plan_id}/accept",
    responses={200: {"model": BuildPlanStagingView}},
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": BuildPlanAcceptance.model_json_schema()}},
        }
    },
)
async def accept_plan(plan_id: str, request: Request) -> JSONResponse:
    service = getattr(request.app.state, "build_intake", None)
    if not isinstance(service, BuildIntakeService) or not service.allow_acceptance:
        return JSONResponse(status_code=404, content=error_body("not_found"))
    raw = await read_capped_body(request)
    if isinstance(raw, JSONResponse):
        return raw
    try:
        body = BuildPlanAcceptance.model_validate_json(raw)
    except ValidationError:
        return JSONResponse(status_code=422, content=error_body("invalid_plan_acceptance"))
    return await asyncio.to_thread(_operation, request, plan_id, None, body)


def _operation(
    request: Request,
    identifier: str | None,
    body: BuildPlanSubmission | None,
    acceptance: BuildPlanAcceptance | None = None,
) -> JSONResponse:
    try:
        api, service = getattr(request.app.state, "goal_api", None), getattr(request.app.state, "build_intake", None)
        if not isinstance(api, GoalApi) or not isinstance(service, BuildIntakeService):
            raise KernelDenied("not_found")
        actor = authorize(request, api)
        if body is not None or acceptance is not None:
            with open_database(api.database_url) as connection:
                uow = UnitOfWork(connection)
                lock_project(uow, actor)
                reauthorize_mutation(request, api, connection)
                if body is not None:
                    identifier = service.stage(uow, actor, body)
                elif acceptance is not None and identifier is not None:
                    identifier = service.accept(uow, actor, identifier, acceptance)
                else:
                    raise KernelDenied("not_found")
                reauthorize_mutation(request, api, connection)
        if identifier is None:
            raise KernelDenied("not_found")
        with open_database(api.database_url) as connection:
            value = service.inspect(UnitOfWork(connection), actor, identifier)
            connection.rollback()  # Protected inspection never commits observation writes.
        if acceptance is not None:
            value = value.model_copy(update={"operation": "PLAN_ACCEPTED_NO_EXECUTION"})
        authorize(request, api)
        return JSONResponse(value.model_dump(mode="json"), headers={"Cache-Control": "no-store"})
    except LoopbackDenied as exc:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code))
    except KernelDenied as exc:
        status = (
            401
            if exc.code == "unauthorized"
            else 403
            if exc.code in {"csrf_denied", "origin_denied", "origin_required"}
            else 404
            if exc.code == "not_found"
            else 409
        )
        return JSONResponse(status_code=status, content=error_body(exc.code))
    except (ValueError, ValidationError):
        return JSONResponse(status_code=422, content=error_body("invalid_public_plan"))
    except (DatabaseUnavailable, psycopg.Error, OSError):
        return JSONResponse(status_code=503, content=error_body("build_intake_unavailable"))
