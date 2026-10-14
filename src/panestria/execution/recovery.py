"""Resume a launched process and report the workflow's durable status."""

from __future__ import annotations

import json
import time
from uuid import uuid4

import sqlalchemy as sa
from dbos import DBOS

from panestria.execution.dbos_runtime import sqlalchemy_url

_RECOVERY_INSTANCE = str(uuid4())


def recovery_instance() -> str:
    """One identity for this process. It does not change between recoveries."""
    return _RECOVERY_INSTANCE


_TERMINAL = frozenset({"SUCCESS", "ERROR", "MAX_RECOVERY_ATTEMPTS_EXCEEDED", "CANCELLED"})


class RecoveryReport:
    def __init__(
        self,
        workflow_id: str,
        status: str,
        error: str,
        recovery_instance_id: str,
        recovery_attempts: int | None,
        latency_ms: int,
        goal_id: str = "",
        task_id: str = "",
    ) -> None:
        self.workflow_id = workflow_id
        self.status = status
        self.error = error
        self.recovery_instance = recovery_instance_id
        self.recovery_attempts = recovery_attempts
        self.latency_ms = latency_ms
        self.goal_id = goal_id
        self.task_id = task_id


def format_recovery_audit(report: RecoveryReport) -> str:
    """One line for the recover command. It names the goal, task, workflow, and the wait."""
    return json.dumps(
        {
            "goal_id": report.goal_id,
            "latency_ms": report.latency_ms,
            "recovery_attempts": report.recovery_attempts,
            "recovery_instance": report.recovery_instance,
            "status": report.status,
            "task_id": report.task_id,
            "workflow_id": report.workflow_id,
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def workflow_scope(database_url: str, workflow_id: str) -> tuple[str, str]:
    """Return the goal and task linked to a workflow. Missing links are empty."""
    engine = sa.create_engine(sqlalchemy_url(database_url), connect_args={"connect_timeout": 2})
    try:
        with engine.connect() as connection:
            row = connection.execute(
                sa.text(
                    "SELECT goal.id::text, task.id::text"
                    " FROM panestria.workflow_link AS link"
                    " JOIN panestria.task AS task ON task.id = link.task_id"
                    " JOIN panestria.goal AS goal ON goal.id = task.goal_id"
                    " WHERE link.dbos_workflow_id = :workflow"
                ),
                {"workflow": workflow_id},
            ).fetchone()
    finally:
        engine.dispose()
    if row is None or row[0] is None or row[1] is None:
        return "", ""
    return str(row[0]), str(row[1])


def unfinished_audits(database_url: str) -> tuple[str, ...]:
    """List PENDING and ENQUEUED workflows with their goal and task. No database URL."""
    engine = sa.create_engine(sqlalchemy_url(database_url), connect_args={"connect_timeout": 2})
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                sa.text(
                    "SELECT workflow.workflow_uuid, workflow.status, workflow.recovery_attempts,"
                    " goal.id::text, task.id::text"
                    " FROM dbos.workflow_status AS workflow"
                    " LEFT JOIN panestria.workflow_link AS link"
                    " ON link.dbos_workflow_id = workflow.workflow_uuid"
                    " LEFT JOIN panestria.task AS task ON task.id = link.task_id"
                    " LEFT JOIN panestria.goal AS goal ON goal.id = task.goal_id"
                    " WHERE workflow.status IN ('PENDING', 'ENQUEUED')"
                    " ORDER BY workflow.workflow_uuid"
                )
            ).fetchall()
    finally:
        engine.dispose()
    lines: list[str] = []
    for workflow_id, status, attempts, goal_id, task_id in rows:
        lines.append(
            json.dumps(
                {
                    "goal_id": "" if goal_id is None else str(goal_id),
                    "recovery_attempts": None if attempts is None else int(attempts),
                    "status": str(status),
                    "task_id": "" if task_id is None else str(task_id),
                    "workflow_id": str(workflow_id),
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )
    return tuple(lines)


class RecoveryService:
    def recover_pending(self, workflow_id: str, timeout_seconds: float = 20) -> RecoveryReport:
        """Poll after launch. Launch itself resumes an unfinished workflow."""
        started = time.monotonic()
        deadline = started + timeout_seconds
        attempts: int | None = None
        while time.monotonic() < deadline:
            status = DBOS.get_workflow_status(workflow_id)
            if status is not None and status.recovery_attempts is not None:
                attempts = int(status.recovery_attempts)
            if status is not None and status.status in _TERMINAL:
                observed = status.error
                return RecoveryReport(
                    workflow_id,
                    str(status.status),
                    "" if observed is None else str(observed),
                    recovery_instance(),
                    attempts,
                    _elapsed_ms(started),
                )
            time.sleep(0.2)
        return RecoveryReport(workflow_id, "PENDING", "", recovery_instance(), attempts, _elapsed_ms(started))


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.monotonic() - started) * 1000))


def connect_for_admission(database_url: str) -> None:
    """Open the database before any admission write. A refusal leaves no task state."""
    engine = sa.create_engine(sqlalchemy_url(database_url), connect_args={"connect_timeout": 2})
    try:
        with engine.connect() as connection:
            connection.execute(sa.text("SELECT 1"))
    finally:
        engine.dispose()
