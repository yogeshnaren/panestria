"""Opaque controller launch metadata; no task permission, path or secret."""

from __future__ import annotations

import hashlib
import json
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SandboxLaunchIntent(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    invocation_id: UUID
    binding_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    scope_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    runtime_attempt_id: UUID
    launch_id: UUID
    profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    image_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @field_validator("schema_version", mode="before")
    @classmethod
    def exact_version(cls, value: object) -> object:
        if type(value) is not int or value != 1:
            raise ValueError("invalid_launch_schema")
        return value

    @field_validator("launch_id")
    @classmethod
    def launch_uuid4(cls, value: UUID) -> UUID:
        if value.version != 4:
            raise ValueError("invalid_launch_identity")
        return value

    def sha256(self) -> str:
        raw = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(raw).hexdigest()


class SandboxLaunchObservation(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    intent_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["REMOVED", "NOT_OBSERVED", "UNCONFIRMED"]
    container_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    reason: Literal[
        "owned_container_removed",
        "no_owned_container_observed",
        "launch_candidates_unconfirmed",
        "launch_identity_unconfirmed",
        "launch_removal_unconfirmed",
        "launch_runtime_unconfirmed",
    ]

    @model_validator(mode="after")
    def consistent_observation(self) -> SandboxLaunchObservation:
        if self.status == "REMOVED":
            valid = self.reason == "owned_container_removed" and self.container_id is not None
        elif self.status == "NOT_OBSERVED":
            valid = self.reason == "no_owned_container_observed" and self.container_id is None
        else:
            valid = self.reason not in {"owned_container_removed", "no_owned_container_observed"}
        if not valid:
            raise ValueError("inconsistent_launch_observation")
        return self
