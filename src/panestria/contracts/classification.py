"""Canonical goal classes and conservative interpretation of legacy inputs.

This pure compatibility boundary never reclassifies or rewrites stored records.
Audited owner resolution and versioned storage/API migration are separate work.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

CanonicalClass = Literal["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"]
_RANK: dict[CanonicalClass, int] = {"PUBLIC": 0, "INTERNAL": 1, "CONFIDENTIAL": 2, "RESTRICTED": 3}


@dataclass(frozen=True)
class Classification:
    effective: CanonicalClass | None
    interpretation: Literal["CANONICAL", "LEGACY_RESTRICTED", "UNKNOWN"]


def resolve_classification(label: object) -> Classification:
    """Unknown denies; unresolved PRIVATE is effectively restricted, never internal."""
    if not isinstance(label, str):
        return Classification(None, "UNKNOWN")
    if label == "PRIVATE":
        return Classification("RESTRICTED", "LEGACY_RESTRICTED")
    if label in _RANK:
        return Classification(label, "CANONICAL")
    return Classification(None, "UNKNOWN")


def classification_rank(label: object) -> int:
    """Compare effective classes; uncertainty is not an authorized downgrade."""
    resolved = resolve_classification(label)
    if resolved.effective is None:
        raise ValueError("classification_unknown")
    return _RANK[resolved.effective]


def derive_classification(source_labels: Iterable[object]) -> Classification:
    """Strictest source wins; missing/unknown lineage can never authorize a class."""
    labels = [resolve_classification(label) for label in source_labels]
    if not labels or any(label.effective is None for label in labels):
        return Classification(None, "UNKNOWN")
    effective = max((label.effective for label in labels if label.effective is not None), key=_RANK.__getitem__)
    interpretation: Literal["CANONICAL", "LEGACY_RESTRICTED", "UNKNOWN"] = (
        "LEGACY_RESTRICTED" if any(label.interpretation == "LEGACY_RESTRICTED" for label in labels) else "CANONICAL"
    )
    return Classification(effective, interpretation)
