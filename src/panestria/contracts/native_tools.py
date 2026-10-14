"""Worker input is data; scope and dispatch authority come from the controller."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_PAYLOAD_BYTES = 32 * 1024
MAX_REQUEST_BYTES = 64 * 1024


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise ValueError("nonfinite_json")


def canonical_payload(raw: str) -> str:
    try:
        if len(raw.encode()) > MAX_PAYLOAD_BYTES:
            raise ValueError("payload_limit")
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
        if not isinstance(value, dict):
            raise ValueError("payload_object_required")
        pending: list[tuple[Any, int]] = [(value, 0)]
        while pending:
            node, depth = pending.pop()
            if depth > 16:
                raise ValueError("payload_depth")
            if isinstance(node, dict):
                pending.extend((child, depth + 1) for child in node.values())
            elif isinstance(node, list):
                pending.extend((child, depth + 1) for child in node)
        canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
        if len(canonical.encode()) > MAX_PAYLOAD_BYTES:
            raise ValueError("payload_limit")
        return canonical
    except (ValueError, TypeError, UnicodeError, RecursionError):
        # Never include a prompt or arbitrary parser exception in diagnostics.
        raise ValueError("invalid_tool_payload") from None


class ToolRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    request_id: UUID
    command_ref: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    payload_json: str = Field(max_length=MAX_PAYLOAD_BYTES)

    @field_validator("payload_json")
    @classmethod
    def validate_payload(cls, value: str) -> str:
        return canonical_payload(value)

    def canonical_bytes(self) -> bytes:
        data = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
        if len(data) > MAX_REQUEST_BYTES:
            raise ValueError("tool_request_limit")
        return data

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


class ToolScope(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    owner_id: UUID
    project_id: UUID
    task_id: UUID
    attempt_id: UUID
    lease_epoch: int = Field(ge=1)
    contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_ref: str = Field(min_length=1, max_length=128)

    def sha256(self) -> str:
        return hashlib.sha256(
            json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
