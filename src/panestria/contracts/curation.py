"""Separate explicit owner evidence for local training-data preparation, never training."""

import hashlib
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt, model_validator

from panestria.contracts.build import canonical_sha256

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Eligibility = Literal["ALLOWED", "DENIED", "UNKNOWN"]
Role = Literal["ORIGIN", "DATA_RIGHTS", "VALIDATION"]


class Closed(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)


class CuratedExample(Closed):
    schema_version: StrictInt = Field(default=1, ge=1, le=1)
    origin: Literal["OWNER_AUTHORED", "PROVIDER_OUTPUT", "LOCAL_MODEL_OUTPUT", "UNKNOWN"] = "UNKNOWN"
    privacy_class: Literal["PUBLIC"]
    input: str = Field(min_length=1, max_length=1024, repr=False)
    response: str = Field(min_length=1, max_length=2048, repr=False)

    @model_validator(mode="after")
    def bounded_bytes(self) -> "CuratedExample":
        if len(self.input.encode()) > 1024 or len(self.response.encode()) > 2048:
            raise ValueError("example_byte_limit")
        return self

    def sha256(self) -> str:
        return canonical_sha256(self.model_dump(mode="json"))

    @property
    def content_sha256(self) -> str:
        return canonical_sha256({"input": self.input, "response": self.response})

    @property
    def input_sha256(self) -> str:
        return hashlib.sha256(self.input.encode()).hexdigest()

    @property
    def fold(self) -> Literal["development", "holdout"]:
        # Exact same input stays in one fold, including different reviewed answers.
        return "holdout" if int(self.input_sha256, 16) % 5 == 0 else "development"


class OwnerEvidence(Closed):
    schema_version: StrictInt = Field(default=1, ge=1, le=1)
    privacy_class: Literal["PUBLIC"]
    role: Role
    subject_sha256: Digest
    assessment: Eligibility = "UNKNOWN"
    basis: str = Field(min_length=1, max_length=2048, repr=False)
    valid_until: AwareDatetime
    assessment_source: Literal["OWNER_ATTESTED"] = "OWNER_ATTESTED"
    provider_basis: Literal["NO_PROVIDER_OR_MODEL_INPUTS"] | None = None
    permitted_purpose: Literal["LOCAL_TRAINING_DATA_PREPARATION"] | None = None
    validation_method: Literal["OWNER_REVIEWED"] | None = None

    @model_validator(mode="after")
    def meaningful_basis(self) -> "OwnerEvidence":
        if not self.basis.strip():
            raise ValueError("owner_evidence_basis_required")
        return self


class CurationPreview(Closed):
    schema_version: StrictInt = Field(default=1, ge=1, le=1)
    owner_id: UUID
    project_id: UUID
    example: CuratedExample
    evidence: tuple[OwnerEvidence, ...] = Field(max_length=3)
    policy_ref: str = Field(pattern=r"^project-policy:[1-9][0-9]*:[a-f0-9]{64}$")
    eligibility_days: StrictInt = Field(ge=1, le=30)
    proposed_eligibility: Eligibility
    reasons: tuple[str, ...]
    purpose: Literal["LOCAL_TRAINING_DATA_PREPARATION"] = "LOCAL_TRAINING_DATA_PREPARATION"
    assessment_source: Literal["OWNER_ATTESTED_NOT_AUTOMATICALLY_VERIFIED"] = (
        "OWNER_ATTESTED_NOT_AUTOMATICALLY_VERIFIED"
    )
    training_export: Literal["DENIED_UNTIL_SEPARATE_OWNER_CONFIRMATION"] = "DENIED_UNTIL_SEPARATE_OWNER_CONFIRMATION"

    def sha256(self) -> str:
        return canonical_sha256(self.model_dump(mode="json"))


class ExportEntry(Closed):
    review_sha256: Digest
    example_sha256: Digest
    example: CuratedExample
    fold: Literal["development", "holdout"]
    evidence_sha256: tuple[Digest, ...] = Field(min_length=3, max_length=3)
    expires_at: AwareDatetime
    training_eligibility: Literal["ALLOWED"] = "ALLOWED"
    assessment_source: Literal["EXPLICIT_OWNER_REVIEW"] = "EXPLICIT_OWNER_REVIEW"


class ExampleExport(Closed):
    schema_version: StrictInt = Field(default=1, ge=1, le=1)
    owner_id: UUID
    project_id: UUID
    created_at: AwareDatetime
    entries: tuple[ExportEntry, ...] = Field(min_length=1, max_length=16)
    purpose: Literal["LOCAL_TRAINING_DATA_PREPARATION"] = "LOCAL_TRAINING_DATA_PREPARATION"
    authority: Literal["DATA_PACKET_NOT_MODEL_PROMOTION"] = "DATA_PACKET_NOT_MODEL_PROMOTION"
    training_started: Literal[False] = False
