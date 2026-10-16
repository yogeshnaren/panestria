"""Owner quota metadata input/read. No provider scraping or background dispatch."""

from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import Field, StrictInt, ValidationError

from panestria.api.auth import GoalApi, LoopbackDenied, authorize, error_body, read_capped_body
from panestria.api.db import DatabaseUnavailable
from panestria.api.routes.ask import _transaction
from panestria.contracts.quota import QuotaContract, QuotaId, QuotaObservation, QuotaScope
from panestria.kernel.errors import KernelDenied
from panestria.kernel.quota import QuotaService, QuotaView

router = APIRouter(prefix="/v2/quota")
_SERVICE = QuotaService()
_HEADERS = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff"}


class OwnerQuotaObservation(QuotaObservation):
    source: Literal["OWNER_REPORTED", "UNKNOWN"]
    source_sha256: None = None


class SubmitQuota(QuotaContract):
    schema_version: StrictInt = Field(ge=1, le=1)
    task_id: QuotaId
    observation: OwnerQuotaObservation


class QueryQuota(QuotaContract):
    schema_version: StrictInt = Field(ge=1, le=1)
    scope: QuotaScope


def _response(content: dict[str, object], status: int = 200) -> JSONResponse:
    return JSONResponse(content={"schema_version": 1, **content}, status_code=status, headers=_HEADERS)


def _body(view: QuotaView) -> dict[str, object]:
    return {
        "observation": view.observation.model_dump(mode="json"),
        "recorded_at": view.recorded_at.isoformat(),
        "evaluated_at": view.evaluated_at.isoformat(),
        "freshness": view.freshness,
        "confidence": view.confidence,
        "effective_remaining": view.effective_remaining,
        "replayed": view.replayed,
        "authority": view.authority,
    }


def _denied(exc: Exception) -> JSONResponse:
    if isinstance(exc, LoopbackDenied):
        return _response(error_body(exc.code), exc.status_code)
    if isinstance(exc, KernelDenied):
        return _response(
            error_body(exc.code),
            {"not_found": 404, "quota_observation_conflict": 409, "unauthorized": 401, "csrf_denied": 403}.get(
                exc.code, 422
            ),
        )
    if isinstance(exc, DatabaseUnavailable):
        return _response(error_body("database_unavailable"), 503)
    return _response(error_body("invalid_quota_request"), 422)


def _api(request: Request) -> GoalApi:
    api = getattr(request.app.state, "goal_api", None)
    if not isinstance(api, GoalApi):
        raise LoopbackDenied("quota_not_configured", 503)
    return api


@router.post("/observations")
async def submit_observation(request: Request) -> JSONResponse:
    try:
        api = _api(request)
        actor = authorize(request, api)
        raw = await read_capped_body(request)
        if isinstance(raw, JSONResponse):
            raw.headers.update(_HEADERS)
            return raw
        submitted = SubmitQuota.model_validate_json(raw)
        # Revalidate as the base closed contract at the trusted service boundary.
        observation = QuotaObservation.model_validate_json(submitted.observation.model_dump_json())
        view = await asyncio.to_thread(
            _transaction, request, api, lambda u: _SERVICE.record(u, actor, submitted.task_id, observation)
        )
        return _response(_body(view), 200 if view.replayed else 201)
    except (LoopbackDenied, KernelDenied, ValidationError, DatabaseUnavailable) as exc:
        return _denied(exc)


@router.get("/observations/{observation_id}")
async def read_observation(observation_id: str, request: Request) -> JSONResponse:
    try:
        api = _api(request)
        actor = authorize(request, api)
        view = await asyncio.to_thread(_transaction, request, api, lambda u: _SERVICE.read(u, actor, observation_id))
        return _response(_body(view))
    except (LoopbackDenied, KernelDenied, ValidationError, DatabaseUnavailable) as exc:
        return _denied(exc)


@router.post("/current")
async def current_quota(request: Request) -> JSONResponse:
    try:
        api = _api(request)
        actor = authorize(request, api)
        raw = await read_capped_body(request)
        if isinstance(raw, JSONResponse):
            raw.headers.update(_HEADERS)
            return raw
        query = QueryQuota.model_validate_json(raw)
        views = await asyncio.to_thread(_transaction, request, api, lambda u: _SERVICE.latest(u, actor, query.scope))
        return _response({"lanes": [_body(view) for view in views], "authority": "OBSERVATION_ONLY"})
    except (LoopbackDenied, KernelDenied, ValidationError, DatabaseUnavailable) as exc:
        return _denied(exc)
