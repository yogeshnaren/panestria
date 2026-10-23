"""Common immutable authority binding; a serialized binding grants no execution."""

from typing import Literal

from pydantic import Field

from panestria.contracts.fetch_connection import FetchConnectionBinding
from panestria.contracts.research import ResearchContract, ResearchId, ResearchScope, Sha256

FetchDiagnostic = Literal[
    "retained",
    "fetch_size_limit",
    "fetch_timeout",
    "fetch_http_error",
    "fetch_denied_or_unavailable",
    "reader_truncated",
    "reader_unsupported",
    "reader_unavailable",
    "unconfirmed",
]
CollectionStop = Literal[
    "queries_exhausted",
    "source_limit",
    "body_limit",
    "connection_limit",
    "search_unavailable",
    "interrupted",
]


class ResearchAuthorityBinding(ResearchContract):
    scope: ResearchScope
    request_id: ResearchId
    request_sha256: Sha256
    contract_sha256: Sha256
    policy_sha256: Sha256
    configuration_sha256: Sha256


class FetchPlan(ResearchAuthorityBinding):
    """Source/byte/redirect limits come from the immutable hashed research request."""

    # Old serialized plans remain readable, but missing bindings cannot execute.
    connection: FetchConnectionBinding | None = Field(default=None, exclude_if=lambda value: value is None)
