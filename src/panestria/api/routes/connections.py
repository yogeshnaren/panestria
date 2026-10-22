"""Owner-only declaration review. Approval never connects or dispatches a tool."""

from __future__ import annotations

import asyncio
from dataclasses import asdict

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from panestria.api.auth import GoalApi, LoopbackDenied, authorize, error_body, read_capped_body
from panestria.api.db import DatabaseUnavailable
from panestria.api.routes.ask import _transaction
from panestria.contracts.connections import ConnectionScopeView, DecideReview, SubmitReview
from panestria.contracts.connections import parse_connection_contract as _parse
from panestria.kernel.connections import ConnectionReview, ConnectionReviewService
from panestria.kernel.errors import KernelDenied

router = APIRouter(prefix="/v2/connections")
_SERVICE = ConnectionReviewService()
_HEADERS = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff"}


def _api(request: Request) -> GoalApi:
    if (
        getattr(request.app.state, "connection_terminal_only", False)
        and getattr(request.app.state, "browser_access", None) is not None
    ):
        raise LoopbackDenied("connection_terminal_mode_only", 403)
    value = getattr(request.app.state, "goal_api", None)
    if not isinstance(value, GoalApi):
        raise LoopbackDenied("connections_not_configured", 503)
    return value


def _response(body: dict[str, object], status: int = 200) -> JSONResponse:
    return JSONResponse(content={"schema_version": 1, **body}, status_code=status, headers=_HEADERS)


def _denied(error: Exception) -> JSONResponse:
    if isinstance(error, LoopbackDenied):
        return _response(error_body(error.code), error.status_code)
    if isinstance(error, DatabaseUnavailable):
        return _response(error_body("database_unavailable"), 503)
    if isinstance(error, KernelDenied):
        status = {
            "not_found": 404,
            "unauthorized": 401,
            "csrf_denied": 403,
            "policy_mismatch": 409,
            "connection_version_conflict": 409,
            "connection_proposal_conflict": 409,
            "decision_conflict": 409,
            "digest_mismatch": 409,
            "connection_review_expired": 409,
            "connection_already_revoked": 409,
            "connection_review_corrupt": 503,
            "connection_revision_corrupt": 503,
        }.get(error.code, 422)
        return _response(error_body(error.code), status)
    return _response(error_body("invalid_connection_request"), 422)


def _review(view: ConnectionReview) -> dict[str, object]:
    return {
        "proposal_id": view.proposal_id,
        "grant_id": view.grant_id,
        "expected_version": view.expected_version,
        "effect_digest": view.effect_digest,
        "operation": view.operation,
        "policy_ref": view.policy_ref,
        "review_expires_at": view.expires_at.isoformat(),
        "manifest": view.manifest.model_dump(mode="json"),
        "state": view.state,
        "replayed": view.replayed,
        "authority": "DECLARATION_ONLY",
        "conformance_status": "UNVERIFIED",
        "runtime_available": False,
    }


@router.get("/scope", responses={200: {"model": ConnectionScopeView}})
async def connection_scope(request: Request) -> JSONResponse:
    try:
        api = _api(request)
        actor = authorize(request, api)
        view = await asyncio.to_thread(_transaction, request, api, lambda u: _SERVICE.scope(u, actor))
        return _response(view.model_dump(mode="json"))
    except (LoopbackDenied, KernelDenied, DatabaseUnavailable) as error:
        return _denied(error)


@router.post("/reviews")
async def propose_connection(request: Request) -> JSONResponse:
    try:
        api = _api(request)
        actor = authorize(request, api)
        raw = await read_capped_body(request)
        if isinstance(raw, JSONResponse):
            raw.headers.update(_HEADERS)
            return raw
        submitted = _parse(SubmitReview, raw)
        view = await asyncio.to_thread(
            _transaction,
            request,
            api,
            lambda u: _SERVICE.propose(u, actor, submitted.task_id, submitted.change),
        )
        return _response(_review(view), 200 if view.replayed else 201)
    except (LoopbackDenied, KernelDenied, DatabaseUnavailable, ValidationError, ValueError, RecursionError) as error:
        return _denied(error)


@router.get("/reviews/{proposal_id}")
async def preview_connection(proposal_id: str, request: Request) -> JSONResponse:
    try:
        api = _api(request)
        actor = authorize(request, api)
        view = await asyncio.to_thread(_transaction, request, api, lambda u: _SERVICE.preview(u, actor, proposal_id))
        return _response(_review(view))
    except (LoopbackDenied, KernelDenied, DatabaseUnavailable) as error:
        return _denied(error)


@router.post("/reviews/{proposal_id}/decision")
async def decide_connection(proposal_id: str, request: Request) -> JSONResponse:
    try:
        api = _api(request)
        actor = authorize(request, api)
        raw = await read_capped_body(request)
        if isinstance(raw, JSONResponse):
            raw.headers.update(_HEADERS)
            return raw
        decision = _parse(DecideReview, raw)
        receipt = await asyncio.to_thread(
            _transaction,
            request,
            api,
            lambda u: _SERVICE.decide(u, actor, proposal_id, decision.effect_digest, decision.decision),
        )
        # No scheduler kick, root enrollment, conformance validation, native
        # client/provider call or tool invocation follows an owner decision.
        return _response({**asdict(receipt), "conformance_status": "UNVERIFIED", "runtime_available": False})
    except (LoopbackDenied, KernelDenied, DatabaseUnavailable, ValidationError, ValueError, RecursionError) as error:
        return _denied(error)


@router.get("/grants/{grant_id}")
async def read_connection(grant_id: str, request: Request) -> JSONResponse:
    try:
        api = _api(request)
        actor = authorize(request, api)
        view = await asyncio.to_thread(_transaction, request, api, lambda u: _SERVICE.current(u, actor, grant_id))
        return _response(
            {
                "grant_id": view.grant_id,
                "version": view.version,
                "state": view.state,
                "policy_ref": view.policy_ref,
                "policy_status": view.policy_status,
                "manifest": view.manifest.model_dump(mode="json"),
                "authority": view.authority,
                "conformance_status": view.conformance_status,
                "runtime_available": False,
            }
        )
    except (LoopbackDenied, KernelDenied, DatabaseUnavailable) as error:
        return _denied(error)
