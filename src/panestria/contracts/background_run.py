"""Finite native background coordinator reservation, not another task store."""

from typing import Literal

from pydantic import AwareDatetime, Field, StrictInt

from panestria.contracts.plan import PlanContract, PlanId, PlanSha


class BackgroundRun(PlanContract):
    schema_version: StrictInt = Field(default=1, ge=1, le=1)
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
