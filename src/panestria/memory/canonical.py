"""Version-2 read projections keep canonical labels and original source lineage."""

from __future__ import annotations

from dataclasses import asdict
from typing import cast

from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.uow import UnitOfWork
from panestria.memory.classification import MemoryClassificationService
from panestria.memory.service import MemoryService


class CanonicalMemoryView:
    def __init__(self) -> None:
        self.memory = MemoryService()
        self.classification = MemoryClassificationService()

    def search(self, uow: UnitOfWork, actor: Actor, query: str, *, limit: int = 10) -> list[dict[str, object]]:
        result: list[dict[str, object]] = []
        for hit in self.memory.search(uow, actor, query, limit=limit):
            record = self.classification.get(uow, actor, hit.ref.source_id)
            if (record.source_sha256, record.original_label) != (hit.ref.sha256, hit.label):
                raise KernelDenied("classification_corrupt")
            result.append(
                {**asdict(hit), "label": record.effective_label, "classification": record.model_dump(mode="json")}
            )
        return result

    def history(self, uow: UnitOfWork, actor: Actor, item_id: str, *, after_revision: int = 0) -> dict[str, object]:
        history = self.memory.history(uow, actor, item_id, after_revision=after_revision)
        revisions = cast(list[dict[str, object]], history["revisions"])
        for revision in revisions:
            record = self.classification.get(uow, actor, str(revision["source_id"]))
            if (record.source_sha256, record.original_label) != (revision["sha256"], revision["label"]):
                raise KernelDenied("classification_corrupt")
            revision["label"] = record.effective_label
            revision["classification"] = record.model_dump(mode="json")
        return {**history, "schema_version": 2}
