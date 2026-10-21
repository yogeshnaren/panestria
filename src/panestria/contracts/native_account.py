"""Pseudonymous CLI account metadata, separate from execution/billing proof."""

from typing import Literal

from pydantic import AwareDatetime, Field, StrictInt

from panestria.contracts.plan import PlanContract, PlanId, PlanSha


class NativeAccountObservation(PlanContract):
    schema_version: StrictInt = Field(default=1, ge=1, le=1)
    owner_id: PlanId
    project_id: PlanId
    account_ref: PlanId
    observed_at: AwareDatetime
    source: Literal["PINNED_CLI_AUTH_STATUS"] = "PINNED_CLI_AUTH_STATUS"
    provider: Literal["claude-subscription"] = "claude-subscription"
    identity_sha256: PlanSha
    identity_basis: Literal["ACCOUNT_ID", "EMAIL"]
    profile_sha256: PlanSha
    binary_sha256: PlanSha
    compatibility_sha256: PlanSha
    subscription_type: Literal["pro", "max"]
    privacy_class: Literal["INTERNAL"] = "INTERNAL"
    billing_verified: Literal[False] = False
    inference_verified: Literal[False] = False
    execution_authority: Literal["NONE"] = "NONE"


class BackgroundAccountLink(PlanContract):
    schema_version: StrictInt = Field(default=1, ge=1, le=1)
    owner_id: PlanId
    project_id: PlanId
    item_id: PlanId
    binding_sha256: PlanSha
    observation_sha256: PlanSha
    identity_sha256: PlanSha
    profile_sha256: PlanSha
    account_ref: PlanId
    binary_sha256: PlanSha
    execution_authority: Literal["NONE"] = "NONE"
