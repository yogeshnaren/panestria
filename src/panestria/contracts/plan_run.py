"""One explicit foreground invocation, distinct from tasks, verification and merge."""

from typing import Literal

from pydantic import Field, StrictInt, field_validator

from panestria.contracts.plan import PlanContract, PlanId, PlanSha


class PlanRunIntent(PlanContract):
    request_id: PlanId
    plan_sha256: PlanSha
    public_subscription_run: Literal[True]

    @field_validator("public_subscription_run", mode="before")
    @classmethod
    def explicit_intent(cls, value: object) -> object:
        if value is not True:
            raise ValueError("explicit_public_subscription_run_required")
        return value


class PlanRunRecord(PlanContract):
    owner_id: PlanId
    project_id: PlanId
    goal_id: PlanId
    plan_id: PlanId
    intent: PlanRunIntent
    configuration_sha256: PlanSha
    expires_at: str = Field(max_length=64)


class PlanRunReturn(PlanContract):
    request_id: PlanId
    record_sha256: PlanSha
    outcome: Literal["RETURNED", "ADMISSION_DENIED", "CONTROLLER_ERROR"]
    runner_status: str = Field(pattern=r"^[A-Z_]{1,64}$")


class PlanRunStorage(PlanContract):
    record_sha256: PlanSha
    decision: Literal["ALLOW", "DEFER"]
    reason: Literal[
        "capacity_observed",
        "storage_capacity_unknown",
        "storage_policy_filesystem_mismatch",
        "storage_critical",
        "storage_reserve_at_risk",
        "storage_policy_unconfirmed",
    ]
    warnings: tuple[Literal["capacity_unknown", "disk_high", "disk_critical", "free_reserve_at_risk"], ...] = ()
    available_bytes: StrictInt | None = Field(default=None, ge=0)
    anticipated_write_bytes: StrictInt | None = Field(default=None, ge=1)
    cleanup_authority: Literal["NONE"] = "NONE"


class PlanRunView(PlanContract):
    owner_id: PlanId
    project_id: PlanId
    goal_id: PlanId
    plan_id: PlanId
    plan_sha256: PlanSha
    record: PlanRunRecord | None
    state: Literal["NOT_REQUESTED", "REQUESTED", "CLAIMED_UNCONFIRMED", "RETURN_RECORDED"]
    result: PlanRunReturn | None
    goal_status: str
    controller_active: bool = False
    configuration_current: bool
    observed_at: str
    expired: bool
    storage: PlanRunStorage | None = None
    merge_authority: Literal["NONE"] = "NONE"
    claim_release_authority: Literal["NONE"] = "NONE"
    release_acceptance: Literal["NOT_ASSESSED"] = "NOT_ASSESSED"


class PlanRunCancellation(PlanContract):
    request_id: PlanId
    plan_sha256: PlanSha
    cancel_plan: Literal[True]

    @field_validator("cancel_plan", mode="before")
    @classmethod
    def explicit_cancellation(cls, value: object) -> object:
        if value is not True:
            raise ValueError("explicit_plan_cancellation_required")
        return value
