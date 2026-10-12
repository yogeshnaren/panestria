"""DAG admission and scoped task transitions. The caller commits."""

from __future__ import annotations

from panestria.contracts.task import ALLOWED_TRANSITIONS
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.repositories.tasks import append_event, lock_task
from panestria.kernel.uow import UnitOfWork


class DagRejected(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class TransitionReceipt:
    def __init__(self, task_id: str, state: str, row_version: int, event_seq: str) -> None:
        self.task_id = task_id
        self.state = state
        self.row_version = row_version
        self.event_seq = event_seq


def validate_dag(nodes: list[str], edges: list[tuple[str, str]]) -> None:
    """Reject self-links, missing endpoints, and cycles. Edges point at dependencies."""
    if len(nodes) != len(set(nodes)):
        raise DagRejected("duplicate_node")
    known = set(nodes)
    outgoing: dict[str, list[str]] = {node: [] for node in nodes}
    for source, target in edges:
        if source == target:
            raise DagRejected("self_link")
        if source not in known or target not in known:
            raise DagRejected("unknown_node")
        outgoing[source].append(target)
    color: dict[str, int] = {}

    def visit(node: str) -> None:
        color[node] = 1
        for nxt in outgoing[node]:
            state = color.get(nxt, 0)
            if state == 1:
                raise DagRejected("cycle")
            if state == 0:
                visit(nxt)
        color[node] = 2

    for node in nodes:
        if color.get(node, 0) == 0:
            visit(node)


class TaskService:
    def set_dependencies(
        self,
        uow: UnitOfWork,
        actor: Actor,
        edges: list[tuple[str, str]],
    ) -> None:
        """Validate the DAG, then persist edges. The event append is the last write."""
        endpoints = sorted({task_id for edge in edges for task_id in edge})
        goal_id: str | None = None
        for task_id in endpoints:
            current = lock_task(uow, actor.owner_id, actor.project_id, task_id)
            if current is None:
                raise KernelDenied("not_found")
            locked_goal, _state, _version, _epoch = current
            if goal_id is None:
                goal_id = locked_goal
            elif locked_goal != goal_id:
                raise KernelDenied("not_found")
        validate_dag(endpoints, edges)
        for task_id, depends_on in edges:
            uow.execute(
                "INSERT INTO panestria.task_dependency (task_id, depends_on) VALUES (%s, %s)",
                (task_id, depends_on),
            )
        if goal_id is None:
            return
        append_event(
            uow,
            goal_id=goal_id,
            task_id=None,
            kind="task.dependencies",
            actor=actor.owner_id,
            payload={"edges": [[source, target] for source, target in edges]},
        )

    def transition(
        self,
        uow: UnitOfWork,
        actor: Actor,
        task_id: str,
        expected_version: int,
        epoch: int,
        target: str,
        cause: str,
    ) -> TransitionReceipt:
        current = lock_task(uow, actor.owner_id, actor.project_id, task_id)
        if current is None:
            raise KernelDenied("not_found")
        goal_id, state, row_version, lease_epoch = current
        if row_version != expected_version or lease_epoch != epoch:
            raise KernelDenied("version_conflict")
        if (state, target) not in ALLOWED_TRANSITIONS:
            raise KernelDenied("illegal_transition")
        updated = uow.execute(
            "UPDATE panestria.task SET state = %s, row_version = row_version + 1,"
            " updated_at = now() WHERE id = %s AND row_version = %s"
            " RETURNING row_version",
            (target, task_id, expected_version),
        ).fetchone()
        if updated is None:
            raise KernelDenied("version_conflict")
        seq = append_event(
            uow,
            goal_id=goal_id,
            task_id=task_id,
            kind="task.transition",
            actor=actor.owner_id,
            payload={"from": state, "to": target, "cause": cause},
        )
        return TransitionReceipt(task_id, target, int(updated[0]), str(seq))
