"""Scoped approval preview and one locked decision. The decision does not dispatch."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from panestria.api.auth import GoalApi, LoopbackDenied, authorize, error_body, read_capped_body, reauthorize_mutation
from panestria.api.db import DatabaseUnavailable, open_database, run_database
from panestria.api.routes.goals import _api, _kick, _unavailable
from panestria.api.views import ApprovalList, ApprovalPreviewBody, DecisionReceipt
from panestria.kernel.approvals import ApprovalService, ApprovalView
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.uow import UnitOfWork

router = APIRouter()
_SERVICE = ApprovalService()
_STATUSES = {
    "not_found": 404,
    "unauthorized": 401,
    "csrf_denied": 403,
    "origin_required": 403,
    "origin_denied": 403,
    "policy_mismatch": 409,
    "actor_mismatch": 403,
    "idempotency_conflict": 409,
    "digest_mismatch": 409,
    "decision_conflict": 409,
    "version_conflict": 409,
    "expired": 409,
    "unknown_check": 409,
    "not_approved": 409,
}


def _denied(exc: KernelDenied) -> JSONResponse:
    return JSONResponse(status_code=_STATUSES.get(exc.code, 422), content=error_body(exc.code))


@router.get("/v1/approvals", responses={200: {"model": ApprovalList}})
def list_approvals(request: Request, limit: int = 50) -> JSONResponse:
    try:
        api = _api(request)
        actor = authorize(request, api)
    except LoopbackDenied as exc:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code))
    if not 1 <= limit <= 100:
        return JSONResponse(status_code=422, content=error_body("invalid_limit"))
    try:
        connection = open_database(api.database_url)
    except DatabaseUnavailable:
        return _unavailable()
    try:
        try:
            listed = _SERVICE.list_pending(UnitOfWork(connection), actor, limit)
        except KernelDenied as exc:
            connection.rollback()
            return _denied(exc)
        connection.rollback()
    finally:
        connection.close()
    return JSONResponse(status_code=200, headers={"Cache-Control": "no-store"}, content={"approvals": listed})


@router.get("/v1/approvals/{approval_id}", responses={200: {"model": ApprovalPreviewBody}})
def read_approval(approval_id: str, request: Request) -> JSONResponse:
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
            view = _SERVICE.preview(UnitOfWork(connection), actor, approval_id)
        except KernelDenied as exc:
            connection.rollback()
            return _denied(exc)
        connection.rollback()
    finally:
        connection.close()
    return JSONResponse(status_code=200, content=_view_body(view))


@router.post("/v1/approvals/{approval_id}/decision", responses={200: {"model": DecisionReceipt}})
async def decide_approval(approval_id: str, request: Request) -> JSONResponse:
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
        return JSONResponse(status_code=422, content=error_body("invalid_decision"))
    if not isinstance(document, dict):
        return JSONResponse(status_code=422, content=error_body("invalid_decision"))
    return await run_database(_decide, request, api, actor, approval_id, document, key)


def _decide(
    request: Request,
    api: GoalApi,
    actor: Actor,
    approval_id: str,
    document: dict[str, Any],
    key: str,
) -> JSONResponse:
    if set(document) != {"effect_digest", "expected_version", "decision"}:
        return JSONResponse(status_code=422, content=error_body("invalid_decision"))
    digest = document.get("effect_digest")
    version = document.get("expected_version")
    decision = document.get("decision")
    if not isinstance(digest, str) or not isinstance(version, int) or isinstance(version, bool):
        return JSONResponse(status_code=422, content=error_body("invalid_decision"))
    if not isinstance(decision, str):
        return JSONResponse(status_code=422, content=error_body("invalid_decision"))
    found: tuple[object, ...] | None = None
    try:
        connection = open_database(api.database_url)
    except DatabaseUnavailable:
        return _unavailable()
    try:
        try:
            reauthorize_mutation(request, api, connection)
            receipt = _SERVICE.decide(UnitOfWork(connection), actor, approval_id, digest, version, decision, key)
            found = connection.execute(
                "SELECT goal_id::text FROM panestria.approval_request WHERE id = %s",
                (approval_id,),
            ).fetchone()
        except KernelDenied as exc:
            connection.rollback()
            return _denied(exc)
        connection.commit()
    finally:
        connection.close()
    if found is not None:
        _kick(request, str(found[0]))
    return JSONResponse(
        status_code=200,
        content={
            "approval_id": receipt.approval_id,
            "state": receipt.state,
            "effect_digest": receipt.effect_digest,
            "row_version": receipt.row_version,
            "replayed": receipt.replayed,
        },
    )


def _view_body(view: ApprovalView) -> dict[str, object]:
    return {
        "approval_id": view.approval_id,
        "effect_digest": view.effect_digest,
        "expected_version": view.expected_version,
        "state": view.state,
        "continuation_kind": view.continuation_kind,
        "preview": view.preview,
    }
