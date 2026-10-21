"""CLI issues a one-use code; same-origin browser receives an HttpOnly cookie."""

from __future__ import annotations

import json

import psycopg
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from panestria.api.auth import LoopbackDenied, authorize, error_body, read_capped_body
from panestria.api.db import DatabaseUnavailable, open_database, run_database
from panestria.api.routes.goals import _api
from panestria.api.sessions import BrowserAccess
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.uow import UnitOfWork

router = APIRouter()


class PairBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    code: str = Field(pattern=r"^[0-9A-F]{8}$")


def _access(request: Request) -> BrowserAccess:
    access = getattr(request.app.state, "browser_access", None)
    if not isinstance(access, BrowserAccess):
        raise LoopbackDenied("not_configured", 503)
    return access


@router.post("/v1/session/code")
def issue_code(request: Request) -> JSONResponse:
    try:
        api, access = _api(request), _access(request)
        if "origin" in request.headers or request.cookies.get(access.cookie_name):
            raise LoopbackDenied("cli_auth_required", 403)
        actor = authorize(request, api)
        with open_database(api.database_url) as connection:
            code = access.service.issue_pairing_code(UnitOfWork(connection), actor)
        return JSONResponse(content={"code": code, "expires_in_seconds": 120})
    except LoopbackDenied as exc:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code))
    except (DatabaseUnavailable, psycopg.Error):
        return JSONResponse(status_code=503, content=error_body("database_unavailable"))
    except KernelDenied as exc:
        return JSONResponse(status_code=403, content=error_body(exc.code))


@router.post("/v1/session/pair")
async def pair(request: Request) -> JSONResponse:
    try:
        api, access = _api(request), _access(request)
        access.validate_origin(request, mutation=True)
        raw = await read_capped_body(request)
        if isinstance(raw, JSONResponse):
            return raw
        document = PairBody.model_validate_json(raw)
    except (ValidationError, json.JSONDecodeError):
        return JSONResponse(status_code=422, content=error_body("invalid_pairing_request"))
    except LoopbackDenied as exc:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code))
    except KernelDenied as exc:
        return JSONResponse(status_code=403, content=error_body(exc.code))
    return await run_database(_pair, access, Actor(api.owner_id, api.project_id), document.code)


def _pair(access: BrowserAccess, actor: Actor, code: str) -> JSONResponse:
    try:
        with open_database(access.database_url) as connection:
            tokens = access.service.pair(UnitOfWork(connection), actor, code)
    except KernelDenied as exc:
        return JSONResponse(status_code=401, content=error_body(exc.code))
    except (DatabaseUnavailable, psycopg.Error):
        return JSONResponse(status_code=503, content=error_body("database_unavailable"))
    response = JSONResponse(
        content={
            "session_id": tokens.session_id,
            "csrf_token": tokens.csrf,
            "expires_at": tokens.expires_at.isoformat(),
        }
    )
    # Remove the legacy path to avoid two same-name cookies on /v1 requests.
    response.delete_cookie(access.cookie_name, path="/v1", httponly=True, secure=access.secure, samesite="strict")
    response.set_cookie(
        access.cookie_name,
        tokens.token,
        max_age=8 * 3600,
        httponly=True,
        secure=access.secure,
        samesite="strict",
        path="/",
    )
    return response


@router.post("/v1/session/logout")
def logout(request: Request) -> JSONResponse:
    try:
        api, access = _api(request), _access(request)
        access.validate_origin(request, mutation=True)
        with open_database(api.database_url) as connection:
            access.service.revoke(
                UnitOfWork(connection),
                Actor(api.owner_id, api.project_id),
                request.cookies.get(access.cookie_name, ""),
                request.headers.get("x-panestria-csrf", ""),
            )
    except LoopbackDenied as exc:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code))
    except KernelDenied as exc:
        return JSONResponse(status_code=403, content=error_body(exc.code))
    except (DatabaseUnavailable, psycopg.Error):
        return JSONResponse(status_code=503, content=error_body("database_unavailable"))
    response = JSONResponse(content={"state": "REVOKED"})
    response.delete_cookie(access.cookie_name, path="/", httponly=True, secure=access.secure, samesite="strict")
    response.delete_cookie(access.cookie_name, path="/v1", httponly=True, secure=access.secure, samesite="strict")
    return response
