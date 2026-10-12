"""Path patterns shared by contract scope and per-check diffs."""

from __future__ import annotations


def matches(pattern: str, relative: str) -> bool:
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return relative == prefix or relative.startswith(prefix + "/")
    if pattern.endswith("*"):
        return relative.startswith(pattern[:-1])
    return relative == pattern


def matches_any(patterns: frozenset[str] | tuple[str, ...] | list[str], relative: str) -> bool:
    return any(matches(pattern, relative) for pattern in patterns)


def path_permitted(
    relative: str,
    allowed: frozenset[str] | tuple[str, ...] | list[str],
    forbidden: frozenset[str] | tuple[str, ...] | list[str],
    *,
    also_allowed: frozenset[str] | tuple[str, ...] | list[str] | None = None,
) -> bool:
    if matches_any(forbidden, relative):
        return False
    if not matches_any(allowed, relative):
        return False
    if also_allowed is not None and not matches_any(also_allowed, relative):
        return False
    return True
