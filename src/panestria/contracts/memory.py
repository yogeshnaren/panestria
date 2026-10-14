"""User-submitted memory and explicit usage observations."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from panestria.contracts.policy import DataLabel


class MemorySubmission(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    body: str = Field(min_length=1, max_length=8192, repr=False)
    label: DataLabel
    kind: Literal["fact", "preference", "procedure"] = "fact"
    pinned: bool = False
    source_uri: str = Field(default="user-submitted", min_length=1, max_length=512)
    conflict_key: str | None = Field(default=None, min_length=1, max_length=128)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    retain_until: datetime | None = None

    @model_validator(mode="after")
    def validity(self) -> Self:
        if len(self.body.encode()) > 8192 or self.label == "UNKNOWN":
            raise ValueError("memory_requires_classification")
        for when in (self.valid_from, self.valid_until, self.retain_until):
            if when is not None and when.tzinfo is None:
                raise ValueError("memory_requires_timezone")
        if self.valid_from and self.valid_until and self.valid_from >= self.valid_until:
            raise ValueError("invalid_validity")
        return self


MemoryStage = Literal["retrieved", "included", "used_by_worker", "judged_unused", "candidate_helped"]


class MemoryObservation(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    stage: MemoryStage
    observer_kind: Literal["application", "worker_report", "human", "verifier"]
    observer_id: str = Field(min_length=1, max_length=128)
    confidence: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    evidence_ref: str | None = Field(default=None, min_length=1, max_length=256)

    @model_validator(mode="after")
    def causality(self) -> Self:
        if self.stage == "candidate_helped" and (
            self.observer_kind not in {"human", "verifier"} or not self.evidence_ref
        ):
            raise ValueError("help_requires_explicit_assessment")
        if self.observer_kind == "worker_report" and self.confidence is not None and self.confidence > 0.5:
            raise ValueError("worker_report_is_not_verification")
        return self
