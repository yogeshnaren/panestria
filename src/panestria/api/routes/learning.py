"""Only authenticated owner mutations capture corrections; text stays out of route logs."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from panestria.api.auth import LoopbackDenied, error_body, read_capped_body
from panestria.api.db import DatabaseUnavailable
from panestria.api.routes.ask import _configured, _status, _transaction
from panestria.contracts.learning import UserCorrection
from panestria.kernel.errors import KernelDenied
from panestria.learning.recorder import LearningRecorder

router = APIRouter()
_RECORDER = LearningRecorder()


@router.get("/v1/ask/{request_id}/ledger")
async def request_ledger(request_id: str, request: Request) -> JSONResponse:
    try:
        api, _ask, actor = _configured(request)
        rows = await asyncio.to_thread(_transaction, request, api, lambda u: _RECORDER.export(u, actor, request_id))
        return JSONResponse(status_code=200, content={"records": rows})
    except LoopbackDenied as exc:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code))
    except KernelDenied as exc:
        return JSONResponse(status_code=_status(exc.code), content=error_body(exc.code))
    except DatabaseUnavailable:
        return JSONResponse(status_code=503, content=error_body("database_unavailable"))


@router.post("/v1/corrections")
async def capture_correction(request: Request) -> JSONResponse:
    try:
        api, _ask, actor = _configured(request)
        raw = await read_capped_body(request)
        if isinstance(raw, JSONResponse):
            return raw
        try:
            document = UserCorrection.model_validate_json(raw)
        except ValidationError:
            return JSONResponse(status_code=422, content=error_body("invalid_correction"))
        consent = str(uuid4())  # This authenticated POST is the explicit owner consent.
        identity = await asyncio.to_thread(
            _transaction,
            request,
            api,
            lambda u: _RECORDER.capture_correction(
                u,
                actor,
                document,
                consent_ref=consent,
            ),
        )
        return JSONResponse(status_code=201, content={"correction_id": identity, "consent_ref": consent})
    except LoopbackDenied as exc:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code))
    except KernelDenied as exc:
        return JSONResponse(status_code=_status(exc.code), content=error_body(exc.code))
    except DatabaseUnavailable:
        return JSONResponse(status_code=503, content=error_body("database_unavailable"))
