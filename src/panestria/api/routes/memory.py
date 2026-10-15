"""Explicit owner facts/corrections and scoped recall; model output has no write endpoint."""

from __future__ import annotations

import asyncio
from dataclasses import asdict

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from panestria.api.auth import LoopbackDenied, error_body, read_capped_body
from panestria.api.db import DatabaseUnavailable
from panestria.api.routes.ask import _configured, _status, _transaction
from panestria.contracts.memory import MemorySubmission
from panestria.kernel.errors import KernelDenied
from panestria.memory.reclassification import ReclassificationService
from panestria.memory.service import MemoryService

router = APIRouter()
_SERVICE = MemoryService()
_REVIEWS = ReclassificationService()


class Correction(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    expected_version: int = Field(ge=0)
    document: MemorySubmission
    review_id: str | None = Field(default=None, pattern=r"^[0-9a-f-]{36}$")


class Suppression(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    expected_version: int = Field(ge=0)


@router.post("/v1/memory")
async def add_memory(request: Request) -> JSONResponse:
    try:
        api, _ask, actor = _configured(request)
        raw = await read_capped_body(request)
        if isinstance(raw, JSONResponse):
            return raw
        document = MemorySubmission.model_validate_json(raw)
        reference = await asyncio.to_thread(_transaction, request, api, lambda u: _SERVICE.add(u, actor, document))
        return JSONResponse(status_code=201, content=asdict(reference))
    except ValidationError:
        return JSONResponse(status_code=422, content=error_body("invalid_memory"))
    except LoopbackDenied as exc:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code))
    except KernelDenied as exc:
        return JSONResponse(status_code=_status(exc.code), content=error_body(exc.code))
    except DatabaseUnavailable:
        return JSONResponse(status_code=503, content=error_body("database_unavailable"))


@router.get("/v1/memory/search")
async def search_memory(request: Request, q: str, limit: int = 10) -> JSONResponse:
    try:
        api, _ask, actor = _configured(request)
        hits = await asyncio.to_thread(_transaction, request, api, lambda u: _SERVICE.search(u, actor, q, limit=limit))
        return JSONResponse(status_code=200, content={"hits": [asdict(hit) for hit in hits]})
    except LoopbackDenied as exc:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code))
    except KernelDenied as exc:
        return JSONResponse(status_code=_status(exc.code), content=error_body(exc.code))
    except DatabaseUnavailable:
        return JSONResponse(status_code=503, content=error_body("database_unavailable"))


@router.post("/v1/memory/{item_id}/correct")
async def correct_memory(item_id: str, request: Request) -> JSONResponse:
    try:
        api, _ask, actor = _configured(request)
        raw = await read_capped_body(request)
        if isinstance(raw, JSONResponse):
            return raw
        document = Correction.model_validate_json(raw)
        ref = await asyncio.to_thread(
            _transaction,
            request,
            api,
            lambda u: _SERVICE.correct(
                u,
                actor,
                item_id,
                document.expected_version,
                document.document,
                review_id=document.review_id,
            ),
        )
        return JSONResponse(status_code=201, content=asdict(ref))
    except ValidationError:
        return JSONResponse(status_code=422, content=error_body("invalid_memory_correction"))
    except LoopbackDenied as exc:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code))
    except KernelDenied as exc:
        return JSONResponse(status_code=_status(exc.code), content=error_body(exc.code))
    except DatabaseUnavailable:
        return JSONResponse(status_code=503, content=error_body("database_unavailable"))


@router.post("/v1/memory/{item_id}/suppress")
async def suppress_memory(item_id: str, request: Request) -> JSONResponse:
    try:
        api, _ask, actor = _configured(request)
        raw = await read_capped_body(request)
        if isinstance(raw, JSONResponse):
            return raw
        document = Suppression.model_validate_json(raw)
        version = await asyncio.to_thread(
            _transaction,
            request,
            api,
            lambda u: _SERVICE.suppress(
                u,
                actor,
                item_id,
                document.expected_version,
            ),
        )
        return JSONResponse(
            status_code=200, content={"item_id": item_id, "row_version": version, "state": "SUPPRESSED"}
        )
    except ValidationError:
        return JSONResponse(status_code=422, content=error_body("invalid_memory_suppression"))
    except LoopbackDenied as exc:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code))
    except KernelDenied as exc:
        return JSONResponse(status_code=_status(exc.code), content=error_body(exc.code))
    except DatabaseUnavailable:
        return JSONResponse(status_code=503, content=error_body("database_unavailable"))


class ReviewDecision(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    effect_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: str = Field(pattern=r"^(approve|deny)$")


@router.post("/v1/memory/{item_id}/privacy-review")
async def propose_privacy_review(item_id: str, request: Request) -> JSONResponse:
    try:
        api, _ask, actor = _configured(request)
        raw = await read_capped_body(request)
        if isinstance(raw, JSONResponse):
            return raw
        document = Correction.model_validate_json(raw)
        if document.review_id is not None:
            raise KernelDenied("invalid_memory_review")
        review = await asyncio.to_thread(
            _transaction,
            request,
            api,
            lambda u: _REVIEWS.propose(
                u,
                actor,
                item_id,
                document.expected_version,
                document.document,
            ),
        )
        return JSONResponse(status_code=201, content=review)
    except ValidationError:
        return JSONResponse(status_code=422, content=error_body("invalid_memory_review"))
    except LoopbackDenied as exc:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code))
    except KernelDenied as exc:
        return JSONResponse(status_code=_status(exc.code), content=error_body(exc.code))
    except DatabaseUnavailable:
        return JSONResponse(status_code=503, content=error_body("database_unavailable"))


@router.post("/v1/memory-reviews/{review_id}/decision")
async def decide_privacy_review(review_id: str, request: Request) -> JSONResponse:
    try:
        api, _ask, actor = _configured(request)
        raw = await read_capped_body(request)
        if isinstance(raw, JSONResponse):
            return raw
        document = ReviewDecision.model_validate_json(raw)
        state = await asyncio.to_thread(
            _transaction,
            request,
            api,
            lambda u: _REVIEWS.decide(
                u,
                actor,
                review_id,
                document.effect_digest,
                document.decision,
            ),
        )
        return JSONResponse(status_code=200, content={"review_id": review_id, "state": state})
    except ValidationError:
        return JSONResponse(status_code=422, content=error_body("invalid_review_decision"))
    except LoopbackDenied as exc:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code))
    except KernelDenied as exc:
        return JSONResponse(status_code=_status(exc.code), content=error_body(exc.code))
    except DatabaseUnavailable:
        return JSONResponse(status_code=503, content=error_body("database_unavailable"))


@router.get("/v1/memory/{item_id}")
async def memory_history(item_id: str, request: Request, after_revision: int = 0) -> JSONResponse:
    try:
        api, _ask, actor = _configured(request)
        history = await asyncio.to_thread(
            _transaction,
            request,
            api,
            lambda u: _SERVICE.history(
                u,
                actor,
                item_id,
                after_revision=after_revision,
            ),
        )
        return JSONResponse(status_code=200, content=history)
    except LoopbackDenied as exc:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code))
    except KernelDenied as exc:
        return JSONResponse(status_code=_status(exc.code), content=error_body(exc.code))
    except DatabaseUnavailable:
        return JSONResponse(status_code=503, content=error_body("database_unavailable"))
