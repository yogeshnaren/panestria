"""Canonical memory surfaces reuse scoped transactions and exact owner review."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import asdict
from typing import TypeVar
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from panestria.api.auth import LoopbackDenied, error_body, read_capped_body
from panestria.api.db import DatabaseUnavailable
from panestria.api.routes.ask import _configured, _status, _transaction
from panestria.api.routes.memory import Correction, ReviewDecision, Suppression
from panestria.contracts.classification import resolve_classification
from panestria.contracts.memory import MemorySubmissionV2
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.uow import UnitOfWork
from panestria.memory.canonical import CanonicalMemoryView
from panestria.memory.reclassification import ReclassificationService
from panestria.memory.service import MemoryService

router = APIRouter(prefix="/v2")
_SERVICE, _VIEW, _REVIEWS = MemoryService(), CanonicalMemoryView(), ReclassificationService()
M = TypeVar("M", bound=BaseModel)


class CorrectionV2(Correction):
    document: MemorySubmissionV2


async def _read(request: Request, operation: Callable[[UnitOfWork, Actor], dict[str, object]]) -> JSONResponse:
    try:
        api, _ask, actor = _configured(request)
        result = await asyncio.to_thread(_transaction, request, api, lambda u: operation(u, actor))
        return JSONResponse(status_code=200, content={"schema_version": 2, **result})
    except LoopbackDenied as exc:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code))
    except KernelDenied as exc:
        return JSONResponse(status_code=_status(exc.code), content=error_body(exc.code))
    except DatabaseUnavailable:
        return JSONResponse(status_code=503, content=error_body("database_unavailable"))


async def _write(
    request: Request,
    model: type[M],
    operation: Callable[[UnitOfWork, Actor, M], dict[str, object]],
    *,
    status: int = 201,
) -> JSONResponse:
    try:
        api, _ask, actor = _configured(request)
        raw = await read_capped_body(request)
        if isinstance(raw, JSONResponse):
            return raw
        document = model.model_validate_json(raw)
        result = await asyncio.to_thread(_transaction, request, api, lambda u: operation(u, actor, document))
        return JSONResponse(status_code=status, content={"schema_version": 2, **result})
    except ValidationError:
        return JSONResponse(status_code=422, content=error_body("invalid_memory_v2"))
    except LoopbackDenied as exc:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code))
    except KernelDenied as exc:
        return JSONResponse(status_code=_status(exc.code), content=error_body(exc.code))
    except DatabaseUnavailable:
        return JSONResponse(status_code=503, content=error_body("database_unavailable"))


@router.post("/memory")
async def add_memory(request: Request) -> JSONResponse:
    return await _write(request, MemorySubmissionV2, lambda u, a, d: asdict(_SERVICE.add(u, a, d)))


@router.get("/memory/search")
async def search_memory(request: Request, q: str, limit: int = 10) -> JSONResponse:
    return await _read(request, lambda u, a: {"hits": _VIEW.search(u, a, q, limit=limit)})


@router.get("/memory/{item_id}")
async def memory_history(item_id: UUID, request: Request, after_revision: int = 0) -> JSONResponse:
    return await _read(request, lambda u, a: _VIEW.history(u, a, str(item_id), after_revision=after_revision))


@router.post("/memory/{item_id}/correct")
async def correct_memory(item_id: UUID, request: Request) -> JSONResponse:
    return await _write(
        request,
        CorrectionV2,
        lambda u, a, d: asdict(
            _SERVICE.correct(u, a, str(item_id), d.expected_version, d.document, review_id=d.review_id)
        ),
    )


@router.post("/memory/{item_id}/privacy-review")
async def propose_review(item_id: UUID, request: Request) -> JSONResponse:
    def propose(uow: UnitOfWork, actor: Actor, document: CorrectionV2) -> dict[str, object]:
        if document.review_id is not None:
            raise KernelDenied("invalid_memory_review")
        result = _REVIEWS.propose(uow, actor, str(item_id), document.expected_version, document.document)
        original = result["old_label"]
        effective = resolve_classification(original).effective
        if effective is None:
            raise KernelDenied("classification_corrupt")
        return {**result, "old_label": effective, "original_label": original}

    return await _write(request, CorrectionV2, propose)


@router.post("/memory-reviews/{review_id}/decision")
async def decide_review(review_id: UUID, request: Request) -> JSONResponse:
    return await _write(
        request,
        ReviewDecision,
        lambda u, a, d: {
            "review_id": str(review_id),
            "state": _REVIEWS.decide(u, a, str(review_id), d.effect_digest, d.decision),
        },
        status=200,
    )


@router.post("/memory/{item_id}/suppress")
async def suppress_memory(item_id: UUID, request: Request) -> JSONResponse:
    return await _write(
        request,
        Suppression,
        lambda u, a, d: {
            "item_id": str(item_id),
            "row_version": _SERVICE.suppress(u, a, str(item_id), d.expected_version),
            "state": "SUPPRESSED",
        },
        status=200,
    )


@router.post("/memory/{item_id}/unsuppress")
async def unsuppress_memory(item_id: UUID, request: Request) -> JSONResponse:
    return await _write(
        request,
        Suppression,
        lambda u, a, d: {
            "item_id": str(item_id),
            "row_version": _SERVICE.unsuppress(u, a, str(item_id), d.expected_version),
            "state": "ACTIVE",
        },
        status=200,
    )
