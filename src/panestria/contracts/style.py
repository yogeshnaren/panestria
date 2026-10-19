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
