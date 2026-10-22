"""Explicit local PUBLIC staging only; same-transaction browser and policy fences."""

import asyncio

import psycopg
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from panestria.api.auth import GoalApi, LoopbackDenied, authorize, error_body, read_capped_body, reauthorize_mutation
from panestria.api.db import DatabaseUnavailable, open_database
from panestria.contracts.research_intake import ResearchIntakeSubmission, ResearchIntakeView, ResearchStagingView
from panestria.execution.research_intake import ResearchIntakeService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.repositories.policy import lock_project
from panestria.kernel.uow import UnitOfWork

router = APIRouter()


@router.get("/v1/mission/research/intake", responses={200: {"model": ResearchIntakeView}})
async def intake(request: Request) -> JSONResponse:
    return await asyncio.to_thread(_operation, request, None, None)


@router.post(
    "/v1/mission/research/questions",
    responses={200: {"model": ResearchStagingView}},
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": ResearchIntakeSubmission.model_json_schema()}},
        }
    },
)
async def stage(request: Request) -> JSONResponse:
    raw = await read_capped_body(request)
    if isinstance(raw, JSONResponse):
        return raw
    try:
        body = ResearchIntakeSubmission.model_validate_json(raw)
    except ValidationError:
        return JSONResponse(status_code=422, content=error_body("invalid_public_question"))
    return await asyncio.to_thread(_operation, request, body.goal_id, body)


@router.get("/v1/mission/research/questions/{goal_id}", responses={200: {"model": ResearchStagingView}})
async def inspect(goal_id: str, request: Request) -> JSONResponse:
    return await asyncio.to_thread(_operation, request, goal_id, None)


def _operation(request: Request, goal: str | None, body: ResearchIntakeSubmission | None) -> JSONResponse:
    try:
        api, service = getattr(request.app.state, "goal_api", None), getattr(request.app.state, "research_intake", None)
        if not isinstance(api, GoalApi) or not isinstance(service, ResearchIntakeService):
            raise KernelDenied("not_found")
        actor = authorize(request, api)
        if (actor.owner_id, actor.project_id) != (service.actor.owner_id, service.actor.project_id):
            raise KernelDenied("not_found")
        if body is not None:
            with open_database(api.database_url) as connection:
                uow = UnitOfWork(connection)
                lock_project(uow, actor)
                reauthorize_mutation(request, api, connection)
                goal = service.stage(uow, api.database_url, actor, body)
                reauthorize_mutation(request, api, connection)
        value = service.view if goal is None else service.inspect(api.database_url, actor, goal)
        authorize(request, api)  # expiry/revocation after protected I/O also hides the reply
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
    except (DatabaseUnavailable, psycopg.Error, ValueError, OSError):
        return JSONResponse(status_code=503, content=error_body("research_intake_unavailable"))
