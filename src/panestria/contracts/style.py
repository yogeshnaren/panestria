"""Approved presentation preferences, separate from charter, facts and policy."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class StyleProfile(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)
    schema_version: StrictInt = Field(default=1, ge=1, le=1)
    language: str = Field(default="en", pattern=r"^[a-z]{2,3}(?:-[A-Z]{2})?$", repr=False)
    audience: Literal["general", "beginner", "technical"] = Field(default="general", repr=False)
    detail: Literal["concise", "balanced", "detailed"] = Field(default="balanced", repr=False)
    formatting: Literal["auto", "paragraphs", "bullets"] = Field(default="auto", repr=False)
    tables: Literal["when-useful", "avoid"] = Field(default="when-useful", repr=False)


class PresentationObservation(BaseModel):
    """Descriptive measurements only; no profile value, text or content hash."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    renderer: Literal["lossless-layout-v1"] = "lossless-layout-v1"
    state: Literal["APPLIED", "UNCHANGED", "ABSTAIN"]
    elapsed_seconds: float = Field(ge=0, allow_inf_nan=False)
    input_bytes: StrictInt = Field(ge=0)
    output_bytes: StrictInt = Field(ge=0)
    words: StrictInt = Field(ge=0)
    paragraphs: StrictInt = Field(ge=0)
    words_per_paragraph: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    content_retention: Literal["EXACT_ORIGINAL_EXCLUDING_ADDED_LAYOUT_MARKERS"] = (
        "EXACT_ORIGINAL_EXCLUDING_ADDED_LAYOUT_MARKERS"
    )
    factual_support: Literal["NOT_ASSESSED"] = "NOT_ASSESSED"
    readability_quality: Literal["NOT_ASSESSED"] = "NOT_ASSESSED"
    owner_preference: Literal["NOT_ASSESSED"] = "NOT_ASSESSED"
