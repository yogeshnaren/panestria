"""Bounded owner statements; values stay masked outside explicit encryption."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

ProfileField = Literal["preferred_name", "communication", "goals", "background", "constraints", "sensitive_notes"]


class ProfileDocument(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    fields: dict[ProfileField, SecretStr] = Field(min_length=1, max_length=6, repr=False)
    approved_for_local_context: tuple[ProfileField, ...] = Field(default=(), max_length=6)
    valid_until: AwareDatetime | None = None

    @field_validator("schema_version", mode="before")
    @classmethod
    def explicit_version(cls, value: object) -> object:
        if type(value) is not int or value != 1:
            raise ValueError("invalid_profile_schema_version")
        return value

    @model_validator(mode="after")
    def bounded_statements(self) -> Self:
        values = [value.get_secret_value() for value in self.fields.values()]
        if any(not value or len(value.encode()) > 8192 for value in values):
            raise ValueError("profile_field_size_invalid")
        if sum(len(value.encode()) for value in values) > 16384:
            raise ValueError("profile_size_invalid")
        approved = self.approved_for_local_context
        if len(set(approved)) != len(approved) or not set(approved).issubset(self.fields):
            raise ValueError("profile_field_approval_invalid")
        return self
