"""Common immutable authority binding; a serialized binding grants no execution."""

from panestria.contracts.research import ResearchContract, ResearchId, ResearchScope, Sha256


class ResearchAuthorityBinding(ResearchContract):
    scope: ResearchScope
    request_id: ResearchId
    request_sha256: Sha256
    contract_sha256: Sha256
    policy_sha256: Sha256
    configuration_sha256: Sha256


class FetchPlan(ResearchAuthorityBinding):
    """Source/byte/redirect limits come from the immutable hashed research request."""
