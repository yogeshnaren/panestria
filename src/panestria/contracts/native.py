"""Inspection metadata carries no native execution or acceptance authority."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SkillMember(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    member: str = Field(max_length=256)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class NativeCompatibilityManifest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    observed_at: datetime
    profile_version: Literal["claude-2.1.273-preflight-v1"] = "claude-2.1.273-preflight-v1"
    cli_version: Literal["2.1.273"]
    binary_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    help_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    advertised_controls: tuple[str, ...]
    skills_archive_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    skill_members: tuple[SkillMember, ...]
    config_private: bool
    status: Literal["INSPECTED", "CONFIG_UNSAFE", "AUTH_REQUIRED", "AUTH_MODE_DENIED"]
    auth_state: Literal["NOT_INSPECTED", "MISSING", "SUBSCRIPTION", "DENIED"]
    conformance: Literal["NOT_RUN"] = "NOT_RUN"
    execution_authorized: Literal[False] = False
    inference_verified: Literal[False] = False
