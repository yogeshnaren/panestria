"""Small untrusted local-model response; the controller supplies UUIDs and bindings."""

from pydantic import Field, StrictInt

from panestria.contracts.plan import PlanContract, PlanNode, Ref


class DraftNode(PlanNode):
    task_id: Ref
    depends_on: tuple[Ref, ...] = Field(default=(), max_length=15)
    expected_artifacts: tuple[Ref, ...] = ("patch",)
    attempts: StrictInt = Field(default=1, ge=1, le=5)
    wall_seconds_per_attempt: StrictInt = Field(default=90, ge=1, le=3600)
    api_microusd_per_attempt: StrictInt = Field(default=0, ge=0, le=0)


class ModelPlanDraft(PlanContract):
    edits: tuple[DraftNode, ...] = Field(min_length=1, max_length=15)
