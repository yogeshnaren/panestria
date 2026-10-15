"""Explicit local owner profile operations; no key provisioning or inference."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Literal, TypeVar
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from panestria.api.auth import GoalApi, LoopbackDenied, authorize, error_body, read_capped_body
from panestria.api.db import DatabaseUnavailable
from panestria.api.routes.ask import _transaction
from panestria.contracts.profile import ProfileDocument
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.uow import UnitOfWork
from panestria.memory.keys import ProfileKeyHandle
from panestria.memory.vault import ProfileVault

router = APIRouter(prefix="/v2/profiles")
M = TypeVar("M", bound=BaseModel)
_UUID = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
_HEADERS = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff"}


@dataclass(frozen=True)
class ProfileApi:
    vault: ProfileVault


class VersionedProfileInput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    schema_version: Literal[1]

    @field_validator("schema_version", mode="before")
    @classmethod
    def explicit_version(cls, value: object) -> object:
        if type(value) is not int or value != 1:
            raise ValueError("invalid_profile_api_version")
        return value


class CreateProfile(VersionedProfileInput):
    profile_id: str = Field(pattern=_UUID)
    key_id: str = Field(pattern=_UUID)
    intent: Literal["SAVE_RESTRICTED_PROFILE"]
    document: ProfileDocument


class ReviseProfile(VersionedProfileInput):
    expected_version: int = Field(ge=0)
    key_id: str = Field(pattern=_UUID)
    intent: Literal["SAVE_RESTRICTED_PROFILE"]
    document: ProfileDocument


class ProfileVersion(VersionedProfileInput):
    expected_version: int = Field(ge=0)


class ViewProfile(ProfileVersion):
    purpose: Literal["OWNER_REVIEW"]


def _configured(request: Request) -> tuple[GoalApi, ProfileApi, Actor]:
    api, profiles = getattr(request.app.state, "goal_api", None), getattr(request.app.state, "profile_api", None)
    if not isinstance(api, GoalApi) or not isinstance(profiles, ProfileApi):
        raise LoopbackDenied("profile_not_configured", 503)
    return api, profiles, authorize(request, api)


def _response(content: dict[str, object], status: int = 200) -> JSONResponse:
    return JSONResponse(content={"schema_version": 1, **content}, status_code=status, headers=_HEADERS)


def _denial(code: str) -> JSONResponse:
    status = {
        "not_found": 404,
        "version_conflict": 409,
        "unauthorized": 401,
        "csrf_denied": 403,
        "profile_disabled": 503,
        "key_store_unavailable": 503,
        "key_store_timeout": 503,
        "key_store_locked": 423,
        "key_handle_missing": 409,
    }.get(code, 422)
    return _response(error_body(code), status)


async def _write(
    request: Request,
    model: type[M],
    operation: Callable[[UnitOfWork, Actor, ProfileVault, M], dict[str, object]],
    *,
    status: int = 200,
) -> JSONResponse:
    try:
        api, profiles, actor = _configured(request)
        raw = await read_capped_body(request)
        if isinstance(raw, JSONResponse):
            raw.headers.update(_HEADERS)
            return raw
        document = model.model_validate_json(raw)
        result = await asyncio.to_thread(
            _transaction, request, api, lambda u: operation(u, actor, profiles.vault, document)
        )
        return _response(result, status)
    except ValidationError:
        return _response(error_body("invalid_profile_request"), 422)
    except LoopbackDenied as exc:
        return _response(error_body(exc.code), exc.status_code)
    except KernelDenied as exc:
        return _denial(exc.code)
    except DatabaseUnavailable:
        return _response(error_body("database_unavailable"), 503)


def _handle(actor: Actor, profile_id: str, key_id: str) -> ProfileKeyHandle:
    return ProfileKeyHandle(owner_id=actor.owner_id, project_id=actor.project_id, profile_id=profile_id, key_id=key_id)


@router.post("")
async def create_profile(request: Request) -> JSONResponse:
    return await _write(
        request,
        CreateProfile,
        lambda u, a, v, d: {
            **asdict(v.create(u, a, _handle(a, d.profile_id, d.key_id), d.document, consent_ref=str(uuid4()))),
            "classification": "RESTRICTED",
        },
        status=201,
    )


@router.post("/{profile_id}/correct")
async def correct_profile(profile_id: str, request: Request) -> JSONResponse:
    return await _write(
        request,
        ReviseProfile,
        lambda u, a, v, d: {
            **asdict(
                v.revise(
                    u, a, _handle(a, profile_id, d.key_id), d.expected_version, d.document, consent_ref=str(uuid4())
                )
            ),
            "classification": "RESTRICTED",
        },
        status=201,
    )


@router.post("/{profile_id}/view")
async def view_profile(profile_id: str, request: Request) -> JSONResponse:
    def view(uow: UnitOfWork, actor: Actor, vault: ProfileVault, document: ViewProfile) -> dict[str, object]:
        # Validate path as strictly as an opaque handle, without echoing it.
        _handle(actor, profile_id, str(uuid4()))
        ref, content = vault.read(uow, actor, profile_id, expected_version=document.expected_version)
        return {
            **asdict(ref),
            "classification": "RESTRICTED",
            "document": {
                **content.model_dump(mode="json"),
                "fields": {name: value.get_secret_value() for name, value in content.fields.items()},
            },
        }

    return await _write(request, ViewProfile, view)


@router.post("/{profile_id}/suppress")
async def suppress_profile(profile_id: str, request: Request) -> JSONResponse:
    def suppress(uow: UnitOfWork, actor: Actor, vault: ProfileVault, document: ProfileVersion) -> dict[str, object]:
        _handle(actor, profile_id, str(uuid4()))
        return {
            "profile_id": profile_id,
            "row_version": vault.suppress(uow, actor, profile_id, document.expected_version),
            "state": "SUPPRESSED",
            "classification": "RESTRICTED",
        }

    return await _write(request, ProfileVersion, suppress)
