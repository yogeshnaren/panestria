"""Local-only PUBLIC question staging, no research execution or support authority."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, SecretStr, field_validator

from panestria.contracts.research import ResearchLimits


class ResearchIntakeSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    goal_id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
    template_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    question: SecretStr
    public_question: Literal[True]

    @field_validator("public_question", mode="before")
    @classmethod
    def explicit_public_intent(cls, value: object) -> object:
        if value is not True:
            raise ValueError("explicit_public_question_required")
        return value

    @field_validator("question")
    @classmethod
    def bounded_question(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip() or len(value.get_secret_value().encode()) > 4096:
            raise ValueError("public_question_size_invalid")
        return value


class ResearchIntakeView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    owner_id: str
    project_id: str
    template_sha256: str
    contract_template: dict[str, JsonValue]
    limits: ResearchLimits
    execution_authority: Literal["NONE"] = "NONE"


class ResearchStagingView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    owner_id: str
    project_id: str
    goal_id: str
    task_id: str
    request_id: str
    request_sha256: str
    question: str
    goal_status: str
    task_state: str
    limits: ResearchLimits
    operation: Literal["STAGED_NO_EXECUTION"] = "STAGED_NO_EXECUTION"
    semantic_support: Literal["NOT_ASSESSED"] = "NOT_ASSESSED"
    execution_authority: Literal["NONE"] = "NONE"
