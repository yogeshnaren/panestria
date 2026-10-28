"""Filesystem-independent comparison of private path components."""

from __future__ import annotations

import unicodedata


def folded_name(part: str) -> str:
    """Return the name a permissive filesystem would resolve ``part`` to.

    NFKC folds compatibility forms such as fullwidth letters, casefold covers
    case-insensitive filesystems, and trailing dots and spaces are dropped as
    Windows does. ``.ENV.``, ``.Git`` and a fullwidth spelling of ``secrets``
    therefore compare equal to ``.env``, ``.git`` and ``secrets``.
    """
    return unicodedata.normalize("NFKC", part).casefold().rstrip(". ")
