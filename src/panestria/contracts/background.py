"""Owner-reviewed background constraints; no quota observation grants dispatch."""

from typing import Literal, Self

from pydantic import AwareDatetime, Field, StrictInt, model_validator

from panestria.contracts.native_model import NativeModel
from panestria.contracts.plan import PlanContract, PlanId, PlanSha
from panestria.contracts.quota import QuotaId, QuotaScope


class BillingBoundary(PlanContract):
    source: Literal["OWNER_REPORTED"] = "OWNER_REPORTED"
    reported_by: PlanId
    account_ref: QuotaId
    observed_at: AwareDatetime
    fresh_for_seconds: StrictInt = Field(default=900, ge=1, le=3600)
    usage_credits_enabled: bool | None = None
    # This is an explicit account-settings report, not provider telemetry or a
    # CLI dollar estimate. It does not alter any billing setting.


class BackgroundWorkPolicy(PlanContract):
    schema_version: StrictInt = Field(default=1, ge=1, le=2)
    policy_id: PlanId
    owner_id: PlanId
    project_id: PlanId
    version: StrictInt = Field(default=1, ge=1, le=1)
    provider: Literal["claude-subscription"] = "claude-subscription"
    model_ref: NativeModel | None = None  # Legacy null bytes remain part of the original policy hash.
    quota_windows: tuple[QuotaScope, ...] = Field(min_length=1, max_length=4)
    billing: BillingBoundary | None = None
    allow_unknown_quota: bool = False
    allow_estimated_quota: bool = False
    regular_use_reserve_percent: StrictInt = Field(default=20, ge=1, le=99)
    regular_use_reserve_tokens: StrictInt = Field(default=10000, ge=1, le=10000000)
    regular_use_reserve_requests: StrictInt = Field(default=2, ge=1, le=10000)
    maximum_job_wall_seconds: StrictInt = Field(default=300, ge=30, le=900)
    maximum_background_workers: StrictInt = Field(default=1, ge=1, le=1)
    foreground_reserve_slots: StrictInt = Field(default=1, ge=1, le=1)
    api_microusd: StrictInt = Field(default=0, ge=0, le=0)
    privacy_class: Literal["PUBLIC"] = "PUBLIC"
    categories: tuple[Literal["PUBLIC_BUILD", "ARCHITECTURE_REVIEW", "TEST_DESIGN"], ...] = ("PUBLIC_BUILD",)
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def scope(self) -> Self:
        accounts = {s.account_ref for s in self.quota_windows}
        if (self.schema_version == 1) != (self.model_ref is None):
            raise ValueError("background_model_policy_version")
        if len(accounts) != 1 or any(
            s.provider != self.provider or s.model_ref not in {None, self.model_ref} for s in self.quota_windows
        ):
            raise ValueError("background_account_or_model_scope")
        if self.model_ref is not None and (
            not any(s.model_ref == self.model_ref for s in self.quota_windows)
            or not any(s.model_ref is None for s in self.quota_windows)
        ):
            raise ValueError("background_account_and_model_windows_required")
        if len({s.sha256() for s in self.quota_windows}) != len(self.quota_windows):
            raise ValueError("background_duplicate_windows")
        if self.billing is not None and (
            self.billing.reported_by != self.owner_id or self.billing.account_ref not in accounts
        ):
            raise ValueError("background_billing_report_owner")
        if not self.categories or len(set(self.categories)) != len(self.categories) or len(self.categories) > 3:
            raise ValueError("background_categories")
        return self


class BackgroundEnqueue(PlanContract):
    schema_version: StrictInt = Field(default=1, ge=1, le=1)
    item_id: PlanId
    plan_id: PlanId
    expected_plan_sha256: PlanSha
    category: Literal["PUBLIC_BUILD", "ARCHITECTURE_REVIEW", "TEST_DESIGN"] = "PUBLIC_BUILD"
    value_priority: StrictInt = Field(default=2, ge=1, le=3)
    policy: BackgroundWorkPolicy


class BackgroundBinding(PlanContract):
    schema_version: StrictInt = Field(default=1, ge=1, le=1)
    request: BackgroundEnqueue
    owner_id: PlanId
    project_id: PlanId
    goal_id: PlanId
    task_id: PlanId
    contract_sha256: PlanSha
    inventory_sha256: PlanSha
    context_sha256: PlanSha
    context_basis: Literal["DECLARED_PLAN_INPUTS_NOT_COMPILED_MODEL_PROMPT"] = (
        "DECLARED_PLAN_INPUTS_NOT_COMPILED_MODEL_PROMPT"
    )
    policy_sha256: PlanSha
    upper_wall_seconds: StrictInt = Field(ge=1)
    execution_authority: Literal["NONE"] = "NONE"
