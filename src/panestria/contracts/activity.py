"""Content-free canonical activity observations, never execution or acceptance."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class ActivityEntry(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)
    id: UUID
    source: Literal["ASK", "GOAL"]
    workflow: Literal["ASK", "DELEGATE", "BUILD", "KERNEL"]
    canonical_state: str = Field(pattern=r"^[A-Z_]{1,32}$")
    created_at: datetime
    active_tasks: StrictInt = Field(ge=0)
    waiting_reviews: StrictInt = Field(ge=0)
    held_build_claims: StrictInt | None = Field(default=None, ge=0)
    needs_attention: bool


class ProjectActivity(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)
    owner_id: UUID
    project_id: UUID
    observed_at: datetime
    entries: tuple[ActivityEntry, ...] = Field(max_length=32)
    storage_available: bool = Field(default=False, exclude_if=lambda v: not v)
    next_cursor: str | None = Field(default=None, max_length=41, pattern=r"^(ASK|GOAL):[0-9a-f-]{36}$")
    view_authority: Literal["READ_ONLY_METADATA"] = "READ_ONLY_METADATA"
    acceptance_authority: Literal["NONE"] = "NONE"


class ActivityEvent(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)
    seq: str = Field(pattern=r"^(0|[1-9][0-9]{0,18})$")
    id: UUID
    kind: str = Field(min_length=1, max_length=128)
    schema_version: StrictInt = Field(ge=1)
    privacy_label: str = Field(pattern=r"^[A-Z_]{1,32}$")


class ActivityTask(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    id: UUID
    state: str = Field(pattern=r"^[A-Z_]{1,32}$")
    row_version: str = Field(pattern=r"^(0|[1-9][0-9]{0,18})$")
    lease_epoch: str = Field(pattern=r"^(0|[1-9][0-9]{0,18})$")


class ActivityGoalSnapshot(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    goal_id: UUID
    status: str = Field(pattern=r"^[A-Z_]{1,32}$")
    cursor: str = Field(pattern=r"^(0|[1-9][0-9]{0,18})$")
    tasks: tuple[ActivityTask, ...]


class ActivityTimeline(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    owner_id: UUID
    project_id: UUID
    events: tuple[ActivityEvent, ...] = Field(max_length=50)
    snapshot: ActivityGoalSnapshot
    next_cursor: str = Field(pattern=r"^(0|[1-9][0-9]{0,18})$")
    resync: bool
    view_authority: Literal["READ_ONLY_METADATA"] = "READ_ONLY_METADATA"
    acceptance_authority: Literal["NONE"] = "NONE"
