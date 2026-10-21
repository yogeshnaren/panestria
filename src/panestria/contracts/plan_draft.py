"""Small untrusted local-model response; the controller supplies UUIDs and bindings."""

from pydantic import Field, StrictInt

from panestria.contracts.plan import PlanContract, PlanId, PlanNode, PlanSha, Ref


class DraftNode(PlanNode):
    task_id: Ref
    depends_on: tuple[Ref, ...] = Field(default=(), max_length=15)
    expected_artifacts: tuple[Ref, ...] = ("patch",)
    attempts: StrictInt = Field(default=1, ge=1, le=5)
    wall_seconds_per_attempt: StrictInt = Field(default=90, ge=1, le=3600)
    api_microusd_per_attempt: StrictInt = Field(default=0, ge=0, le=0)


class ModelPlanDraft(PlanContract):
    edits: tuple[DraftNode, ...] = Field(min_length=1, max_length=15)


class RepairDraftContext(PlanContract):
    """Controller-observed stopped work; model advice grants no revision authority."""

    parent_plan_id: PlanId
    parent_proposal_sha256: PlanSha
    return_proof_sha256: PlanSha
    parent_version: StrictInt = Field(ge=1, le=3)
    maximum_versions: StrictInt = Field(ge=2, le=3)
    remaining_wall_seconds: StrictInt = Field(ge=2)
    as_of_event_seq: StrictInt = Field(ge=0)
    failure_states: tuple[tuple[str, str, tuple[tuple[str, str], ...], str | None], ...] = Field(max_length=16)
