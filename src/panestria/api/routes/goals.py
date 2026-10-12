"""Scoped goal submit and read. The route commits only after the service returns."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from panestria.api.auth import GoalApi, LoopbackDenied, authorize, error_body, read_capped_body
from panestria.api.db import DatabaseUnavailable, open_database
from panestria.api.views import CancelResult, GoalStatus, GoalSubmission
from panestria.kernel.cancellation import CancellationService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor, GoalService
from panestria.kernel.uow import UnitOfWork

router = APIRouter()
_SERVICE = GoalService()
_CANCEL = CancellationService()
_STATUSES = {"not_found": 404, "idempotency_conflict": 409, "version_conflict": 409}


def _api(request: Request) -> GoalApi:
    api = getattr(request.app.state, "goal_api", None)
    if not isinstance(api, GoalApi):
        raise LoopbackDenied("not_configured", 503)
    return api


def _denied(exc: KernelDenied) -> JSONResponse:
    status = _STATUSES.get(exc.code, 422)
    return JSONResponse(status_code=status, content=error_body(exc.code))


@router.post("/v1/goals", responses={202: {"model": GoalSubmission}})
async def submit_goal(request: Request) -> JSONResponse:
    try:
        api = _api(request)
        actor = authorize(request, api)
    except LoopbackDenied as exc:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code))
    raw = await read_capped_body(request)
    if isinstance(raw, JSONResponse):
        return raw
    key = request.headers.get("idempotency-key", "")
    if key == "" or len(key) > 128:
        return JSONResponse(status_code=400, content=error_body("missing_idempotency_key"))
    try:
        document = json.loads(raw)
    except json.JSONDecodeError:
        return JSONResponse(status_code=422, content=error_body("invalid_contract"))
    if not isinstance(document, dict):
        return JSONResponse(status_code=422, content=error_body("invalid_contract"))
    response = _submit(api, actor, document, key)
    if response.status_code == 202:
        _kick(request, str(json.loads(bytes(response.body))["goal_id"]))
    return response


def _submit(api: GoalApi, actor: Actor, document: dict[str, Any], key: str) -> JSONResponse:
    try:
        connection = open_database(api.database_url)
    except DatabaseUnavailable:
        return _unavailable()
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


@router.get("/v1/goals/{goal_id}", responses={200: {"model": GoalStatus}})
def read_goal(goal_id: str, request: Request) -> JSONResponse:
    try:
        api = _api(request)
        actor = authorize(request, api)
    except LoopbackDenied as exc:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code))
    try:
        connection = open_database(api.database_url)
    except DatabaseUnavailable:
        return _unavailable()
    try:
        try:
            view = _SERVICE.get(UnitOfWork(connection), actor, goal_id)
            version = connection.execute(
                "SELECT row_version FROM panestria.task WHERE goal_id = %s ORDER BY id LIMIT 1",
                (goal_id,),
            ).fetchone()
        except KernelDenied as exc:
            connection.rollback()
            return _denied(exc)
        connection.rollback()
    finally:
        connection.close()
    task_version = 0 if version is None else int(version[0])
    return JSONResponse(
        status_code=200,
        content={"goal_id": view.goal_id, "status": view.status, "task_version": task_version},
    )


@router.post("/v1/goals/{goal_id}/cancel", responses={200: {"model": CancelResult}})
async def cancel_goal(goal_id: str, request: Request) -> JSONResponse:
    try:
        api = _api(request)
        actor = authorize(request, api)
    except LoopbackDenied as exc:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code))
    raw = await read_capped_body(request)
    if isinstance(raw, JSONResponse):
        return raw
    try:
        document = json.loads(raw)
    except json.JSONDecodeError:
        return JSONResponse(status_code=422, content=error_body("invalid_contract"))
    if not isinstance(document, dict):
        return JSONResponse(status_code=422, content=error_body("invalid_contract"))
    version = document.get("expected_version")
    reason = document.get("reason")
    if not isinstance(version, int) or isinstance(version, bool) or not isinstance(reason, str):
        return JSONResponse(status_code=422, content=error_body("invalid_contract"))
    try:
        connection = open_database(api.database_url)
    except DatabaseUnavailable:
        return _unavailable()
    try:
        try:
            receipt = _CANCEL.cancel(UnitOfWork(connection), actor, goal_id, version, reason)
        except KernelDenied as exc:
            connection.rollback()
            return _denied(exc)
        connection.commit()
    finally:
        connection.close()
    return JSONResponse(
        status_code=200,
        content={
            "goal_id": receipt.goal_id,
            "goal_status": receipt.goal_status,
            "task_state": receipt.task_state,
            "task_version": receipt.task_version,
        },
    )


def _kick(request: Request, goal_id: str) -> None:
    driver = getattr(request.app.state, "journey", None)
    submit = getattr(driver, "submit", None)
    if callable(submit):
        submit(goal_id)


def _unavailable() -> JSONResponse:
    return JSONResponse(status_code=503, content=error_body("database_unavailable"))
