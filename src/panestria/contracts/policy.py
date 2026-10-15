"""Closed independent policy axes. Client-provided approval flags are invalid."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Action = Literal["read", "edit", "tool-install", "external-send", "spend", "merge", "delete", "policy-change"]
DataLabel = Literal["PUBLIC", "PRIVATE", "RESTRICTED", "UNKNOWN"]
TrustProfile = Literal["SYNTHETIC_DEV", "PERSONAL_SANDBOX", "TRUSTED_PROJECT", "HARDENED_WORKSPACE"]
Autonomy = Literal["observe", "suggest", "approve-first", "act-and-report", "act-silently"]


class ClosedPolicy(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class TrustAxis(ClosedPolicy):
    version: int = Field(ge=1)
    profile: TrustProfile
    allowed_actions: list[Action]
    runtime_certificate_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @field_validator("allowed_actions")
    @classmethod
    def canonical_actions(cls, value: list[Action]) -> list[Action]:
        if len(set(value)) != len(value):
            raise ValueError("duplicate_action")
        return sorted(value)


class PrivacyAxis(ClosedPolicy):
    version: int = Field(ge=1)
    cloud_destinations: list[str] = Field(default_factory=list, max_length=16)
    allow_private_cloud: bool = False

    @field_validator("cloud_destinations")
    @classmethod
    def canonical_destinations(cls, value: list[str]) -> list[str]:
        if any(item not in {"claude-subscription", "openai-api", "anthropic-api"} for item in value):
            raise ValueError("unknown_destination")
        return sorted(set(value))


class AutonomyAxis(ClosedPolicy):
    version: int = Field(ge=1)
    actions: dict[Action, Autonomy]

    @field_validator("actions")
    @classmethod
    def complete_actions(cls, value: dict[Action, Autonomy]) -> dict[Action, Autonomy]:
        required = {"read", "edit", "tool-install", "external-send", "spend", "merge", "delete", "policy-change"}
        if set(value) != required:
            raise ValueError("incomplete_action_policy")
        return dict(sorted(value.items()))


class PolicyContext(ClosedPolicy):
    owner_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    project_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    version: int = Field(ge=1)
    trust: TrustAxis
    privacy: PrivacyAxis
    autonomy: AutonomyAxis

    def sha256(self) -> str:
        return hashlib.sha256(json.dumps(self.model_dump(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class PolicyRequest(ClosedPolicy):
    owner_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    project_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    action: Action
    label: DataLabel
    destination: str = Field(min_length=1, max_length=128)
    effect_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
