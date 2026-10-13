"""Derived labels preserve the most restrictive source, including uncertainty."""

from __future__ import annotations

from collections.abc import Iterable

from panestria.contracts.policy import DataLabel

_RANK: dict[DataLabel, int] = {"PUBLIC": 0, "PRIVATE": 1, "RESTRICTED": 2, "UNKNOWN": 3}


class LabelService:
    def derive(self, source_labels: Iterable[DataLabel | None]) -> DataLabel:
        labels = list(source_labels)
        if not labels or any(item is None or item not in _RANK for item in labels):
            return "UNKNOWN"
        return max((item for item in labels if item is not None), key=_RANK.__getitem__)
