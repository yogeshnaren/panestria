"""Unverified local drafts with controller-owned retained-passage citations."""

import json
from typing import Literal, Self

from pydantic import Field, SecretStr, StrictInt, model_validator

from panestria.contracts.research import PassageRef, ResearchContract, ResearchId, ResearchScope, Sha256


class SynthesisPassage(ResearchContract):
    citation: str = Field(pattern=r"^p[1-4]$")
    reference: PassageRef
    source_metadata_sha256: Sha256
    quote: SecretStr = Field(min_length=1, max_length=384)
    url: SecretStr
    shortened: bool
    limitations: tuple[str, ...]


class SynthesisPacket(ResearchContract):
    scope: ResearchScope
    request_id: ResearchId
    request_sha256: Sha256
    question_sha256: Sha256
    question_excerpt: SecretStr = Field(min_length=1, max_length=512)
    question_shortened: bool
    task_version: StrictInt = Field(ge=0)
    lease_epoch: StrictInt = Field(ge=0)
    policy_ref: str = Field(pattern=r"^project-policy:[1-9][0-9]*:[0-9a-f]{64}$")
    passages: tuple[SynthesisPassage, ...] = Field(min_length=1, max_length=4)
    omitted_passages: StrictInt = Field(ge=0)
    privacy_label: Literal["PUBLIC"] = "PUBLIC"
    prompt_version: Literal["retained-draft-v1"] = "retained-draft-v1"


class SynthesisClaim(ResearchContract):
    text: SecretStr = Field(min_length=1, max_length=2000)
    kind: Literal["FACT", "INTERPRETATION", "OPINION"]
    citations: tuple[str, ...] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if len(self.text.get_secret_value().encode()) > 2000 or len(set(self.citations)) != len(self.citations):
            raise ValueError("invalid_synthesis_claim")
        return self


class SynthesisResponse(ResearchContract):
    claims: tuple[SynthesisClaim, ...] = Field(min_length=1, max_length=4)


class RetainedSynthesis(ResearchContract):
    purpose: Literal["UNVERIFIED_LOCAL_RESEARCH_DRAFT"] = "UNVERIFIED_LOCAL_RESEARCH_DRAFT"
    synthesis_id: ResearchId
    input_sha256: Sha256
    packet: SynthesisPacket
    response: SynthesisResponse
    model_ref: str
    model_digest: Sha256
    prompt_sha256: Sha256
    input_tokens: StrictInt = Field(ge=0)
    output_tokens: StrictInt = Field(ge=0, le=768)
    semantic_support: Literal["NOT_ASSESSED"] = "NOT_ASSESSED"
    contradictions: Literal["NOT_ASSESSED"] = "NOT_ASSESSED"
    task_completion_authority: Literal["NONE"] = "NONE"
    limitations: tuple[str, ...] = (
        "Model-generated claims are untrusted; valid citations do not establish factual support.",
        "Only the bounded question excerpt and selected passage prefixes were provided to the model.",
        "Source instructions cannot authorize tools, egress, approvals or policy changes.",
        "This draft neither completes the task nor grants permission to train on the result.",
    )

    @model_validator(mode="after")
    def citation_membership(self) -> Self:
        allowed = {p.citation for p in self.packet.passages}
        if len(allowed) != len(self.packet.passages) or any(set(c.citations) - allowed for c in self.response.claims):
            raise ValueError("unknown_synthesis_citation")
        return self


def packet_json(packet: SynthesisPacket) -> bytes:
    body = packet.model_dump(mode="json")
    body["question_excerpt"] = packet.question_excerpt.get_secret_value()
    for item, source in zip(body["passages"], packet.passages, strict=True):
        item["quote"], item["url"] = source.quote.get_secret_value(), source.url.get_secret_value()
    return json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def synthesis_json(draft: RetainedSynthesis) -> bytes:
    body = draft.model_dump(mode="json")
    body["packet"] = json.loads(packet_json(draft.packet))
    for item, claim in zip(body["response"]["claims"], draft.response.claims, strict=True):
        item["text"] = claim.text.get_secret_value()
    raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    if len(raw) > 65536:
        raise ValueError("synthesis_output_limit")
    return raw
