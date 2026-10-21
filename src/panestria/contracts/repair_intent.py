"""Immutable metadata for local repair I/O; never an accepted plan or task verdict."""

from typing import Literal, Self

from pydantic import Field, StrictInt, model_validator

from panestria.contracts.plan import PlanContract, PlanId, PlanSha

STARTED = "build.repair_draft.started"
FINISHED = "build.repair_draft.finished"
KINDS = (STARTED, FINISHED)
# Reservation includes generation and lifecycle overhead. It is not a claim
# that the OS can interrupt uninterruptible filesystem/driver I/O on time.
TURN_WALL_SECONDS: Literal[360] = 360
DRAFT_FILES = (
    "contract.json",
    "inventory.json",
    "request.json",
    "repair-context.json",
    "response.txt",
    "proposal.json",
    "validation.json",
    "result.json",
)


class RepairIntent(PlanContract):
    draft_id: PlanId
    parent_plan_id: PlanId
    parent_sha256: PlanSha
    return_proof_sha256: PlanSha
    contract_sha256: PlanSha
    key_sha256: PlanSha
    directory_sha256: PlanSha
    context_sha256: PlanSha
    request_sha256: PlanSha
    turn: StrictInt = Field(ge=1, le=2)
    maximum_turns: StrictInt = Field(ge=1, le=2)
    reserved_wall_seconds: Literal[360] = TURN_WALL_SECONDS

    @model_validator(mode="after")
    def turn_bound(self) -> Self:
        if self.turn > self.maximum_turns:
            raise ValueError("repair_turn_exceeds_bound")
        return self


class RepairOutcome(PlanContract):
    draft_id: PlanId
    intent_sha256: PlanSha
    status: Literal["RETAINED", "NOT_PUBLISHED", "UNCONFIRMED"]
    physical_return: Literal["CONFIRMED", "UNCONFIRMED"]
    receipt_sha256: PlanSha | None = None
    files: dict[str, PlanSha] = Field(default_factory=dict, max_length=8)
    reason: Literal["ok", "draft_not_published", "return_unconfirmed", "wall_reservation_exceeded"]

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if set(self.files) - set(DRAFT_FILES):
            raise ValueError("repair_file_name_invalid")
        if self.status == "RETAINED" and (
            self.physical_return != "CONFIRMED"
            or self.reason != "ok"
            or set(self.files) != set(DRAFT_FILES)
            or not self.receipt_sha256
            or self.files["result.json"] != self.receipt_sha256
        ):
            raise ValueError("repair_retained_receipt_invalid")
        if self.status == "NOT_PUBLISHED" and (
            self.physical_return != "CONFIRMED" or self.reason != "draft_not_published" or self.receipt_sha256
        ):
            raise ValueError("repair_not_published_receipt_invalid")
        if self.status == "UNCONFIRMED" and self.reason not in {"return_unconfirmed", "wall_reservation_exceeded"}:
            raise ValueError("repair_unconfirmed_reason_invalid")
        return self
