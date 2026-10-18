"""Immutable search budget; it cannot expand the underlying goal or policy."""

from pydantic import Field, StrictInt

from panestria.contracts.research import ResearchContract, ResearchId, ResearchScope, Sha256


class SearchPlan(ResearchContract):
    scope: ResearchScope
    request_id: ResearchId
    request_sha256: Sha256
    contract_sha256: Sha256
    policy_sha256: Sha256
    configuration_sha256: Sha256
    max_queries: StrictInt = Field(ge=1, le=16)
