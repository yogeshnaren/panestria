"""Bounded provider inputs, honest usage and completed versus partial results."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from panestria.contracts.policy import DataLabel


class InferenceRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    owner_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    project_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    request_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    model_ref: str = Field(min_length=1, max_length=128)
    prompt: str = Field(min_length=1, max_length=8192, repr=False)
    label: DataLabel
    offline: bool = True
    max_output_tokens: int = Field(default=128, ge=16, le=1024)
    context_tokens: int = Field(default=2048, ge=512, le=4096)
    deadline_seconds: float = Field(default=30.0, ge=0.1, le=60.0)
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")

    @model_validator(mode="after")
    def bounded_bytes(self) -> InferenceRequest:
        if len(self.prompt.encode()) > 8192:
            raise ValueError("prompt_byte_limit")
        return self

    def sha256(self) -> str:
        return hashlib.sha256(json.dumps(self.model_dump(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class Usage:
    input_tokens: int | None
    output_tokens: int | None
    cash_actual_microusd: int | None = None
    cash_estimate_microusd: int | None = None
    quota_remaining: int | None = None


@dataclass(frozen=True)
class InferenceResult:
    model_ref: str
    text: str
    usage: Usage
    elapsed_seconds: float
    first_token_seconds: float | None
    completion: Literal["COMPLETED"] = "COMPLETED"


class InferenceUnavailable(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class CloudAuthorizer(Protocol):
    def require(self, request: InferenceRequest, provider: str, upper_cash_microusd: int) -> None: ...
