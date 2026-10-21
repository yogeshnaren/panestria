"""Closed PUBLIC Build evidence metadata; no description, path, prompt or report body."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BuildCheckObservation(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    key: str
    required: bool
    verdict: str
    report_sha256: str | None


class BuildMilestoneObservation(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    task_id: UUID
    state: str
    evidence_status: Literal["NOT_RUN", "CONFIRMED", "UNCONFIRMED"]
    evidence_sha256: str | None
    candidate_commit: str | None
    handoff_sha256: str | None


class BuildObservation(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    owner_id: UUID
    project_id: UUID
    goal_id: UUID
    goal_status: str
    observed_at: str
    as_of_event_seq: str = Field(pattern=r"^(0|[1-9][0-9]{0,18})$")
    contract_sha256: str
    required_checks_passed: int = Field(ge=0)
    required_checks_total: int = Field(ge=0)
    checks: tuple[BuildCheckObservation, ...]
    milestones: tuple[BuildMilestoneObservation, ...]
    final_evidence_sha256: str | None
    attention_reason: str
    next_action: str
    held_claims: int = Field(ge=0)
    unknown_invocations: int = Field(ge=0)
    owner_merge: Literal["NOT_REQUESTED", "PENDING", "CONFIRMED"]
    release_acceptance: Literal["NOT_ASSESSED"] = "NOT_ASSESSED"
    dispatch_authority: Literal["NONE"] = "NONE"
    view_authority: Literal["READ_ONLY_PUBLIC_BUILD_EVIDENCE_METADATA"] = "READ_ONLY_PUBLIC_BUILD_EVIDENCE_METADATA"
