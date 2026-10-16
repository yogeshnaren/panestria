"""Quota metadata is evidence with provenance, never a dispatch or billing permit."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

QuotaId = Annotated[str, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")]
QuotaSource = Literal["PROVIDER_REPORTED", "OWNER_REPORTED", "ESTIMATED", "UNKNOWN"]


class QuotaContract(BaseModel):
    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True, revalidate_instances="always"
    )


class QuotaScope(QuotaContract):
    provider: Literal["claude-subscription", "anthropic-api", "openai-api", "local-ollama"]
    account_ref: QuotaId
    model_ref: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,127}$")
    window_ref: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")

    def sha256(self) -> str:
        return _sha(self)


class QuotaObservation(QuotaContract):
    schema_version: StrictInt = Field(default=1, ge=1, le=1)
    observation_id: QuotaId
    scope: QuotaScope
    source: QuotaSource
    remaining: str | None = Field(default=None, pattern=r"^(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,3})?$")
    unit: Literal["percent", "tokens", "requests"] | None = None
    observed_at: AwareDatetime
    resets_at: AwareDatetime | None = None
    fresh_for_seconds: StrictInt = Field(default=900, ge=1, le=86400)
    source_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @field_validator("observed_at", "resets_at")
    @classmethod
    def utc_times(cls, value: AwareDatetime | None) -> AwareDatetime | None:
        return None if value is None else value.astimezone(UTC)

    @field_validator("remaining")
    @classmethod
    def normalized_decimal(cls, value: str | None) -> str | None:
        return None if value is None else format(Decimal(value).normalize(), "f")

    @model_validator(mode="after")
    def honest_shape(self) -> Self:
        if self.source == "UNKNOWN":
            if self.remaining is not None:
                raise ValueError("unknown_quota_requires_null")
        if self.remaining is not None and self.unit is None:
            raise ValueError("quota_unit_required")
        if self.remaining is not None:
            amount = Decimal(self.remaining)
            if self.unit == "percent" and amount > 100:
                raise ValueError("invalid_quota_percent")
            if self.unit in {"tokens", "requests"} and amount != amount.to_integral_value():
                raise ValueError("invalid_quota_count")
        if (self.source in {"PROVIDER_REPORTED", "ESTIMATED"}) != (self.source_sha256 is not None):
            raise ValueError("quota_source_provenance_mismatch")
        if self.resets_at is not None and self.resets_at <= self.observed_at:
            raise ValueError("invalid_quota_reset")
        return self

    def sha256(self) -> str:
        return _sha(self)


def _sha(value: BaseModel) -> str:
    return hashlib.sha256(
        json.dumps(value.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
