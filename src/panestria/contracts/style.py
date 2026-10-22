"""Approved presentation preferences, separate from charter, facts and policy."""

import json
import unicodedata
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictInt, model_validator


class StyleExample(BaseModel):
    """Owner statement, identified only within its encrypted profile revision."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)
    reference: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,47}$", repr=False)
    input: SecretStr = Field(repr=False)
    response: SecretStr = Field(repr=False)

    @model_validator(mode="after")
    def bounded(self) -> Self:
        for value, limit in ((self.input, 256), (self.response, 384)):
            text = value.get_secret_value()
            if (
                not text.strip()
                or len(text.encode()) > limit
                or any(c != "\n" and (not c.isprintable() or unicodedata.category(c) == "Cf") for c in text)
            ):
                raise ValueError("style_example_size_invalid")
        return self

    def private_data(self) -> dict[str, str]:
        # Explicit only at encrypted storage / authorized ephemeral compilation.
        return {
            "reference": self.reference,
            "input": self.input.get_secret_value(),
            "response": self.response.get_secret_value(),
        }


class StyleExamples(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)
    examples: tuple[StyleExample, ...] = Field(default=(), max_length=2, repr=False, exclude_if=lambda v: not v)

    @model_validator(mode="after")
    def distinct(self) -> Self:
        if len({v.reference for v in self.examples}) != len(self.examples):
            raise ValueError("style_example_reference_duplicate")
        return self


class StyleProfile(StyleExamples):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)
    schema_version: StrictInt = Field(default=1, ge=1, le=1)
    language: str = Field(default="en", pattern=r"^[a-z]{2,3}(?:-[A-Z]{2})?$", repr=False)
    audience: Literal["general", "beginner", "technical"] = Field(default="general", repr=False)
    detail: Literal["concise", "balanced", "detailed"] = Field(default="balanced", repr=False)
    formatting: Literal["auto", "paragraphs", "bullets"] = Field(default="auto", repr=False)
    tables: Literal["when-useful", "avoid"] = Field(default="when-useful", repr=False)

    def private_json(self) -> str:
        """Unmasked content for the encrypted communication field, never a public export."""
        if not self.examples:
            return self.model_dump_json()  # Preserve every legacy byte.
        return json.dumps(
            {
                **self.model_dump(mode="json", exclude={"examples"}),
                "examples": [v.private_data() for v in self.examples],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )


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
