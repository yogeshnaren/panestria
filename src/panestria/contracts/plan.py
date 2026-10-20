"""Bounded Build proposals, never worker admission, policy grants or accepted task state."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from panestria.contracts.classification import CanonicalClass

PlanId = Annotated[str, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")]
PlanSha = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Ref = Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")]


class PlanContract(BaseModel):
    model_config = ConfigDict(
        strict=True, extra="forbid", frozen=True, revalidate_instances="always", hide_input_in_errors=True
    )

    def sha256(self) -> str:
        return hashlib.sha256(
            json.dumps(self.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest()


class WorkerInventory(PlanContract):
    worker_ref: Ref
    binary_sha256: PlanSha
    profile_sha256: PlanSha
    capabilities: tuple[Ref, ...] = Field(min_length=1, max_length=16)
    maximum_parallel: StrictInt = Field(ge=1, le=2)

    @field_validator("capabilities")
    @classmethod
    def unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("duplicate_capability")
        return tuple(sorted(value))


class ProjectInventory(PlanContract):
    schema_version: StrictInt = Field(default=1, ge=1, le=1)
    owner_id: PlanId
    project_id: PlanId
    base_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    snapshot_sha256: PlanSha
    workers: tuple[WorkerInventory, ...] = Field(min_length=1, max_length=4)
    maximum_nodes: StrictInt = Field(default=16, ge=1, le=16)
    maximum_depth: StrictInt = Field(default=8, ge=1, le=8)
    maximum_parallel: StrictInt = Field(default=2, ge=1, le=2)

    @model_validator(mode="after")
    def unique(self) -> Self:
        if len({w.worker_ref for w in self.workers}) != len(self.workers):
            raise ValueError("duplicate_worker")
        return self


class PlanNode(PlanContract):
    task_id: PlanId
    depends_on: tuple[PlanId, ...] = Field(default=(), max_length=15)
    worker_ref: Ref
    capabilities: tuple[Ref, ...] = Field(min_length=1, max_length=16)
    paths: tuple[str, ...] = Field(min_length=1, max_length=32)
    acceptance_keys: tuple[str, ...] = Field(min_length=1, max_length=100)
    expected_artifacts: tuple[Ref, ...] = Field(min_length=1, max_length=8)
    attempts: StrictInt = Field(ge=1, le=5)
    wall_seconds_per_attempt: StrictInt = Field(ge=1, le=3600)
    api_microusd_per_attempt: StrictInt = Field(ge=0, le=1_000_000_000)

    @model_validator(mode="after")
    def closed_scope(self) -> Self:
        for field in (self.depends_on, self.capabilities, self.paths, self.acceptance_keys, self.expected_artifacts):
            if len(set(field)) != len(field):
                raise ValueError("duplicate_plan_member")
        for path in self.paths:
            # Literal relative file paths only: no glob/shell/alias/traversal interpretation.
            parts = path.split("/")
            if (
                not 1 <= len(path.encode()) <= 256
                or any(p in {"", ".", "..", ".git"} for p in parts)
                or any(not (ch.isascii() and (ch.isalnum() or ch in "_./-")) for ch in path)
            ):
                raise ValueError("invalid_plan_path")
        if any(not 1 <= len(k.encode()) <= 128 for k in self.acceptance_keys):
            raise ValueError("invalid_plan_check_key")
        return self


class PlanProposal(PlanContract):
    schema_version: StrictInt = Field(default=1, ge=1, le=1)
    plan_id: PlanId
    owner_id: PlanId
    project_id: PlanId
    goal_id: PlanId
    contract_sha256: PlanSha
    inventory_sha256: PlanSha
    privacy_class: CanonicalClass
    nodes: tuple[PlanNode, ...] = Field(min_length=1, max_length=16)


class ValidatedDAG(PlanContract):
    proposal_sha256: PlanSha
    contract_sha256: PlanSha
    inventory_sha256: PlanSha
    layers: tuple[tuple[PlanId, ...], ...]
    maximum_parallel: StrictInt = Field(ge=1, le=2)
    upper_wall_seconds: StrictInt = Field(ge=1)
    upper_api_microusd: StrictInt = Field(ge=0)
    authority: Literal["PROPOSAL_ONLY"] = "PROPOSAL_ONLY"


class PlanConsent(PlanContract):
    plan_sha256: PlanSha
    contract_sha256: PlanSha
    inventory_sha256: PlanSha
    policy_ref: str = Field(pattern=r"^project-policy:[1-9][0-9]*:[0-9a-f]{64}$")
    expires_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T.*[+]00:00$")


class PlanRevisionConsent(PlanConsent):
    schema_version: Literal[2] = 2
    version: StrictInt = Field(ge=2, le=3)
    maximum_versions: StrictInt = Field(ge=2, le=3)
    parent_sha256: PlanSha
    return_proof_sha256: PlanSha
    cumulative_wall_seconds: StrictInt = Field(ge=1)
    cumulative_api_microusd: StrictInt = Field(ge=0, le=0)


class StoredPlan(PlanContract):
    proposal: PlanProposal
    inventory: ProjectInventory
    validation: ValidatedDAG
    consent: PlanConsent | PlanRevisionConsent
    effect_digest: PlanSha
    version: StrictInt = Field(ge=1)
    parent_sha256: PlanSha | None = None
    state: Literal["PROPOSED", "ACCEPTED"]
    execution_authority: Literal["NONE"] = "NONE"


class HandoffSubmission(PlanContract):
    handoff_id: PlanId
    plan_id: PlanId
    task_id: PlanId
    expected_task_version: StrictInt = Field(ge=0)
    evidence_sha256: PlanSha
    next_tasks: tuple[PlanId, ...] = Field(default=(), max_length=16)
    summary: str = Field(default="", max_length=2048, repr=False)

    @model_validator(mode="after")
    def bounded_note(self) -> Self:
        if len(self.summary.encode()) > 2048 or len(set(self.next_tasks)) != len(self.next_tasks):
            raise ValueError("invalid_handoff_note")
        return self


class RetainedHandoff(PlanContract):
    submission: HandoffSubmission
    plan_sha256: PlanSha
    contract_sha256: PlanSha
    inventory_sha256: PlanSha
    attempt_id: PlanId
    lease_epoch: StrictInt = Field(ge=1)
    candidate_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    candidate_tree: str = Field(pattern=r"^[0-9a-f]{40}$")
    snapshot_sha256: PlanSha
    actual_adapter: Ref
    declared_worker: WorkerInventory
    runtime_qualification: Literal["NOT_ASSESSED"] = "NOT_ASSESSED"
    summary_authority: Literal["UNTRUSTED_NOTE"] = "UNTRUSTED_NOTE"
    task_completion_authority: Literal["NONE"] = "NONE"


class PlanTaskScope(PlanContract):
    """Derived from immutable accepted membership, never selected by a worker."""

    plan_id: PlanId
    plan_sha256: PlanSha
    inventory_sha256: PlanSha
    node: PlanNode
    integration_task_id: PlanId

    @property
    def integration(self) -> bool:
        return self.node.task_id == self.integration_task_id
