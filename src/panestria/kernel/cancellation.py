"""Cancel a scoped goal without starting an external effect."""

from __future__ import annotations

from panestria.contracts.task import ALLOWED_TRANSITIONS
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.repositories.tasks import append_event
from panestria.kernel.tasks import TaskService
from panestria.kernel.transition import require_correlation
from panestria.kernel.uow import UnitOfWork

_OUTSTANDING = frozenset({"PREPARED", "EXECUTING", "UNKNOWN", "RECONCILING"})
_TERMINAL = frozenset({"COMPLETED", "FAILED", "REJECTED"})


class CancelReceipt:
    def __init__(self, goal_id: str, goal_status: str, task_state: str | None, task_version: int) -> None:
        self.goal_id = goal_id
        self.goal_status = goal_status
        self.task_state = task_state
        self.task_version = task_version


class CancellationService:
    def __init__(self) -> None:
        self.tasks = TaskService()

    def cancel(
        self,
        uow: UnitOfWork,
        actor: Actor,
        goal_id: str,
        expected_version: int,
        reason: str,
        *,
        correlation_id: str,
    ) -> CancelReceipt:
        correlation = require_correlation(correlation_id)
        if not isinstance(reason, str) or reason.strip() == "" or len(reason) > 200:
            raise KernelDenied("invalid_contract")
        # Serialize status changes while allowing a worker holding the task row
        # to insert its final goal-referencing event (FK key-share lock).
        goal = uow.execute(
            "SELECT status FROM panestria.goal"
            " WHERE id = %s AND owner_id = %s AND project_id = %s FOR NO KEY UPDATE",
            (goal_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if goal is None:
            raise KernelDenied("not_found")
        if str(goal[0]) == "CANCELLED":
            return CancelReceipt(goal_id, "CANCELLED", "CANCELLED", expected_version)
        if str(goal[0]) in _TERMINAL:
            raise KernelDenied("illegal_transition")
        tasks = uow.execute(
            "SELECT id::text, state, row_version, lease_epoch FROM panestria.task"
            " WHERE goal_id = %s ORDER BY id FOR UPDATE",
            (goal_id,),
        ).fetchall()
        if not tasks:
            if expected_version != 0:
                raise KernelDenied("version_conflict")
            self._finish_goal(uow, actor, goal_id)
            return CancelReceipt(goal_id, "CANCELLED", None, 0)
        task_id, state, row_version, epoch = tasks[0]
        state = str(state)
        row_version = int(row_version)
        epoch = int(epoch)
        if state in _TERMINAL:
            raise KernelDenied("illegal_transition")
        if state != "CANCELLING":
            if row_version != expected_version:
                raise KernelDenied("version_conflict")
            if (state, "CANCELLING") not in ALLOWED_TRANSITIONS:
                raise KernelDenied("illegal_transition")
            policy = self._policy(uow, str(task_id))
            moved = self.tasks.transition(
                uow,
                actor,
                str(task_id),
                row_version,
                epoch,
                "CANCELLING",
                "owner-cancel",
                policy_version=policy,
                correlation_id=correlation,
            )
            row_version = moved.row_version
            state = "CANCELLING"
        elif row_version != expected_version:
            raise KernelDenied("version_conflict")
        outstanding = uow.execute(
            "SELECT state FROM panestria.side_effect WHERE task_id = %s",
            (task_id,),
        ).fetchall()
        if any(str(item[0]) in _OUTSTANDING for item in outstanding):
            return CancelReceipt(goal_id, "CREATED", "CANCELLING", row_version)
        policy = self._policy(uow, str(task_id))
        finished = self.tasks.transition(
            uow,
            actor,
            str(task_id),
            row_version,
            epoch,
            "CANCELLED",
            "owner-cancel",
            policy_version=policy,
            correlation_id=correlation,
        )
        self._finish_goal(uow, actor, goal_id)
        return CancelReceipt(goal_id, "CANCELLED", "CANCELLED", finished.row_version)

    def _policy(self, uow: UnitOfWork, task_id: str) -> str:
        row = uow.execute(
            "SELECT contract.body->>'autonomy_profile_ref'"
            " FROM panestria.task AS task"
            " JOIN panestria.goal_contract AS contract ON contract.id = task.contract_id"
            " WHERE task.id = %s",
            (task_id,),
        ).fetchone()
        if row is None or not isinstance(row[0], str):
            raise KernelDenied("invalid_policy")
        return row[0]

    def _finish_goal(self, uow: UnitOfWork, actor: Actor, goal_id: str) -> None:
        uow.execute(
            "UPDATE panestria.goal SET status = 'CANCELLED', updated_at = now() WHERE id = %s",
            (goal_id,),
        )
        append_event(
            uow,
            goal_id=goal_id,
            task_id=None,
            kind="goal.cancelled",
            actor=actor.owner_id,
            payload={"cause": "owner-cancel"},
        )
