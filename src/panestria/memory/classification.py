"""Scoped read-only source classification history; no reclassification authority."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from panestria.contracts.classification import CanonicalClass, resolve_classification
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.uow import UnitOfWork


class SourceClassification(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    source_id: str
    source_sha256: str
    original_label: str
    effective_label: CanonicalClass
    interpretation: Literal["CANONICAL", "LEGACY_RESTRICTED"]
    resolver_version: Literal[1]
    origin: Literal["MIGRATION", "SOURCE_WRITE"]
    consented_by: str
    policy_ref: str | None
    review_id: str | None
    review_effect_digest: str | None
    review_decided_by: str | None
    created_at: datetime


class MemoryClassificationService:
    def get(self, uow: UnitOfWork, actor: Actor, source_id: str) -> SourceClassification:
        row = uow.execute(
            "SELECT source_id::text,source_sha256,original_label,effective_label,interpretation,resolver_version,"
            " origin,consented_by::text,policy_ref,review_id::text,review_effect_digest,"
            " review_decided_by::text,created_at"
            " FROM panestria.memory_classification WHERE source_id=%s AND owner_id=%s AND project_id=%s",
            (source_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        fields = list(SourceClassification.model_fields)
        try:
            result = SourceClassification.model_validate(dict(zip(fields, row, strict=True)))
        except (ValueError, ValidationError):
            raise KernelDenied("classification_corrupt") from None
        expected = resolve_classification(result.original_label)
        if (result.effective_label, result.interpretation) != (expected.effective, expected.interpretation):
            raise KernelDenied("classification_corrupt")
        return result
