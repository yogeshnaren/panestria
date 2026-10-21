"""Bounded read-only PUBLIC Build discovery; no execution or approval authority."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BuildGoalSummary(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    goal_id: UUID
    title: str = Field(max_length=120)
    status: Literal["CREATED", "ACTIVE", "COMPLETED", "FAILED", "CANCELLED"]
    created_at: str
    review_available: bool
    running_tasks: int = Field(ge=0)
    waiting_reviews: int = Field(ge=0)


class BuildGoalIndex(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    schema_version: Literal[1] = 1
    owner_id: UUID
    project_id: UUID
    goals: tuple[BuildGoalSummary, ...] = Field(max_length=32)
    authority: Literal["READ_ONLY_METADATA"] = "READ_ONLY_METADATA"
