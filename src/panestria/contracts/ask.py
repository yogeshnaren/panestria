"""Offline Ask inputs; prompts cannot grant cloud or retention permission."""

from __future__ import annotations

import hashlib
import json
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from panestria.contracts.policy import DataLabel


class AskSubmission(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    request_id: str
    project_id: str
    question: str = Field(min_length=1, max_length=4096, repr=False)
    privacy_label: DataLabel = "PRIVATE"
    offline: Literal[True] = True
    retain_response: Literal[False] = False
    context_tokens: int = Field(default=2048, ge=512, le=4096)
    max_output_tokens: int = Field(default=128, ge=16, le=1024)
    deadline_seconds: float = Field(default=30.0, ge=0.1, le=60.0)

    @model_validator(mode="after")
    def bounded(self) -> Self:
        UUID(self.request_id)
        UUID(self.project_id)
        if len(self.question.encode()) > 4096 or self.privacy_label == "UNKNOWN":
            raise ValueError("ask_classification_or_size_invalid")
        return self

    def sha256(self) -> str:
        return hashlib.sha256(json.dumps(self.model_dump(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
