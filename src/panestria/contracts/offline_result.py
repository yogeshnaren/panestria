"""Immutable offline reference metadata; reference retention is not training consent."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
ModelName = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")]


class Closed(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", revalidate_instances="always")


class RetainedPart(Closed):
    sha256: Digest
    size_bytes: int = Field(ge=0, le=256 * 1024)
    chunks: tuple[Digest, ...] = Field(min_length=1, max_length=8)


class InvocationProvenance(Closed):
    invocation_id: UUID
    binding_sha256: Digest
    receipt_sha256: Digest | None
    kind: Literal["native-proposal", "native-tool", "build-integration"]
    controller_source_sha256: Digest | None
    model: None = None
    request_sha256: Digest | None = None
    configuration_sha256: Digest | None = None
    requested_model: ModelName | None = None
    reported_init_model: ModelName | None = None
    selected_context_part: str | None = Field(
        default=None, pattern=r"^native-context-[0-9]{1,2}$", exclude_if=lambda value: value is None
    )


class OfflineBuildReference(Closed):
    schema_version: Literal[1, 2, 3] = 1
    kind: Literal["offline-build-reference"] = "offline-build-reference"
    owner_id: UUID
    project_id: UUID
    goal_id: UUID
    task_id: UUID
    plan_id: UUID
    plan_sha256: Digest
    contract_sha256: Digest
    evidence_sha256: Digest
    base_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    candidate_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    approval_id: UUID
    effect_id: UUID
    effect_digest: Digest
    confirmed_at: AwareDatetime
    captured_under_policy_ref: str
    parts: dict[str, RetainedPart] = Field(min_length=3, max_length=103)
    invocations: tuple[InvocationProvenance, ...] = Field(max_length=64)
    privacy_class: Literal["PUBLIC"] = "PUBLIC"
    validation: Literal["INDEPENDENT_CHECKS_AND_CONFIRMED_MERGE"] = "INDEPENDENT_CHECKS_AND_CONFIRMED_MERGE"
    permitted_purpose: Literal["OWNER_LOCAL_REFERENCE"] = "OWNER_LOCAL_REFERENCE"
    training_eligibility: Literal["UNKNOWN"] = "UNKNOWN"
    training_export: Literal["DENIED"] = "DENIED"
    training_reason: Literal["SEPARATE_PROVIDER_DATA_RIGHTS_AND_PURPOSE_REVIEW_REQUIRED"] = (
        "SEPARATE_PROVIDER_DATA_RIGHTS_AND_PURPOSE_REVIEW_REQUIRED"
    )
    retention: Literal["OWNER_MANAGED_NO_AUTOMATIC_DELETION"] = "OWNER_MANAGED_NO_AUTOMATIC_DELETION"
    authority: Literal["DERIVED_REFERENCE_ONLY"] = "DERIVED_REFERENCE_ONLY"

    @model_validator(mode="after")
    def versioned_identity(self) -> "OfflineBuildReference":
        for invocation in self.invocations:
            if self.schema_version < 3 and invocation.selected_context_part is not None:
                raise ValueError("legacy_reference_context_must_remain_unknown")
            if self.schema_version == 1 and any(
                value is not None
                for value in (
                    invocation.request_sha256,
                    invocation.configuration_sha256,
                    invocation.requested_model,
                    invocation.reported_init_model,
                )
            ):
                raise ValueError("legacy_reference_identity_must_remain_unknown")
            if self.schema_version >= 2 and (
                invocation.request_sha256 is None or invocation.configuration_sha256 is None
            ):
                raise ValueError("reference_invocation_hashes_required")
        return self
