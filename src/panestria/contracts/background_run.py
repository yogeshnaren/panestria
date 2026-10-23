"""Finite native background coordinator reservation, not another task store."""

from typing import Literal, Self

from pydantic import AwareDatetime, Field, StrictInt, model_validator

from panestria.contracts.native_model import NativeModel
from panestria.contracts.plan import PlanContract, PlanId, PlanSha


class BackgroundRun(PlanContract):
    schema_version: StrictInt = Field(default=1, ge=1, le=2)
    model_ref: NativeModel | None = Field(default=None, exclude_if=lambda value: value is None)
    run_id: PlanId
    owner_id: PlanId
    project_id: PlanId
    item_id: PlanId
    binding_sha256: PlanSha
    link_sha256: PlanSha
    account_observation_sha256: PlanSha
    identity_sha256: PlanSha
    profile_sha256: PlanSha
    binary_sha256: PlanSha
    quota_basis_sha256: PlanSha
    started_at: AwareDatetime
    deadline: AwareDatetime
    maximum_parallel: StrictInt = Field(default=1, ge=1, le=1)
    billing_evidence: Literal["FRESH_OWNER_REPORT_DISABLED_SAME_LINKED_ACCOUNT"] = (
        "FRESH_OWNER_REPORT_DISABLED_SAME_LINKED_ACCOUNT"
    )
    # Lifecycle and actual side effects still use canonical task/attempt/
    # invocation/claim/evidence protocols. This record is no dispatch token.
    dispatch_authority: Literal["NONE"] = "NONE"

    @model_validator(mode="after")
    def model_version(self) -> Self:
        if (self.schema_version == 1) != (self.model_ref is None):
            raise ValueError("background_run_model_version")
        return self
