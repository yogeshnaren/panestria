"""Offline Ask uses the local provider only; cancellation closes the active stream."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TypeVar

import psycopg
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from panestria.api.auth import GoalApi, LoopbackDenied, authorize, error_body, read_capped_body, reauthorize_mutation
from panestria.api.db import DatabaseUnavailable, open_database
from panestria.contracts.ask import AskSubmission
from panestria.contracts.hardware import HardwareManifest
from panestria.contracts.inference import InferenceResult, InferenceUnavailable
from panestria.inference.local import LocalProvider
from panestria.kernel.ask import AskService, PreparedAsk
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.uow import UnitOfWork
from panestria.resources.admission import RuntimeGovernor, admit
from panestria.resources.hardware import ProbeUnavailable

T = TypeVar("T")
router = APIRouter()
_SERVICE = AskService()


@dataclass
class AskApi:
    provider: LocalProvider
    probe: Callable[[], HardwareManifest]
    governor: RuntimeGovernor = field(default_factory=RuntimeGovernor)
    active: dict[str, asyncio.Task[InferenceResult]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.provider, LocalProvider):
            raise TypeError("Ask requires the registered local provider")


def _configured(request: Request) -> tuple[GoalApi, AskApi, Actor]:
    api, ask = getattr(request.app.state, "goal_api", None), getattr(request.app.state, "ask_api", None)
    if not isinstance(api, GoalApi) or not isinstance(ask, AskApi):
        raise LoopbackDenied("ask_not_configured", 503)
    return api, ask, authorize(request, api)


def _transaction(request: Request, api: GoalApi, operation: Callable[[UnitOfWork], T], *, auth: bool = True) -> T:
    try:
        with open_database(api.database_url) as connection:
            if auth:
                reauthorize_mutation(request, api, connection)
            return operation(UnitOfWork(connection))
    except psycopg.Error:
        raise DatabaseUnavailable from None


def _status(code: str) -> int:
    return {"not_found": 404, "idempotency_conflict": 409, "unauthorized": 401, "csrf_denied": 403}.get(code, 422)


@router.post("/v1/ask")
async def ask_question(request: Request) -> JSONResponse:
    prepared: PreparedAsk | None = None
    ticket, model_task = None, None
    client_disconnected = False
    try:
        api, ask, actor = _configured(request)
        raw = await read_capped_body(request)
        if isinstance(raw, JSONResponse):
            return raw
        try:
            submission = AskSubmission.model_validate_json(raw)
        except ValidationError:
            return JSONResponse(status_code=422, content=error_body("invalid_ask"))
        prepared = await asyncio.to_thread(_transaction, request, api, lambda u: _SERVICE.prepare(u, actor, submission))
        ticket = await ask.governor.acquire(wait_seconds=min(5.0, submission.deadline_seconds))
        resource_deadline = time.monotonic() + min(5.0, submission.deadline_seconds)
        while True:
            snapshot = await asyncio.to_thread(ask.probe)
            admission = admit(snapshot, gpu=ask.provider.gpu)
            if admission.decision == "PERMIT":
                break
            if admission.decision == "UNAVAILABLE" or time.monotonic() >= resource_deadline:
                raise InferenceUnavailable(admission.reasons[0])
            if await request.is_disconnected():
                client_disconnected = True
                raise asyncio.CancelledError()
            await asyncio.sleep(0.2)
        inference = await asyncio.to_thread(_transaction, request, api, lambda u: _SERVICE.claim(u, actor, prepared))
        model_task = asyncio.create_task(ask.provider.agenerate(inference))
        ask.active[submission.request_id] = model_task
        while not model_task.done():
            await asyncio.wait({model_task}, timeout=0.1)
            if not model_task.done() and await request.is_disconnected():
                client_disconnected = True
                model_task.cancel()
                raise asyncio.CancelledError()
        result = await model_task
        await asyncio.to_thread(
            _transaction, request, api, lambda u: _SERVICE.finish(u, actor, submission.request_id, result)
        )
        receipt = await asyncio.to_thread(
            _transaction, request, api, lambda u: _SERVICE.receipt(u, actor, submission.request_id)
        )
        return JSONResponse(status_code=200, content={**receipt, "text": result.text})
    except LoopbackDenied as exc:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code))
    except KernelDenied as exc:
        code = exc.code
        if code == "request_already_admitted":
            receipt = await asyncio.to_thread(
                _transaction, request, api, lambda u: _SERVICE.receipt(u, actor, submission.request_id)
            )
            return JSONResponse(status_code=200, content={**receipt, "replayed_receipt": True})
        if prepared:
            await asyncio.to_thread(
                _transaction,
                request,
                api,
                lambda u: _SERVICE.stop(
                    u,
                    actor,
                    prepared.submission.request_id,
                    cancelled=False,
                    code=code,
                ),
                auth=False,
            )
        return JSONResponse(status_code=_status(exc.code), content=error_body(exc.code))
    except InferenceUnavailable as exc:
        code = exc.code
        if prepared:
            await asyncio.to_thread(
                _transaction,
                request,
                api,
                lambda u: _SERVICE.stop(
                    u,
                    actor,
                    prepared.submission.request_id,
                    cancelled=False,
                    code=code,
                ),
                auth=False,
            )
        return JSONResponse(status_code=503, content=error_body(exc.code))
    except (DatabaseUnavailable, ProbeUnavailable, OSError):
        return JSONResponse(status_code=503, content=error_body("database_or_resource_unavailable"))
    except asyncio.CancelledError:
        if model_task:
            model_task.cancel()
            await asyncio.gather(model_task, return_exceptions=True)
        if prepared:
            await asyncio.shield(
                asyncio.to_thread(
                    _transaction,
                    request,
                    api,
                    lambda u: _SERVICE.stop(
                        u,
                        actor,
                        prepared.submission.request_id,
                        cancelled=True,
                        code="request_cancelled",
                    ),
                    auth=False,
                )
            )
        current = asyncio.current_task()
        if not client_disconnected and current is not None and current.cancelling() == 0:
            return JSONResponse(status_code=409, content=error_body("ask_cancelled"))
        raise
    finally:
        if prepared:
            ask.active.pop(prepared.submission.request_id, None)
        if ticket:
            ask.governor.release(ticket)


@router.get("/v1/ask/{request_id}")
async def ask_receipt(request_id: str, request: Request) -> JSONResponse:
    try:
        api, _ask, actor = _configured(request)
        receipt = await asyncio.to_thread(_transaction, request, api, lambda u: _SERVICE.receipt(u, actor, request_id))
        return JSONResponse(status_code=200, content=receipt)
    except LoopbackDenied as exc:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code))
    except KernelDenied as exc:
        return JSONResponse(status_code=_status(exc.code), content=error_body(exc.code))
    except DatabaseUnavailable:
        return JSONResponse(status_code=503, content=error_body("database_unavailable"))


@router.post("/v1/ask/{request_id}/cancel")
async def cancel_ask(request_id: str, request: Request) -> JSONResponse:
    try:
        api, ask, actor = _configured(request)
        raw = await read_capped_body(request)
        if isinstance(raw, JSONResponse):
            return raw
        try:
            valid = json.loads(raw) == {}
        except ValueError:
            valid = False
        if not valid:
            return JSONResponse(status_code=422, content=error_body("invalid_cancel"))
        state = await asyncio.to_thread(
            _transaction,
            request,
            api,
            lambda u: _SERVICE.stop(
                u,
                actor,
                request_id,
                cancelled=True,
                code="owner_cancelled",
            ),
        )
        if state == "CANCELLED" and (active := ask.active.get(request_id)):
            active.cancel()
        return JSONResponse(status_code=200, content={"request_id": request_id, "state": state})
    except LoopbackDenied as exc:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code))
    except KernelDenied as exc:
        return JSONResponse(status_code=_status(exc.code), content=error_body(exc.code))
    except DatabaseUnavailable:
        return JSONResponse(status_code=503, content=error_body("database_unavailable"))
