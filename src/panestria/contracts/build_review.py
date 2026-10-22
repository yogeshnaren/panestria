"""Exact PUBLIC review content; recording consent never dispatches a merge."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from panestria.contracts.approval import ActionPreview
from panestria.contracts.build import BuildCheck


class ReviewCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    check: BuildCheck
    report: str = Field(max_length=32768)


class BuildReview(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    owner_id: str
    project_id: str
    goal_id: str
    goal_status: str
    task_state: str
    approval_id: str
    approval_state: str
    expected_version: StrictInt
    effect_digest: str
    preview: ActionPreview
    observed_at: str
    review_sha256: str
    base_commit: str
    candidate_commit: str
    candidate_tree: str
    diff: str = Field(max_length=65536)
    checks: tuple[ReviewCheck, ...]
    decision_available: bool
    dispatch_authority: Literal["NONE"] = "NONE"
    release_acceptance: Literal["NOT_ASSESSED"] = "NOT_ASSESSED"


class BuildReviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)
    approval_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    effect_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_version: StrictInt = Field(ge=0)
    review_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: Literal["approve", "deny"]
    idempotency_key: str = Field(pattern=r"^[0-9a-f-]{36}$")


class BuildReviewReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    approval_id: str
    state: str
    effect_digest: str
    row_version: int
    replayed: bool
    dispatch_authority: Literal["NONE"] = "NONE"
    next_action: Literal["INSPECT_CANONICAL_STATE_USE_EXISTING_OWNER_BUILD_CLI"] = (
        "INSPECT_CANONICAL_STATE_USE_EXISTING_OWNER_BUILD_CLI"
    )


class MissionCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    build_review_enabled: bool
    offline_ask_enabled: bool = False
    research_intake_enabled: bool = False
    dispatch_authority: Literal["NONE"] = "NONE"
