"""Honest observations and explicit corrections, without authority flags."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from panestria.contracts.classification import resolve_classification
from panestria.contracts.policy import DataLabel


class Observation(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    status: Literal["known", "estimated", "unknown"]
    value: int | None = Field(default=None, ge=0)
    unit: Literal["cash_microusd", "tokens", "requests"]

    @model_validator(mode="after")
    def honesty(self) -> Self:
        if (self.status == "unknown") != (self.value is None):
            raise ValueError("unknown_observation_requires_null")
        return self


class RouteCandidate(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    provider: Literal["local-ollama", "openai-api", "claude-code"]
    model_ref: str = Field(min_length=1, max_length=128)
    capability: Literal["chat", "generate", "build"]
    available: bool
    expected_cash: Observation
    quota_remaining: Observation


class ExposureObservation(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    dimension: Literal["authorized", "accessible", "observed"]
    destination: Literal["local", "openai-api", "claude-code"]
    label: DataLabel
    payload_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    value: Literal["yes", "no", "unknown"]
    source_kind: Literal["policy", "scope_manifest", "os_network"]
    content_visible: bool = False
    evidence_ref: str = Field(pattern=r"^[a-z][a-z_-]{0,31}:[0-9a-f-]{32,64}$")

    @model_validator(mode="after")
    def dimensions(self) -> Self:
        kinds = {"authorized": "policy", "accessible": "scope_manifest", "observed": "os_network"}
        if self.source_kind != kinds[self.dimension]:
            raise ValueError("exposure_source_mismatch")
        if (
            self.destination != "local"
            and resolve_classification(self.label).effective != "PUBLIC"
            and self.dimension == "authorized"
            and self.value == "yes"
        ):
            raise ValueError("restricted_or_unknown_cloud_denied")
        return self


class UserCorrection(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    request_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    output_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    kind: Literal["explicit_text", "diff", "rejection"]
    body: str = Field(min_length=1, max_length=8192, repr=False)
    label: DataLabel

    @model_validator(mode="after")
    def bounds(self) -> Self:
        if len(self.body.encode()) > 8192 or self.label == "UNKNOWN":
            raise ValueError("correction_requires_classification")
        return self
