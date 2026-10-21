"""Local query proposals are data, never web, acceptance or training authority."""

import json
from typing import Literal, Self

from pydantic import Field, SecretStr, StrictInt, model_validator

from panestria.contracts.research import ResearchContract, ResearchId, ResearchScope, Sha256


class QueryPlanInput(ResearchContract):
    scope: ResearchScope
    request_id: ResearchId
    request_sha256: Sha256
    question_sha256: Sha256
    question_excerpt: SecretStr = Field(min_length=1, max_length=512)
    question_shortened: bool
    task_version: StrictInt = Field(ge=0)
    lease_epoch: StrictInt = Field(ge=0)
    policy_ref: str = Field(pattern=r"^project-policy:[1-9][0-9]*:[0-9a-f]{64}$")
    privacy_label: Literal["PUBLIC"] = "PUBLIC"
    prompt_version: Literal["local-query-plan-v1"] = "local-query-plan-v1"


class QueryPlanResponse(ResearchContract):
    queries: tuple[SecretStr, ...] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def bounded(self) -> Self:
        values = [q.get_secret_value() for q in self.queries]
        if any(
            not q.strip() or q != q.strip() or len(q.encode()) > 256 or any(ord(c) < 32 or ord(c) == 127 for c in q)
            for q in values
        ):
            raise ValueError("query_plan_invalid_query")
        if len({q.casefold() for q in values}) != len(values):
            raise ValueError("query_plan_duplicate_query")
        return self


class RetainedQueryPlan(ResearchContract):
    schema_version: Literal[1] = 1
    plan_id: ResearchId
    purpose: Literal["UNVERIFIED_LOCAL_QUERY_PROPOSAL"] = "UNVERIFIED_LOCAL_QUERY_PROPOSAL"
    packet: QueryPlanInput
    response: QueryPlanResponse
    input_sha256: Sha256
    prompt_sha256: Sha256
    model_ref: str
    model_digest: Sha256
    input_tokens: StrictInt = Field(ge=0)
    output_tokens: StrictInt = Field(ge=0, le=512)
    model_request_elapsed_seconds: float = Field(ge=0, allow_inf_nan=False)
    query_quality: Literal["NOT_ASSESSED"] = "NOT_ASSESSED"
    web_authority: Literal["NONE"] = "NONE"
    task_completion_authority: Literal["NONE"] = "NONE"
    training_eligibility: Literal["UNKNOWN"] = "UNKNOWN"


def packet_bytes(packet: QueryPlanInput) -> bytes:
    body = packet.model_dump(mode="json")
    body["question_excerpt"] = packet.question_excerpt.get_secret_value()
    return json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def plan_bytes(plan: RetainedQueryPlan) -> bytes:
    body = plan.model_dump(mode="json")
    body["packet"] = json.loads(packet_bytes(plan.packet))
    body["response"]["queries"] = [q.get_secret_value() for q in plan.response.queries]
    return json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
