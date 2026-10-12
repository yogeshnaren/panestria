"""Scoped approval preview and one locked decision. The decision does not dispatch."""

from __future__ import annotations

import json
from typing import Any

import psycopg
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from panestria.api.auth import MAX_BODY_BYTES, GoalApi, LoopbackDenied, authorize, error_body
from panestria.api.routes.goals import _api
from panestria.kernel.approvals import ApprovalService, ApprovalView
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.uow import UnitOfWork

router = APIRouter()
_SERVICE = ApprovalService()
_STATUSES = {
    "not_found": 404,
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


@router.get("/v1/approvals/{approval_id}")
def read_approval(approval_id: str, request: Request) -> JSONResponse:
    try:
        api = _api(request)
        actor = authorize(request, api)
    except LoopbackDenied as exc:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code))
    connection = psycopg.connect(api.database_url)
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


@router.post("/v1/approvals/{approval_id}/decision")
async def decide_approval(approval_id: str, request: Request) -> JSONResponse:
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
        return JSONResponse(status_code=422, content=error_body("invalid_decision"))
    if not isinstance(document, dict):
        return JSONResponse(status_code=422, content=error_body("invalid_decision"))
    return _decide(api, actor, approval_id, document, key)


def _decide(api: GoalApi, actor: Actor, approval_id: str, document: dict[str, Any], key: str) -> JSONResponse:
    digest = document.get("effect_digest")
    version = document.get("expected_version")
    decision = document.get("decision")
    if not isinstance(digest, str) or not isinstance(version, int) or isinstance(version, bool):
        return JSONResponse(status_code=422, content=error_body("invalid_decision"))
    if not isinstance(decision, str):
        return JSONResponse(status_code=422, content=error_body("invalid_decision"))
    connection = psycopg.connect(api.database_url)
    try:
        try:
            receipt = _SERVICE.decide(UnitOfWork(connection), actor, approval_id, digest, version, decision, key)
        except KernelDenied as exc:
            connection.rollback()
            return _denied(exc)
        connection.commit()
    finally:
        connection.close()
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
