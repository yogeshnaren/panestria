"""PUBLIC plan intake; frozen proposals grant no acceptance or worker authority."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, JsonValue, field_validator

from panestria.contracts.plan import StoredPlan


class BuildPlanSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    # The existing canonical parsers validate these complete documents. Keeping
    # their JSON envelope avoids a second, subtly different GoalContract schema.
    contract_document: dict[str, object]
    proposal: dict[str, object]
    inventory: dict[str, object]
    public_plan: Literal[True]

    @field_validator("public_plan", mode="before")
    @classmethod
    def explicit_public_intent(cls, value: object) -> object:
        if value is not True:
            raise ValueError("explicit_public_plan_required")
        return value


class BuildPlanStagingView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    owner_id: str
    project_id: str
    goal_id: str
    goal_status: str
    contract_document: dict[str, JsonValue]
    plan: StoredPlan
    operation: Literal["STAGED_NO_EXECUTION"] = "STAGED_NO_EXECUTION"
    runtime_qualification: Literal["NOT_ASSESSED"] = "NOT_ASSESSED"
    execution_authority: Literal["NONE"] = "NONE"
