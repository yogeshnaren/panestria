"""Canonical acceptance checks. R2 runners are recognized and refused."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class ContractRejected(Exception):
    """Non-retryable contract denial. The message is a stable code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class TrustedCommandRef(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    type: Literal["trusted-command-ref"]
    command_ref: str = Field(min_length=1, max_length=128)
    expected_exit_code: int = Field(ge=0, le=255)
    timeout_seconds: int = Field(ge=1, le=3600)


class GitDiffPathCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    type: Literal["git-diff-path-check"]
    allowed_paths: list[str] = Field(min_length=1)
    forbidden_paths: list[str] = Field(min_length=1)


class PolicyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    type: Literal["policy-decision"]
    action: str = Field(min_length=1)
    expected: Literal["allow", "deny", "approval-required"]


class ArtifactExists(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    type: Literal["artifact-exists"]
    artifact_ref: str = Field(min_length=1)
    expected_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class HumanReview(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    type: Literal["human-review"]
    reviewer_ref: str = Field(min_length=1)
    evidence_requirements: list[str] = Field(min_length=1)


class CitationCheck(BaseModel):
    """Canonical R2 verifier. R0 admits the type and refuses to run it."""

    model_config = ConfigDict(extra="forbid", strict=True)

    type: Literal["citation-check"]
    source_manifest_ref: str = Field(min_length=1)
    claims_ref: str = Field(min_length=1)


class RubricReview(BaseModel):
    """Canonical R2 verifier. R0 admits the type and refuses to run it."""

    model_config = ConfigDict(extra="forbid", strict=True)

    type: Literal["rubric-review"]
    rubric_ref: str = Field(min_length=1)
    calibration_set_ref: str = Field(min_length=1)
    reviewer_ref: str = Field(min_length=1)


Verifier = Annotated[
    TrustedCommandRef | GitDiffPathCheck | PolicyDecision | ArtifactExists | HumanReview | CitationCheck | RubricReview,
    Field(discriminator="type"),
]
R0_VERIFIERS = frozenset(
    {
        "trusted-command-ref",
        "git-diff-path-check",
        "policy-decision",
        "artifact-exists",
        "human-review",
    }
)
R2_VERIFIERS = frozenset({"citation-check", "rubric-review"})
LEGACY_VERIFIERS = frozenset(
    {
        "command",
        "trusted-command",
        "diff-path-check",
        "policy",
        "human-approval",
        "manual-evidence",
        "file_exists",
        "citations",
        "rubric",
    }
)


class EvidenceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    required: Literal[True]
    kind: str = Field(min_length=1)


class AcceptanceCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=1024)
    required: bool
    verifier: Verifier
    evidence: EvidenceSpec
