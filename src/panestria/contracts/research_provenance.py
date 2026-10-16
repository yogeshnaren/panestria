"""Closed protected receipt formats; model validation alone grants no source authority."""

from datetime import datetime
from typing import Literal, Self

from pydantic import Field, StrictInt, model_validator

from panestria.contracts.research import (
    ResearchArtifactRef,
    ResearchContract,
    ResearchId,
    ResearchScope,
    Sha256,
)


class RetainedFetchHop(ResearchContract):
    url_sha256: Sha256
    address: str = Field(min_length=1, max_length=45)
    status: StrictInt = Field(ge=200, le=599)
    certificate_sha256: Sha256


class RetainedFetchReceipt(ResearchContract):
    scope: ResearchScope
    request_id: ResearchId
    raw: ResearchArtifactRef
    requested_url: str = Field(min_length=1, max_length=2048, repr=False)
    terminal_url: str = Field(min_length=1, max_length=2048, repr=False)
    observed_at: datetime
    content_type: Literal["text/plain", "text/html", "application/pdf"]
    status: StrictInt = Field(ge=200, le=299)
    hops: tuple[RetainedFetchHop, ...] = Field(min_length=1, max_length=6)
    adapter_sha256: Sha256


class RetainedReaderReceipt(ResearchContract):
    scope: ResearchScope
    request_id: ResearchId
    raw: ResearchArtifactRef
    text: ResearchArtifactRef
    extractor_version: Literal["strict-utf8-v1", "htmlparser-text-v1", "pypdf-6.20.1-text-v1"]
    tokenizer_sha256: Sha256
    program_sha256: Sha256
    profile_sha256: Sha256
    effective_config_sha256: Sha256
    normalization_version: Literal["nfc-utf8-v1"] = "nfc-utf8-v1"
    pdf_bundle_sha256: Sha256 | None = None
    page_spans: tuple[tuple[StrictInt, StrictInt], ...] = Field(default=(), max_length=32)
    limitations: tuple[Literal["pdf-text-layer-only", "pdf-no-ocr", "pdf-layout-unverified"], ...] = Field(
        default=(), max_length=3
    )

    @model_validator(mode="after")
    def pdf_metadata(self) -> Self:
        if self.extractor_version == "pypdf-6.20.1-text-v1":
            if (
                not self.page_spans
                or self.pdf_bundle_sha256 is None
                or self.limitations != ("pdf-text-layer-only", "pdf-no-ocr", "pdf-layout-unverified")
            ):
                raise ValueError("pdf_receipt_metadata_required")
        elif self.pdf_bundle_sha256 is not None or self.page_spans or self.limitations:
            raise ValueError("unexpected_pdf_metadata")
        return self


class SourceCaptureProof(ResearchContract):
    snapshot_id: ResearchId
    request_id: ResearchId
    scope: ResearchScope
    metadata_sha256: Sha256
    fetch: ResearchArtifactRef
    reader: ResearchArtifactRef
    fetch_adapter_sha256: Sha256
    reader_program_sha256: Sha256
