"""Task row lock and the global event append. Event allocation is the last write."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from panestria.kernel.repositories.events import EVENT_LOCK
from panestria.kernel.uow import UnitOfWork
from panestria.telemetry.tracing import current_trace_id

_EVENT_LOCK = EVENT_LOCK
TASKS_BY_GOAL_SQL = "SELECT id::text FROM panestria.task WHERE goal_id = %s ORDER BY id FOR UPDATE"


def lock_task(
    uow: UnitOfWork,
    owner_id: str,
    project_id: str,
    task_id: str,
) -> tuple[str, str, int, int] | None:
    row = uow.execute(
        "SELECT task.goal_id::text, task.state, task.row_version, task.lease_epoch"
        " FROM panestria.task AS task"
        " JOIN panestria.goal AS goal ON goal.id = task.goal_id"
        " WHERE task.id = %s AND goal.owner_id = %s AND goal.project_id = %s"
        " FOR UPDATE OF task",
        (task_id, owner_id, project_id),
    ).fetchone()
    if row is None:
        return None
    goal_id, state, row_version, lease_epoch = row
    return str(goal_id), str(state), int(row_version), int(lease_epoch)


def append_event(
    uow: UnitOfWork,
    *,
    goal_id: str,
    task_id: str | None,
    kind: str,
    actor: str,
    payload: dict[str, Any],
    trace_id: str | None = None,
) -> int:
    """Allocate the next global seq and insert one event. Callers must not write afterward."""
    trace_id = current_trace_id() or trace_id
    uow.execute("SELECT pg_advisory_xact_lock(%s, %s)", _EVENT_LOCK)
    event_id = str(uuid4())
    body = json.dumps(payload, sort_keys=True)
    if trace_id is None:
        uow.execute(
            "INSERT INTO panestria.task_event (id, goal_id, task_id, kind, actor, payload)"
            " VALUES (%s, %s, %s, %s, %s, %s::jsonb)",
            (event_id, goal_id, task_id, kind, actor, body),
        )
    else:
        uow.execute(
            "INSERT INTO panestria.task_event"
            " (id, goal_id, task_id, kind, actor, payload, trace_id)"
            " VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)",
            (event_id, goal_id, task_id, kind, actor, body, trace_id),
        )
    allocated = uow.execute(
        "SELECT seq FROM panestria.task_event WHERE id = %s",
        (event_id,),
    ).fetchone()
    if allocated is None:
        raise RuntimeError("event seq missing")
    return int(allocated[0])
