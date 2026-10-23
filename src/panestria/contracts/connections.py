"""Versioned connection declarations; validation is never a runtime permit."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from datetime import UTC
from typing import Annotated, Any, Literal, Self, TypeVar
from urllib.parse import urlsplit

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from panestria.contracts.classification import CanonicalClass, classification_rank
from panestria.contracts.native_model import NativeModel

ConnectionId = Annotated[str, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
ConnectionAction = Literal["read", "write", "send", "delete", "spend"]
PolicyRef = Annotated[str, Field(pattern=r"^project-policy:[1-9][0-9]{0,18}:[0-9a-f]{64}$")]


class ConnectionContract(BaseModel):
    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True, revalidate_instances="always"
    )


class ConnectionBudget(ConnectionContract):
    max_calls: StrictInt = Field(ge=1, le=10_000)
    max_bytes: StrictInt = Field(ge=1, le=64 * 1024 * 1024)
    max_cash_microusd: StrictInt = Field(default=0, ge=0, le=1_000_000)
    max_wall_seconds: StrictInt = Field(ge=1, le=3600)


class ConnectionManifest(ConnectionContract):
    schema_version: StrictInt = Field(default=1, ge=1, le=3)
    owner_id: ConnectionId
    project_id: ConnectionId
    connector_ref: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    connector_version: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")
    configuration_sha256: Digest
    account_ref: ConnectionId
    actions: tuple[ConnectionAction, ...] = Field(min_length=1, max_length=5)
    data_classes: tuple[CanonicalClass, ...] = Field(min_length=1, max_length=4)
    # Opaque immutable enrollment references, not unvalidated filesystem paths.
    # A future file broker must resolve and hold actual roots before use.
    root_refs: tuple[Digest, ...] = Field(default=(), max_length=16)
    origins: tuple[str, ...] = Field(default=(), max_length=16)
    budget: ConnectionBudget
    expires_at: AwareDatetime
    conformance_sha256: Digest | None = None
    provider_route: Literal["claude-subscription"] | None = Field(default=None, exclude_if=lambda value: value is None)
    budget_scope: Literal["SELECTED_PUBLIC_CONTEXT_AND_NATIVE_LAUNCHES"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    requested_model: NativeModel | None = Field(default=None, exclude_if=lambda value: value is None)

    @field_validator("actions", "root_refs")
    @classmethod
    def canonical_set(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("duplicate_connection_scope")
        return tuple(sorted(value))

    @field_validator("data_classes")
    @classmethod
    def canonical_labels(cls, value: tuple[CanonicalClass, ...]) -> tuple[CanonicalClass, ...]:
        if len(set(value)) != len(value):
            raise ValueError("duplicate_connection_scope")
        return tuple(sorted(value, key=classification_rank))

    @field_validator("origins")
    @classmethod
    def exact_https_origins(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for origin in value:
            try:
                parts = urlsplit(origin)
                host = parts.hostname or ""
                if (
                    len(origin.encode()) > 261
                    or not host.isascii()
                    or len(host) > 253
                    or "." not in host
                    or any(
                        re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) is None
                        for label in host.split(".")
                    )
                    or origin != "https://" + host
                ):
                    raise ValueError
                try:
                    ipaddress.ip_address(host)
                except ValueError:
                    pass
                else:
                    raise ValueError
            except (ValueError, UnicodeError):
                raise ValueError("invalid_connection_origin") from None
        if len(set(value)) != len(value):
            raise ValueError("duplicate_connection_scope")
        # Syntax only: DNS/SSRF/TLS and every redirect still require the broker.
        return tuple(sorted(value))

    @field_validator("expires_at")
    @classmethod
    def utc_expiry(cls, value: AwareDatetime) -> AwareDatetime:
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def bounded_scope(self) -> Self:
        if self.schema_version in {2, 3}:
            if (
                self.connector_ref != "claude-public-bash"
                or (
                    self.schema_version == 2
                    and (self.connector_version != "account-context-v1" or self.requested_model)
                )
                or (
                    self.schema_version == 3
                    and (self.connector_version != "model-context-v2" or self.requested_model is None)
                )
                or self.provider_route != "claude-subscription"
                or self.budget_scope != "SELECTED_PUBLIC_CONTEXT_AND_NATIVE_LAUNCHES"
                or len(self.root_refs) != 1
                or self.origins
                or set(self.actions) != {"read", "write", "send"}
                or self.data_classes != ("PUBLIC",)
                or self.budget.max_cash_microusd != 0
                or self.budget.max_calls > 64
            ):
                raise ValueError("native_connection_scope_invalid")
            return self
        if self.provider_route is not None or self.budget_scope is not None or self.requested_model is not None:
            raise ValueError("connection_v1_route_invalid")
        if not self.root_refs and not self.origins:
            raise ValueError("unbounded_connection_scope")
        # Remote APIs may write/delete within exact origins; filesystem
        # connectors require enrolled roots at their broker, not a universal
        # local-only assumption here. Neither action implies send permission.
        if "send" in self.actions and not self.origins:
            raise ValueError("connection_origins_required")
        if "spend" in self.actions and self.budget.max_cash_microusd == 0:
            raise ValueError("connection_cash_budget_required")
        return self

    def sha256(self) -> str:
        return hashlib.sha256(
            json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


class ConnectionReviewRequest(ConnectionContract):
    proposal_id: ConnectionId
    policy_ref: PolicyRef
    grant_id: ConnectionId | None = None
    expected_version: StrictInt = Field(ge=0, le=1_000_000)
    operation: Literal["REPLACE", "REVOKE"]
    manifest: ConnectionManifest | None = None

    @model_validator(mode="after")
    def change_shape(self) -> Self:
        # Leave a final revision available to revoke the last active declaration.
        if self.operation == "REPLACE" and self.expected_version == 1_000_000:
            raise ValueError("connection_revision_limit")
        if (self.operation == "REPLACE") != (self.manifest is not None):
            raise ValueError("invalid_connection_change")
        if self.grant_id is None and self.expected_version != 0:
            raise ValueError("invalid_connection_version")
        if self.operation == "REVOKE" and (self.grant_id is None or self.expected_version == 0):
            raise ValueError("invalid_connection_revoke")
        return self


class SubmitReview(ConnectionContract):
    schema_version: StrictInt = Field(ge=1, le=1)
    task_id: ConnectionId
    change: ConnectionReviewRequest


class DecideReview(ConnectionContract):
    schema_version: StrictInt = Field(ge=1, le=1)
    effect_digest: Digest
    decision: Literal["approve", "deny"]


class ConnectionReviewView(ConnectionContract):
    schema_version: Literal[1]
    proposal_id: ConnectionId
    grant_id: ConnectionId
    expected_version: StrictInt = Field(ge=0, le=1_000_000)
    effect_digest: Digest
    operation: Literal["REPLACE", "REVOKE"]
    policy_ref: PolicyRef
    review_expires_at: AwareDatetime
    manifest: ConnectionManifest
    state: Literal["PENDING", "EXPIRED", "APPROVED", "DENIED"]
    replayed: bool
    authority: Literal["DECLARATION_ONLY"]
    conformance_status: Literal["UNVERIFIED"]
    runtime_available: Literal[False]


class ConnectionScopeView(ConnectionContract):
    schema_version: Literal[1] = 1
    owner_id: ConnectionId
    project_id: ConnectionId
    policy_ref: PolicyRef
    authority: Literal["DECLARATION_ONLY"] = "DECLARATION_ONLY"
    conformance_status: Literal["UNVERIFIED"] = "UNVERIFIED"
    runtime_available: Literal[False] = False


class ConnectionGrantView(ConnectionContract):
    schema_version: Literal[1]
    grant_id: ConnectionId
    version: StrictInt = Field(ge=1, le=1_000_001)
    state: Literal["DECLARED_ACTIVE", "DECLARED_REVOKED", "EXPIRED"]
    policy_ref: PolicyRef
    policy_status: Literal["CURRENT", "STALE"]
    manifest: ConnectionManifest
    authority: Literal["DECLARATION_ONLY"]
    conformance_status: Literal["UNVERIFIED"]
    runtime_available: Literal[False]


class ConnectionDecisionView(ConnectionContract):
    schema_version: Literal[1]
    proposal_id: ConnectionId
    grant_id: ConnectionId
    decision: Literal["APPROVED", "DENIED"]
    granted_version: StrictInt | None = Field(ge=1, le=1_000_001)
    effect_digest: Digest
    replayed: bool
    authority: Literal["DECLARATION_ONLY"]
    conformance_status: Literal["UNVERIFIED"]
    runtime_available: Literal[False]

    @model_validator(mode="after")
    def version_binding(self) -> Self:
        if (self.decision == "APPROVED") != (self.granted_version is not None):
            raise ValueError("connection_decision_version_invalid")
        return self


M = TypeVar("M", bound=ConnectionContract)


def parse_connection_contract(model: type[M], raw: bytes) -> M:
    """JSON-mode strict validation without duplicate keys or nonfinite values."""

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name, value in pairs:
            if name in result:
                raise ValueError("duplicate_connection_key")
            result[name] = value
        return result

    def constant(_: str) -> None:
        raise ValueError("nonfinite_connection_value")

    if not 0 < len(raw) <= 65536:
        raise ValueError("connection_document_size_limit")
    json.loads(raw, object_pairs_hook=unique, parse_constant=constant)
    return model.model_validate_json(raw)
