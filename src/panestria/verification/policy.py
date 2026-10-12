"""Synthetic profile decisions. A stored expectation is not itself a decision."""

from __future__ import annotations

_PROFILES: dict[str, dict[str, str]] = {
    "synthetic-approve-first-v1": {
        "contract_consent": "approval-required",
        "protected-merge": "approval-required",
        "scoped-file-edit": "approval-required",
    }
}


def decide_action(profile_ref: str, action: str) -> str | None:
    """Return the profile's decision for one action. Unknown pairs have no decision."""
    profile = _PROFILES.get(profile_ref)
    if profile is None:
        return None
    return profile.get(action)
