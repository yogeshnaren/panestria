"""Content-free pending review discovery; exact review and decisions stay separate."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ReviewInboxEntry(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    kind: Literal["PLAN", "APPROVAL"]
    id: UUID
    goal_id: UUID
    task_id: UUID | None
    canonical_state: Literal["PROPOSED", "PENDING"]
    goal_status: str = Field(pattern=r"^[A-Z_]{1,32}$")
    expires_at: datetime
    expired: bool


class ReviewInbox(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    owner_id: UUID
    project_id: UUID
    observed_at: datetime
    entries: tuple[ReviewInboxEntry, ...] = Field(max_length=32)
    next_cursor: str | None = Field(default=None, pattern=r"^(PLAN|APPROVAL):[0-9a-f-]{36}$")
    view_authority: Literal["READ_ONLY_METADATA"] = "READ_ONLY_METADATA"
    decision_authority: Literal["NONE"] = "NONE"
