"""Closed deterministic claim evidence; semantic support is deliberately unassessed."""

from typing import Literal, Self

from pydantic import Field, SecretStr, StrictInt, model_validator

from panestria.contracts.classification import CanonicalClass
from panestria.contracts.research import ClaimDraft, PassageRef, ResearchContract, ResearchId, ResearchScope, Sha256


class QuotedPassage(ResearchContract):
    reference: PassageRef
    quote: SecretStr = Field(min_length=1, max_length=8192)

    @model_validator(mode="after")
    def byte_limit(self) -> Self:
        if len(self.quote.get_secret_value().encode()) > 8192:
            raise ValueError("claim_quote_byte_limit")
        return self


class ClaimEvidenceDraft(ResearchContract):
    claim: ClaimDraft
    quotes: tuple[QuotedPassage, ...] = Field(default=(), max_length=16)

    @model_validator(mode="after")
    def references(self) -> Self:
        refs = [ref.model_dump_json() for ref in self.claim.passages]
        quotes = [quoted.reference.model_dump_json() for quoted in self.quotes]
        if len(set(refs)) != len(refs) or len(set(quotes)) != len(quotes) or any(ref not in refs for ref in quotes):
            raise ValueError("claim_reference_set_invalid")
        return self


class RetainedClaimPayload(ResearchContract):
    claim_id: ResearchId
    request_id: ResearchId
    scope: ResearchScope
    input_label: CanonicalClass
    draft: ClaimEvidenceDraft


class ClaimPassageCheck(ResearchContract):
    ordinal: StrictInt = Field(ge=0, lt=16)
    reference: PassageRef
    verdict: Literal["EVIDENCE_PRESENT", "INVALID_EVIDENCE"]
    diagnostic: Literal["retained_passage", "source_unavailable", "quote_mismatch"]
    source_metadata_sha256: Sha256 | None = None
    quote_checked: bool
    limitations: tuple[str, ...] = Field(default=(), max_length=5)

    @model_validator(mode="after")
    def evidence_binding(self) -> Self:
        allowed = {
            "html-tokenizer-only",
            "html-layout-unverified",
            "pdf-text-layer-only",
            "pdf-no-ocr",
            "pdf-layout-unverified",
        }
        if len(set(self.limitations)) != len(self.limitations) or set(self.limitations) - allowed:
            raise ValueError("claim_source_limitations_invalid")
        if (self.verdict == "EVIDENCE_PRESENT") != (
            self.source_metadata_sha256 is not None and self.diagnostic == "retained_passage"
        ):
            raise ValueError("claim_evidence_binding_invalid")
        return self


class ClaimEvidenceReport(ResearchContract):
    claim_id: ResearchId
    request_id: ResearchId
    scope: ResearchScope
    payload_sha256: Sha256
    verifier_version: Literal["source-citation-v1"] = "source-citation-v1"
    verdict: Literal["NO_EVIDENCE", "INVALID_EVIDENCE", "EVIDENCE_PRESENT"]
    support_status: Literal["NOT_ASSESSED"] = "NOT_ASSESSED"
    privacy_label: CanonicalClass
    checks: tuple[ClaimPassageCheck, ...] = Field(default=(), max_length=16)

    @model_validator(mode="after")
    def whole_claim(self) -> Self:
        expected = (
            "NO_EVIDENCE"
            if not self.checks
            else (
                "INVALID_EVIDENCE"
                if any(check.verdict == "INVALID_EVIDENCE" for check in self.checks)
                else "EVIDENCE_PRESENT"
            )
        )
        if self.verdict != expected or tuple(c.ordinal for c in self.checks) != tuple(range(len(self.checks))):
            raise ValueError("claim_report_verdict_invalid")
        return self
