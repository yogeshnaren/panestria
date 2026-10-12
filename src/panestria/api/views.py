"""Response bodies published by the loopback API and checked by the CLI."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_HEX = r"^[0-9a-f]{64}$"


class GoalSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal_id: str
    contract_version: int = Field(ge=1)
    contract_sha256: str = Field(pattern=_HEX)
    replayed: bool


class GoalStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal_id: str
    status: str = Field(min_length=1)
    task_version: int = Field(ge=0)


class CancelResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal_id: str
    goal_status: str = Field(min_length=1)
    task_state: str = Field(min_length=1)
    task_version: int = Field(ge=0)


class EventRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seq: str = Field(pattern=r"^[0-9]+$")
    kind: str = Field(min_length=1)
    payload: dict[str, Any]


class EventPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[EventRow]


class ArtifactVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    check_key: str
    verdict: str


class ArtifactBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    kind: str
    sha256: str = Field(pattern=_HEX)
    size_bytes: int = Field(ge=0)
    verdicts: list[ArtifactVerdict]


class PendingApproval(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approval_id: str
    goal_id: str
    effect_digest: str = Field(pattern=_HEX)
    action_kind: str = Field(min_length=1)
    expected_version: int = Field(ge=0)
    expires_at: str = Field(min_length=1)


class ApprovalList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approvals: list[PendingApproval]


class ApprovalPreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approval_id: str
    effect_digest: str = Field(pattern=_HEX)
    expected_version: int = Field(ge=0)
    state: str = Field(min_length=1)
    continuation_kind: str = Field(min_length=1)
    preview: dict[str, Any]


class DecisionReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approval_id: str
    state: str = Field(min_length=1)
    effect_digest: str = Field(pattern=_HEX)
    row_version: int = Field(ge=0)
    replayed: bool
