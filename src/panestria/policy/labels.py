"""Derived labels preserve the most restrictive source, including uncertainty."""

from __future__ import annotations

from collections.abc import Iterable

from panestria.contracts.classification import derive_classification
from panestria.contracts.policy import DataLabel


class LabelService:
    def derive(self, source_labels: Iterable[DataLabel | None]) -> DataLabel:
        return derive_classification(source_labels).effective or "UNKNOWN"
