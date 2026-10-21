"""Exact owner judgments on a retained draft, separate from model qualification."""

import hashlib
import json
from typing import Literal, Self

from pydantic import Field, SecretStr, StrictInt, model_validator

from panestria.contracts.research import ResearchContract, ResearchId, Sha256
from panestria.contracts.research_synthesis import RetainedSynthesis, SynthesisClaim, synthesis_json


def claim_digest(claim: SynthesisClaim) -> str:
    body = {**claim.model_dump(mode="json"), "text": claim.text.get_secret_value()}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class ClaimJudgment(ResearchContract):
    ordinal: StrictInt = Field(ge=0, le=3)
    claim_sha256: Sha256
    verdict: Literal["UNREVIEWED", "SUPPORTED", "PARTIALLY_SUPPORTED", "CONTRADICTED", "INSUFFICIENT", "NOT_FACTUAL"]
    citations: tuple[str, ...] = Field(default=(), max_length=4)
    rationale: SecretStr = Field(default=SecretStr(""), max_length=1024)

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if len(self.rationale.get_secret_value().encode()) > 2048 or len(set(self.citations)) != len(self.citations):
            raise ValueError("invalid_claim_judgment")
        return self


class OwnerDraftReview(ResearchContract):
    schema_version: Literal[1] = 1
    purpose: Literal["OWNER_REPORTED_CLAIM_JUDGMENTS"] = "OWNER_REPORTED_CLAIM_JUDGMENTS"
    request_id: ResearchId
    draft_sha256: Sha256
    claims: tuple[ClaimJudgment, ...] = Field(min_length=1, max_length=4)

    def bind(self, draft: RetainedSynthesis, *, complete: bool) -> None:
        allowed = {p.citation for p in draft.packet.passages}
        if (
            self.request_id != draft.packet.request_id
            or self.draft_sha256 != hashlib.sha256(synthesis_json(draft)).hexdigest()
            or len(self.claims) != len(draft.response.claims)
        ):
            raise ValueError("review_draft_changed")
        for ordinal, (judgment, claim) in enumerate(zip(self.claims, draft.response.claims, strict=True)):
            if (
                judgment.ordinal != ordinal
                or judgment.claim_sha256 != claim_digest(claim)
                or set(judgment.citations) - allowed
            ):
                raise ValueError("review_claim_binding_invalid")
            if complete and (
                judgment.verdict == "UNREVIEWED"
                or not judgment.rationale.get_secret_value().strip()
                or judgment.verdict in {"SUPPORTED", "PARTIALLY_SUPPORTED", "CONTRADICTED"}
                and not judgment.citations
            ):
                raise ValueError("review_incomplete")


def review_json(review: OwnerDraftReview) -> bytes:
    body = review.model_dump(mode="json")
    for row, claim in zip(body["claims"], review.claims, strict=True):
        row["rationale"] = claim.rationale.get_secret_value()
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    if len(raw) > 16384:
        raise ValueError("review_size_limit")
    return raw


def review_template(draft: RetainedSynthesis) -> OwnerDraftReview:
    return OwnerDraftReview(
        request_id=draft.packet.request_id,
        draft_sha256=hashlib.sha256(synthesis_json(draft)).hexdigest(),
        claims=tuple(
            ClaimJudgment(ordinal=i, claim_sha256=claim_digest(c), verdict="UNREVIEWED")
            for i, c in enumerate(draft.response.claims)
        ),
    )
