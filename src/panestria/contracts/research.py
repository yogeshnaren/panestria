"""Research data contracts; validation never establishes fetch/verifier authority."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictInt, field_validator, model_validator

from panestria.contracts.classification import CanonicalClass, classification_rank, derive_classification

ResearchId = Annotated[str, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
MAX_SOURCE_BYTES = 2 * 1024 * 1024
NORMALIZATION: Literal["nfc-utf8-v1"] = "nfc-utf8-v1"


class ResearchContract(BaseModel):
    model_config = ConfigDict(
        strict=True, extra="forbid", frozen=True, hide_input_in_errors=True, revalidate_instances="always"
    )
    schema_version: StrictInt = Field(default=1, ge=1, le=1)


class ResearchScope(ResearchContract):
    owner_id: ResearchId
    project_id: ResearchId
    goal_id: ResearchId
    task_id: ResearchId


class ResearchLimits(ResearchContract):
    max_sources: StrictInt = Field(default=8, ge=1, le=16)
    max_source_bytes: StrictInt = Field(default=1024 * 1024, ge=1, le=MAX_SOURCE_BYTES)
    max_total_bytes: StrictInt = Field(default=8 * 1024 * 1024, ge=1, le=32 * 1024 * 1024)
    max_redirects: StrictInt = Field(default=3, ge=0, le=5)
    deadline_seconds: float = Field(default=60.0, ge=1, le=300, allow_inf_nan=False)

    @model_validator(mode="after")
    def budgets(self) -> Self:
        if self.max_total_bytes < self.max_source_bytes:
            raise ValueError("research_byte_budget_invalid")
        return self


class ResearchArtifactRef(ResearchContract):
    artifact_id: ResearchId
    task_id: ResearchId
    sha256: Sha256
    size_bytes: StrictInt = Field(ge=0, le=MAX_SOURCE_BYTES)
    privacy_label: CanonicalClass


def _url(value: str) -> str:
    # Syntax only. DNS, addresses, redirects and TLS need the actual fetch broker;
    # even a syntactically valid URL never establishes a successful fetch.
    try:
        parts = urlsplit(value)
        if (
            len(value.encode()) > 2048
            or any(ord(c) <= 32 or ord(c) == 127 for c in value)
            or parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or parts.fragment
            or (parts.port is not None and not 1 <= parts.port <= 65535)
        ):
            raise ValueError("invalid_research_url")
    except ValueError:
        raise ValueError("invalid_research_url") from None
    return value


class ResearchRequestRecord(ResearchContract):
    request_id: ResearchId
    scope: ResearchScope
    question: ResearchArtifactRef
    limits: ResearchLimits

    @model_validator(mode="after")
    def question_scope(self) -> Self:
        if self.question.task_id != self.scope.task_id:
            raise ValueError("research_artifact_scope_mismatch")
        return self


class SourceSnapshotRecord(ResearchContract):
    snapshot_id: ResearchId
    request_id: ResearchId
    scope: ResearchScope
    requested_url: str = Field(min_length=1, max_length=2048)
    terminal_url: str | None = Field(default=None, min_length=1, max_length=2048)
    redirect_receipts: tuple[ResearchArtifactRef, ...] = Field(default=(), max_length=5)
    fetched_at: datetime
    http_status: StrictInt | None = Field(default=None, ge=100, le=599)
    content_type: Literal["text/plain", "text/html", "application/pdf", "application/octet-stream"] | None = None
    byte_limit: StrictInt = Field(ge=1, le=MAX_SOURCE_BYTES)
    query_label: CanonicalClass
    source_label: CanonicalClass
    raw: ResearchArtifactRef | None = None
    text: ResearchArtifactRef | None = None
    extractor_version: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    normalization_version: Literal["nfc-utf8-v1"] = NORMALIZATION
    completeness: Literal["COMPLETE", "TRUNCATED", "UNSUPPORTED", "ERROR"]
    error_code: (
        Literal[
            "http_error",
            "network_error",
            "redirect_denied",
            "size_limit",
            "extractor_unsupported",
            "decoder_error",
            "extractor_error",
        ]
        | None
    ) = None

    @field_validator("requested_url", "terminal_url")
    @classmethod
    def url_syntax(cls, value: str | None) -> str | None:
        return _url(value) if value is not None else None

    @property
    def privacy_label(self) -> CanonicalClass:
        label = derive_classification((self.query_label, self.source_label)).effective
        assert label is not None
        return label

    @model_validator(mode="after")
    def integrity(self) -> Self:
        if self.fetched_at.tzinfo is None or self.fetched_at.utcoffset() is None:
            raise ValueError("research_requires_timezone")
        for artifact in (self.raw, self.text, *self.redirect_receipts):
            if artifact is not None:
                if artifact.task_id != self.scope.task_id:
                    raise ValueError("research_artifact_scope_mismatch")
                if classification_rank(artifact.privacy_label) < classification_rank(self.privacy_label):
                    raise ValueError("research_artifact_label_downgrade")
        if self.raw is not None and self.raw.size_bytes > self.byte_limit:
            raise ValueError("research_byte_limit_exceeded")
        if self.text is not None and self.raw is None:
            raise ValueError("research_raw_lineage_required")
        if len({receipt.artifact_id for receipt in self.redirect_receipts}) != len(self.redirect_receipts):
            raise ValueError("research_redirect_receipt_reused")
        if self.completeness == "COMPLETE" and (
            self.http_status is None
            or not 200 <= self.http_status < 300
            or self.terminal_url is None
            or self.content_type not in {"text/plain", "text/html", "application/pdf"}
            or self.raw is None
            or self.text is None
            or self.raw.size_bytes == 0
            or self.text.size_bytes == 0
            or self.error_code is not None
        ):
            raise ValueError("research_complete_snapshot_invalid")
        if self.completeness != "COMPLETE" and self.error_code is None:
            raise ValueError("research_incomplete_reason_required")
        return self


class PassageRef(ResearchContract):
    snapshot_id: ResearchId
    request_id: ResearchId
    text_sha256: Sha256
    normalization_version: Literal["nfc-utf8-v1"] = NORMALIZATION
    offset_unit: Literal["utf8-byte"] = "utf8-byte"
    start: StrictInt = Field(ge=0, lt=MAX_SOURCE_BYTES)
    end: StrictInt = Field(gt=0, le=MAX_SOURCE_BYTES)

    @model_validator(mode="after")
    def half_open(self) -> Self:
        if self.start >= self.end:
            raise ValueError("research_passage_bounds_invalid")
        return self


class ClaimDraft(ResearchContract):
    text: SecretStr = Field(min_length=1, max_length=8192)
    kind: Literal["FACT", "INTERPRETATION", "OPINION", "QUESTION"]
    passages: tuple[PassageRef, ...] = Field(default=(), max_length=16)

    @model_validator(mode="after")
    def bounded_claim(self) -> Self:
        if len(self.text.get_secret_value().encode()) > 8192:
            raise ValueError("research_claim_byte_limit")
        if len({passage.request_id for passage in self.passages}) > 1:
            raise ValueError("research_claim_request_mismatch")
        return self
