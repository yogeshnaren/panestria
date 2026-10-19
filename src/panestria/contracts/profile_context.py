"""Explicit metadata for a bounded offline profile-field request."""

from __future__ import annotations

import hashlib
import json
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from panestria.contracts.profile import ProfileField


class ProfileSelectionRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    profile_id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
    expected_row_version: int = Field(ge=0)
    purpose: Literal["OWNER_ASSISTANCE", "RESPONSE_STYLE", "STRUCTURED_RESPONSE_STYLE"]
    fields: tuple[ProfileField, ...] = Field(min_length=1, max_length=6)
    destination: Literal["OFFLINE_LOCAL_MODEL"]
    max_bytes: int = Field(default=2048, ge=128, le=4096)

    @model_validator(mode="after")
    def purpose_fields(self) -> Self:
        if len(set(self.fields)) != len(self.fields):
            raise ValueError("profile_fields_duplicate")
        if self.purpose == "RESPONSE_STYLE" and not set(self.fields).issubset({"preferred_name", "communication"}):
            raise ValueError("profile_purpose_fields_invalid")
        if self.purpose == "STRUCTURED_RESPONSE_STYLE" and self.fields != ("communication",):
            raise ValueError("structured_style_requires_communication_only")
        return self

    def sha256(self) -> str:
        return hashlib.sha256(json.dumps(self.model_dump(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
