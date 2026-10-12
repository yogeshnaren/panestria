"""Scoped goal submit and read. The route commits only after the service returns."""

from __future__ import annotations

import json
from typing import Any

import psycopg
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from panestria.api.auth import MAX_BODY_BYTES, GoalApi, LoopbackDenied, authorize, error_body
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor, GoalService
from panestria.kernel.uow import UnitOfWork

router = APIRouter()
_SERVICE = GoalService()
_STATUSES = {"not_found": 404, "idempotency_conflict": 409}


def _api(request: Request) -> GoalApi:
    api = getattr(request.app.state, "goal_api", None)
    if not isinstance(api, GoalApi):
        raise LoopbackDenied("not_configured", 503)
    return api


def _denied(exc: KernelDenied) -> JSONResponse:
    status = _STATUSES.get(exc.code, 422)
    return JSONResponse(status_code=status, content=error_body(exc.code))


@router.post("/v1/goals")
async def submit_goal(request: Request) -> JSONResponse:
    try:
        api = _api(request)
        actor = authorize(request, api)
    except LoopbackDenied as exc:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code))
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        return JSONResponse(status_code=413, content=error_body("body_too_large"))
    key = request.headers.get("idempotency-key", "")
    if key == "" or len(key) > 128:
        return JSONResponse(status_code=400, content=error_body("missing_idempotency_key"))
    try:
        document = json.loads(raw)
    except json.JSONDecodeError:
        return JSONResponse(status_code=422, content=error_body("invalid_contract"))
    if not isinstance(document, dict):
        return JSONResponse(status_code=422, content=error_body("invalid_contract"))
    return _submit(api, actor, document, key)


def _submit(api: GoalApi, actor: Actor, document: dict[str, Any], key: str) -> JSONResponse:
    connection = psycopg.connect(api.database_url)
    try:
        try:
            receipt = _SERVICE.submit(UnitOfWork(connection), actor, document, key)
        except KernelDenied as exc:
            connection.rollback()
            return _denied(exc)
        connection.commit()
    finally:
        connection.close()
    return JSONResponse(
        status_code=202,
        content={
            "goal_id": receipt.goal_id,
            "contract_version": receipt.contract_version,
            "contract_sha256": receipt.contract_sha256,
            "replayed": receipt.replayed,
        },
    )


@router.get("/v1/goals/{goal_id}")
def read_goal(goal_id: str, request: Request) -> JSONResponse:
    try:
        api = _api(request)
        actor = authorize(request, api)
    except LoopbackDenied as exc:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code))
    connection = psycopg.connect(api.database_url)
    try:
        try:
            view = _SERVICE.get(UnitOfWork(connection), actor, goal_id)
        except KernelDenied as exc:
            connection.rollback()
            return _denied(exc)
        connection.rollback()
    finally:
        connection.close()
    return JSONResponse(status_code=200, content={"goal_id": view.goal_id, "status": view.status})
