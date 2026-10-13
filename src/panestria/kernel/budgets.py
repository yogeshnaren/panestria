"""Goal-wide integer cash caps. Unknown prices/quota are not zero."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.repositories.tasks import append_event, lock_task
from panestria.kernel.uow import UnitOfWork


@dataclass(frozen=True)
class Reservation:
    reservation_id: str
    amount_microusd: int
    state: str
    replayed: bool = False


def _money(amount: int) -> None:
    if type(amount) is not int or not 0 <= amount <= 10**12:
        raise KernelDenied("invalid_money")


class BudgetService:
    def _task(self, uow: UnitOfWork, actor: Actor, task_id: str) -> str:
        task = lock_task(uow, actor.owner_id, actor.project_id, task_id)
        if task is None:
            raise KernelDenied("not_found")
        return task[0]

    def configure(
        self, uow: UnitOfWork, actor: Actor, task_id: str, cap_microusd: int | None, *, expected_version: int = 0
    ) -> None:
        goal_id = self._task(uow, actor, task_id)
        if cap_microusd is not None:
            _money(cap_microusd)
            body = uow.execute(
                "SELECT c.body FROM panestria.task t JOIN panestria.goal_contract c ON c.id=t.contract_id"
                " WHERE t.id=%s",
                (task_id,),
            ).fetchone()
            try:
                maximum = Decimal(body[0]["budget"]["max_api_usd"]) * 1_000_000 if body else None
            except (KeyError, TypeError, InvalidOperation):
                maximum = None
            if maximum is None or not maximum.is_finite() or cap_microusd > maximum:
                raise KernelDenied("budget_not_authorized")
        uow.execute(
            "INSERT INTO panestria.goal_budget(goal_id,cash_cap_microusd) VALUES (%s,NULL) ON CONFLICT DO NOTHING",
            (goal_id,),
        )
        row = uow.execute(
            "SELECT settled_microusd,row_version FROM panestria.goal_budget WHERE goal_id=%s FOR UPDATE", (goal_id,)
        ).fetchone()
        assert row is not None
        if row[1] != expected_version:
            raise KernelDenied("version_conflict")
        if cap_microusd is not None and row[0] + self._exposure(uow, goal_id) > cap_microusd:
            raise KernelDenied("cap_below_exposure")
        uow.execute(
            "UPDATE panestria.goal_budget SET cash_cap_microusd=%s,row_version=row_version+1 WHERE goal_id=%s",
            (cap_microusd, goal_id),
        )
        append_event(
            uow,
            goal_id=goal_id,
            task_id=task_id,
            kind="budget.configured",
            actor=actor.owner_id,
            payload={"cash_cap_microusd": cap_microusd},
        )

    def _exposure(self, uow: UnitOfWork, goal_id: str) -> int:
        row = uow.execute(
            "SELECT COALESCE(sum(amount_microusd),0) FROM panestria.budget_reservation"
            " WHERE goal_id=%s AND state IN ('RESERVED','UNKNOWN')",
            (goal_id,),
        ).fetchone()
        assert row is not None
        return int(row[0])

    def reserve(
        self, uow: UnitOfWork, actor: Actor, task_id: str, request_key: str, amount_microusd: int | None
    ) -> Reservation:
        goal_id = self._task(uow, actor, task_id)
        if amount_microusd is None:
            raise KernelDenied("cost_unknown_approval_required")
        _money(amount_microusd)
        if not request_key or len(request_key) > 128:
            raise KernelDenied("invalid_reservation")
        budget = uow.execute(
            "SELECT cash_cap_microusd,settled_microusd FROM panestria.goal_budget WHERE goal_id=%s FOR UPDATE",
            (goal_id,),
        ).fetchone()
        if budget is None or budget[0] is None:
            raise KernelDenied("cash_cap_unknown")
        previous = uow.execute(
            "SELECT id::text,task_id::text,amount_microusd,state FROM panestria.budget_reservation"
            " WHERE goal_id=%s AND request_key=%s",
            (goal_id, request_key),
        ).fetchone()
        if previous is not None:
            if previous[1] != task_id or previous[2] != amount_microusd:
                raise KernelDenied("idempotency_conflict")
            return Reservation(str(previous[0]), amount_microusd, str(previous[3]), True)
        if budget[1] + self._exposure(uow, goal_id) + amount_microusd > budget[0]:
            raise KernelDenied("cash_cap_exceeded")
        reservation_id = str(uuid4())
        uow.execute(
            "INSERT INTO panestria.budget_reservation"
            " (id,goal_id,task_id,request_key,amount_microusd,state) VALUES (%s,%s,%s,%s,%s,'RESERVED')",
            (reservation_id, goal_id, task_id, request_key, amount_microusd),
        )
        append_event(
            uow,
            goal_id=goal_id,
            task_id=task_id,
            kind="budget.reserved",
            actor=actor.owner_id,
            payload={"reservation_id": reservation_id, "amount_microusd": amount_microusd},
        )
        return Reservation(reservation_id, amount_microusd, "RESERVED")

    def settle(
        self,
        uow: UnitOfWork,
        actor: Actor,
        reservation_id: str,
        actual_microusd: int | None,
        *,
        confirmed_no_effect: bool = False,
    ) -> None:
        hint = uow.execute(
            "SELECT task_id::text FROM panestria.budget_reservation WHERE id=%s", (reservation_id,)
        ).fetchone()
        if hint is None:
            raise KernelDenied("not_found")
        task_id = str(hint[0])
        goal_id = self._task(uow, actor, task_id)
        uow.execute("SELECT goal_id FROM panestria.goal_budget WHERE goal_id=%s FOR UPDATE", (goal_id,))
        row = uow.execute(
            "SELECT amount_microusd,actual_microusd,state FROM panestria.budget_reservation WHERE id=%s FOR UPDATE",
            (reservation_id,),
        ).fetchone()
        assert row is not None
        if row[2] in {"SETTLED", "RELEASED"}:
            if (confirmed_no_effect and row[2] == "RELEASED") or (row[2] == "SETTLED" and row[1] == actual_microusd):
                return
            raise KernelDenied("settlement_conflict")
        if confirmed_no_effect:
            if actual_microusd is not None:
                raise KernelDenied("invalid_settlement")
            state, actual = "RELEASED", None
        elif actual_microusd is None:
            state, actual = "UNKNOWN", None
        else:
            _money(actual_microusd)
            if actual_microusd > row[0]:
                raise KernelDenied("reservation_exceeded")
            state, actual = "SETTLED", actual_microusd
            uow.execute(
                "UPDATE panestria.goal_budget SET settled_microusd=settled_microusd+%s WHERE goal_id=%s",
                (actual, goal_id),
            )
        uow.execute(
            "UPDATE panestria.budget_reservation SET state=%s,actual_microusd=%s WHERE id=%s",
            (state, actual, reservation_id),
        )
        append_event(
            uow,
            goal_id=goal_id,
            task_id=task_id,
            kind="budget.settled",
            actor=actor.owner_id,
            payload={"reservation_id": reservation_id, "state": state, "actual_microusd": actual},
        )
