"""Search returns untrusted candidates, never fetched sources or support verdicts."""

from __future__ import annotations

from typing import Literal, Self
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, SecretStr, StrictInt, model_validator

from panestria.contracts.research import ResearchContract, ResearchScope, Sha256


class LocalSearchSettings(ResearchContract):
    provider: Literal["searxng-local"]
    origin: str = Field(min_length=1, max_length=128)
    max_response_bytes: StrictInt = Field(default=64 * 1024, ge=1024, le=1024 * 1024)
    max_results: StrictInt = Field(default=8, ge=1, le=16)
    deadline_seconds: float = Field(default=10.0, ge=0.1, le=30, allow_inf_nan=False)

    @model_validator(mode="after")
    def fixed_operator_endpoint(self) -> Self:
        parts = urlsplit(self.origin)
        if (
            parts.scheme != "http"
            or parts.hostname not in {"127.0.0.1", "::1"}
            or parts.port is None
            or not 1024 <= parts.port <= 65535
            or parts.username is not None
            or parts.password is not None
            or parts.path not in {"", "/"}
            or parts.query
            or parts.fragment
            or any(ord(c) <= 32 or c == "\\" for c in self.origin)
        ):
            raise ValueError("configured_local_search_origin_required")
        return self


class SearchQuery(ResearchContract):
    request_id: UUID
    scope: ResearchScope
    query: SecretStr = Field(min_length=1, max_length=512)
    privacy_class: Literal["PUBLIC"]

    @model_validator(mode="after")
    def bounded_plain_query(self) -> Self:
        text = self.query.get_secret_value()
        # SearXNG !/!! syntax selects engines/categories or redirects externally.
        # Query data cannot select a new routing policy.
        if not text.strip() or len(text.encode()) > 512 or "!" in text or any(ord(c) < 32 for c in text):
            raise ValueError("bounded_plain_public_search_query_required")
        return self


class SearchDisclosure(ResearchContract):
    request_id: UUID
    scope: ResearchScope
    provider: Literal["searxng-local"]
    configuration_sha256: Sha256
    request_sha256: Sha256
    query_sha256: Sha256
    query_bytes: StrictInt = Field(ge=1, le=512)
    privacy_class: Literal["PUBLIC"] = "PUBLIC"
    upstream_disclosure: Literal["POSSIBLE_NOT_OBSERVED"] = "POSSIBLE_NOT_OBSERVED"


class SearchCandidate(ResearchContract):
    url: SecretStr = Field(min_length=1, max_length=2048)
    title: SecretStr = Field(max_length=1024)
    snippet: SecretStr = Field(max_length=8192)
    authority: Literal["UNTRUSTED_UNFETCHED"] = "UNTRUSTED_UNFETCHED"


class SearchResults(ResearchContract):
    disclosure: SearchDisclosure
    response_sha256: Sha256
    candidates: tuple[SearchCandidate, ...] = Field(max_length=16)
    omitted: StrictInt = Field(ge=0)
    engine_error_count: StrictInt = Field(ge=0)
    cash_actual_microusd: None = None
    remaining_quota: None = None
    source_authority: Literal["NONE_FETCH_AND_VERIFY_SEPARATELY"] = "NONE_FETCH_AND_VERIFY_SEPARATELY"
