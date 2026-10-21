"""Source-bound Build progress observations; activity does not establish success."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class ProgressRecord(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")


class RequirementProgress(ProgressRecord):
    key: str
    description: str
    required: bool
    verifier_type: str
    verdict: str
    report_sha256: str | None


class NonGoalProgress(ProgressRecord):
    key: str
    description: str
    status: Literal["NOT_ASSESSED"] = "NOT_ASSESSED"


class MilestoneProgress(ProgressRecord):
    task_id: str
    state: str
    lease_epoch: int
    evidence_sha256: str | None
    evidence_status: Literal["NOT_RUN", "CONFIRMED", "UNCONFIRMED"]
    evidence_reason: str | None
    candidate_commit: str | None
    checks: tuple[tuple[str, str], ...]
    handoff_sha256: str | None
    failure_fingerprint: str | None


class PlanProgress(ProgressRecord):
    plan_id: str
    version: int
    proposal_sha256: str
    parent_sha256: str | None
    inventory_sha256: str
    state: str
    milestones: tuple[MilestoneProgress, ...]


class RepairProgress(ProgressRecord):
    planning_turns_used: int = 0
    planning_wall_charged_seconds: int = 0
    unconfirmed_planning_turns: int = 0
    versions_used: int
    maximum_versions: int | None
    wall_envelope_charged_seconds: int
    wall_envelope_remaining_seconds: int
    repeated_failure_count: int
    held_claims: int
    unconfirmed_invocations: int
    expired_held_claims: int
    unknown_invocations: int


class BuildProgress(ProgressRecord):
    schema_version: Literal[1] = 1
    owner_id: str
    project_id: str
    goal_id: str
    contract_sha256: str
    contract_version: int
    goal_status: str
    observed_at: str
    as_of_event_seq: int
    current_plan_id: str | None
    plans: tuple[PlanProgress, ...]
    requirements: tuple[RequirementProgress, ...]
    non_goals: tuple[NonGoalProgress, ...]
    required_checks_passed: int
    required_checks_total: int
    final_evidence_sha256: str | None
    repair: RepairProgress
    attention_reason: str
    next_action: str
    owner_merge: Literal["NOT_REQUESTED", "PENDING", "CONFIRMED"]
    release_acceptance: Literal["NOT_ASSESSED"] = "NOT_ASSESSED"
    dispatch_authority: Literal["NONE"] = "NONE"
