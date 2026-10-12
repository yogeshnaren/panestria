"""Scoped artifact metadata. The response never includes a filesystem path."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from panestria.api.auth import LoopbackDenied, authorize, error_body
from panestria.api.db import DatabaseUnavailable, open_database
from panestria.api.routes.goals import _api, _unavailable
from panestria.kernel.artifacts import ArtifactService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.uow import UnitOfWork

router = APIRouter()
_SERVICE = ArtifactService()
_STATUSES = {"not_found": 404, "missing_evidence": 409, "corrupt_artifact": 409}


@router.get("/v1/artifacts/{artifact_id}")
def read_artifact(artifact_id: str, request: Request) -> JSONResponse:
    try:
        api = _api(request)
        actor = authorize(request, api)
    except LoopbackDenied as exc:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code))
    sandbox = getattr(request.app.state, "sandbox", None)
    if not isinstance(sandbox, Path):
        return JSONResponse(status_code=409, content=error_body("missing_evidence"))
    try:
        connection = open_database(api.database_url)
    except DatabaseUnavailable:
        return _unavailable()
    try:
        try:
            view = _SERVICE.read(UnitOfWork(connection), actor, artifact_id, sandbox)
        except KernelDenied as exc:
            connection.rollback()
            return JSONResponse(status_code=_STATUSES.get(exc.code, 422), content=error_body(exc.code))
        connection.rollback()
    finally:
        connection.close()
    return JSONResponse(
        status_code=200,
        headers={"Cache-Control": "no-store"},
        content={
            "artifact_id": view.artifact_id,
            "kind": view.kind,
            "sha256": view.sha256,
            "size_bytes": view.size_bytes,
            "verdicts": [{"check_key": key, "verdict": verdict} for key, verdict in view.verdicts],
        },
    )
