"""Closed effect classifications and bounded references. No credentials or executable commands."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EffectClassification = Literal[
    "read-only", "idempotent-with-key", "reconcile-by-query", "compensatable", "non-retryable"
]


class EffectIntent(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    task_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    effect_key: str = Field(min_length=1, max_length=128)
    target: str = Field(min_length=1, max_length=512)
    request_ref: str = Field(min_length=1, max_length=256)
    classification: EffectClassification
    policy_version: str = Field(min_length=1, max_length=128)
    effect_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    def fingerprint(self) -> str:
        return hashlib.sha256(json.dumps(self.model_dump(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
