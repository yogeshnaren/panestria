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
) -> int:
    """Allocate the next global seq. Callers must not write afterward."""
    connection.execute(
        sa.text("SELECT pg_advisory_xact_lock(:classid, :objid)"),
        {"classid": EVENT_LOCK[0], "objid": EVENT_LOCK[1]},
    )
    event_id = str(uuid4())
    connection.execute(
        sa.text(
            "INSERT INTO panestria.task_event (id, goal_id, task_id, kind, actor, payload)"
            " VALUES (:id, :goal_id, :task_id, :kind, :actor, CAST(:payload AS jsonb))"
        ),
        {
            "id": event_id,
            "goal_id": goal_id,
            "task_id": task_id,
            "kind": kind,
            "actor": actor,
            "payload": json.dumps(payload, sort_keys=True),
        },
    )
    allocated = connection.execute(
        sa.text("SELECT seq FROM panestria.task_event WHERE id = :id"),
        {"id": event_id},
    ).scalar_one()
    return int(allocated)
