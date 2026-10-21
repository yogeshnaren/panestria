"""Immutable offline reference metadata; reference retention is not training consent."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


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


class OfflineBuildReference(Closed):
    schema_version: Literal[1] = 1
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
