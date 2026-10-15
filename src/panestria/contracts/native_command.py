"""Bounded metadata from the trusted registered-check controller, not task acceptance."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator


class RegisteredCheckReceipt(BaseModel):
    model_config = ConfigDict(
        strict=True, extra="forbid", frozen=True, hide_input_in_errors=True, revalidate_instances="always"
    )
    outcome: Literal["COMPLETED", "DENIED", "CANCELLED", "UNKNOWN"]
    exit_code: StrictInt | None = Field(default=None, ge=-255, le=255)
    report_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def report_binding(self) -> Self:
        if self.outcome == "COMPLETED":
            if self.exit_code is None or self.report_sha256 is None:
                raise ValueError("completed_check_requires_report")
        elif self.exit_code is not None or self.report_sha256 is not None:
            raise ValueError("unconfirmed_check_has_no_completion_metadata")
        return self
