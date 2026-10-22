"""Bounded local layout only. Semantic rewrites are never attempted."""

import re
import time
from dataclasses import dataclass, field
from typing import Literal

from panestria.contracts.style import PresentationObservation, StyleProfile

_UNSAFE = re.compile(
    r"[`<>|]|!\[|^[ \t]*(?:[#>*+-]|\d+[.)])(?:\s|$)|^\s*\[[^\]]+\]:|^(?: {4}|\t)"
    r"|[\x00-\x08\x0b-\x1f\x7f\u202a-\u202e\u2066-\u2069]",
    re.MULTILINE,
)


@dataclass(frozen=True)
class Presentation:
    text: str = field(repr=False)
    observation: PresentationObservation


def present(text: str, style: StyleProfile, *, complete: bool = True) -> Presentation:
    began = time.perf_counter()
    result = text
    state: Literal["APPLIED", "UNCHANGED", "ABSTAIN"] = "ABSTAIN"
    paragraphs = re.split(r"(\n[ \t]*\n)", text) if len(text) <= 65536 else [text]
    count = sum(bool(part.strip()) for part in paragraphs[::2])
    leading_space = any(part.strip() and part[0].isspace() for part in paragraphs[::2])
    if (
        complete is True
        and text
        and len(text.encode()) <= 65536
        and count <= 16
        and not leading_space
        and not _UNSAFE.search(text)
    ):
        if style.formatting == "paragraphs":
            state = "UNCHANGED"  # Already plain paragraphs; preserve every byte.
        elif style.formatting == "bullets":
            candidate = "".join(
                "- " + part if i % 2 == 0 and part.strip() else part for i, part in enumerate(paragraphs)
            )
            # Independent inverse: source list/structural prefixes were refused.
            # No fact, citation, uncertainty, punctuation or whitespace may change.
            if re.sub(r"(?m)^- ", "", candidate) == text:
                result, state = candidate, "APPLIED"
    words = len(text.split())
    return Presentation(
        result,
        PresentationObservation(
            state=state,
            elapsed_seconds=time.perf_counter() - began,
            input_bytes=len(text.encode()),
            output_bytes=len(result.encode()),
            words=words,
            paragraphs=count,
            words_per_paragraph=words / count if count else None,
        ),
    )
