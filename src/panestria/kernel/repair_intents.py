"""Goal-scoped bounded repair intent/receipt projection over canonical immutable events."""

import json
from dataclasses import dataclass

from panestria.contracts.repair_intent import FINISHED, STARTED, RepairIntent, RepairOutcome
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.plan_store import PlanStore
from panestria.kernel.repositories.tasks import append_event
from panestria.kernel.uow import UnitOfWork


@dataclass(frozen=True)
class RepairLedger:
    intents: tuple[RepairIntent, ...]
    outcomes: tuple[RepairOutcome, ...]

    @property
    def charged_wall_seconds(self) -> int:
        return sum(i.reserved_wall_seconds for i in self.intents)

    @property
    def unresolved(self) -> int:
        return sum(
            not any(o.draft_id == i.draft_id and o.status != "UNCONFIRMED" for o in self.outcomes) for i in self.intents
        )

    def outcome(self, intent: RepairIntent) -> RepairOutcome | None:
        return next((o for o in self.outcomes if o.draft_id == intent.draft_id), None)


def repair_ledger(uow: UnitOfWork, actor: Actor, goal: str) -> RepairLedger:
    if not uow.execute(
        "SELECT 1 FROM panestria.goal WHERE id=%s AND owner_id=%s AND project_id=%s",
        (goal, actor.owner_id, actor.project_id),
    ).fetchone():
        raise KernelDenied("not_found")
    rows = uow.execute(
        "SELECT kind,payload FROM panestria.task_event WHERE goal_id=%s AND kind IN (%s,%s) ORDER BY seq LIMIT 5",
        (goal, STARTED, FINISHED),
    ).fetchall()
    if len(rows) > 4:
        raise KernelDenied("repair_intent_audit_unconfirmed")
    try:
        intents = tuple(RepairIntent.model_validate_json(json.dumps(p)) for kind, p in rows if kind == STARTED)
        outcomes = tuple(RepairOutcome.model_validate_json(json.dumps(p)) for kind, p in rows if kind == FINISHED)
        if (
            [i.turn for i in intents] != list(range(1, len(intents) + 1))
            or len({i.draft_id for i in intents}) != len(intents)
            or len({i.key_sha256 for i in intents}) != len(intents)
            or any(i.maximum_turns != intents[0].maximum_turns or i.turn > i.maximum_turns for i in intents)
            or len({o.draft_id for o in outcomes}) != len(outcomes)
            or any(
                not any(o.draft_id == i.draft_id and o.intent_sha256 == i.sha256() for i in intents) for o in outcomes
            )
            or any(
                o.status == "RETAINED"
                and (o.physical_return != "CONFIRMED" or not o.receipt_sha256 or o.reason != "ok")
                for o in outcomes
            )
            or any(o.status == "NOT_PUBLISHED" and o.physical_return != "CONFIRMED" for o in outcomes)
        ):
            raise ValueError
    except ValueError:
        raise KernelDenied("repair_intent_audit_unconfirmed") from None
    return RepairLedger(intents, outcomes)


def begin_repair(uow: UnitOfWork, actor: Actor, goal: str, intent: RepairIntent) -> None:
    intent = RepairIntent.model_validate(intent)
    store = PlanStore()
    parent = store.get(uow, actor, intent.parent_plan_id)
    state, _, contract = store._goal(uow, actor, goal, read_only=True)
    family = uow.execute(
        "SELECT id::text FROM panestria.build_plan WHERE goal_id=%s ORDER BY version", (goal,)
    ).fetchall()
    if (
        state not in {"CREATED", "ACTIVE"}
        or parent.state != "ACCEPTED"
        or not family
        or family[-1] != (intent.parent_plan_id,)
    ):
        raise KernelDenied("local_repair_parent_not_current_stopped_plan")
    if (
        parent.proposal.goal_id != goal
        or parent.proposal.sha256() != intent.parent_sha256
        or parent.proposal.contract_sha256 != intent.contract_sha256
    ):
        raise KernelDenied("repair_intent_scope_unconfirmed")
    current = repair_ledger(uow, actor, goal)
    if current.unresolved:
        raise KernelDenied("repair_draft_prior_unconfirmed")
    if current.intents and intent.maximum_turns != current.intents[0].maximum_turns:
        raise KernelDenied("repair_turn_limit_change_requires_authorization")
    if len(current.intents) >= intent.maximum_turns or intent.turn != len(current.intents) + 1:
        raise KernelDenied("repair_model_turn_limit_exhausted")
    charged = sum(store.get(uow, actor, row[0]).validation.upper_wall_seconds for row in family)
    if charged + current.charged_wall_seconds + intent.reserved_wall_seconds + 2 > contract.budget.max_wall_seconds:
        raise KernelDenied("plan_repair_budget_exhausted")
    append_event(
        uow, goal_id=goal, task_id=None, actor=actor.owner_id, kind=STARTED, payload=intent.model_dump(mode="json")
    )


def finish_repair(uow: UnitOfWork, actor: Actor, goal: str, outcome: RepairOutcome) -> None:
    outcome = RepairOutcome.model_validate(outcome)
    current = repair_ledger(uow, actor, goal)
    intent = next((i for i in current.intents if i.draft_id == outcome.draft_id), None)
    if intent is None or outcome.intent_sha256 != intent.sha256() or current.outcome(intent) is not None:
        raise KernelDenied("repair_outcome_not_confirmed")
    append_event(
        uow, goal_id=goal, task_id=None, actor=actor.owner_id, kind=FINISHED, payload=outcome.model_dump(mode="json")
    )
