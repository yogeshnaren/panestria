"""Global event append on a caller-owned SQLAlchemy transaction."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa

EVENT_LOCK = (106971, 1)


def append_domain_event(
    connection: sa.Connection,
    *,
    goal_id: str,
    task_id: str | None,
    kind: str,
    actor: str,
    payload: dict[str, Any],
    trace_id: str | None = None,
) -> int:
    """Allocate the next global seq. Callers must not write afterward."""
    connection.execute(
        sa.text("SELECT pg_advisory_xact_lock(:classid, :objid)"),
        {"classid": EVENT_LOCK[0], "objid": EVENT_LOCK[1]},
    )
    event_id = str(uuid4())
    statement = (
        "INSERT INTO panestria.task_event (id, goal_id, task_id, kind, actor, payload)"
        " VALUES (:id, :goal_id, :task_id, :kind, :actor, CAST(:payload AS jsonb))"
    )
    values: dict[str, object] = {
        "id": event_id,
        "goal_id": goal_id,
        "task_id": task_id,
        "kind": kind,
        "actor": actor,
        "payload": json.dumps(payload, sort_keys=True),
    }
    if trace_id is not None:
        statement = (
            "INSERT INTO panestria.task_event"
            " (id, goal_id, task_id, kind, actor, payload, trace_id)"
            " VALUES (:id, :goal_id, :task_id, :kind, :actor, CAST(:payload AS jsonb), :trace_id)"
        )
        values["trace_id"] = trace_id
    connection.execute(sa.text(statement), values)
    allocated = connection.execute(
        sa.text("SELECT seq FROM panestria.task_event WHERE id = :id"),
        {"id": event_id},
    ).scalar_one()
    return int(allocated)
