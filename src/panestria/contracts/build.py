"""Immutable verification binds Git identity, scope and the whole declared check set."""

from __future__ import annotations

import hashlib
import json
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

_HEX64 = r"^[0-9a-f]{64}$"
_HEX40 = r"^[0-9a-f]{40}$"
_UUID = r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


class BuildCheck(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    check_id: str = Field(pattern=_UUID)
    check_key: str = Field(min_length=1, max_length=128)
    required: bool
    spec_sha256: str = Field(pattern=_HEX64)
    verdict: Literal["PASS", "FAIL", "UNKNOWN", "ERROR"]
    report_sha256: str = Field(pattern=_HEX64)


class BuildEvidenceBundle(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    owner_id: str = Field(pattern=_UUID)
    project_id: str = Field(pattern=_UUID)
    task_id: str = Field(pattern=_UUID)
    attempt_id: str = Field(pattern=_UUID)
    lease_epoch: int = Field(ge=1)
    contract_id: str = Field(pattern=_UUID)
    contract_sha256: str = Field(pattern=_HEX64)
    contract_version: int = Field(ge=1)
    policy_ref: str = Field(min_length=1, max_length=128)
    base_commit: str = Field(pattern=_HEX40)
    candidate_commit: str = Field(pattern=_HEX40)
    candidate_tree: str = Field(pattern=_HEX40)
    snapshot_sha256: str = Field(pattern=_HEX64)
    verifier_bundle_sha256: str = Field(pattern=_HEX64)
    checks: tuple[BuildCheck, ...] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def _unique(self) -> Self:
        if len({check.check_id for check in self.checks}) != len(self.checks):
            raise ValueError("duplicate_check")
        if len({check.check_key for check in self.checks}) != len(self.checks):
            raise ValueError("duplicate_check")
        if tuple(sorted(self.checks, key=lambda check: check.check_key)) != self.checks:
            raise ValueError("unordered_checks")
        return self

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    def passed(self) -> bool:
        required = [check for check in self.checks if check.required]
        return bool(required) and all(check.verdict == "PASS" for check in required)
