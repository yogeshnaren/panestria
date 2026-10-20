"""Scoped goal and idempotency writes. These functions do not commit."""

from __future__ import annotations

from panestria.kernel.uow import UnitOfWork

GOAL_LOOKUP_SQL = "SELECT id::text, status FROM panestria.goal WHERE id = %s AND owner_id = %s AND project_id = %s"
EVENT_LOOKUP_SQL = (
    "SELECT seq, kind, payload FROM panestria.task_event WHERE goal_id = %s AND seq > %s ORDER BY seq LIMIT %s"
)


def lock_idempotency(
    uow: UnitOfWork,
    owner_id: str,
    project_id: str,
    request_key: str,
) -> tuple[str, object] | None:
    return uow.execute(
        "SELECT request_hash, response_ref FROM panestria.idempotency_record"
        " WHERE owner_id = %s AND project_id = %s AND operation = 'goal.submit'"
        " AND request_key = %s FOR UPDATE",
        (owner_id, project_id, request_key),
    ).fetchone()


def insert_goal(uow: UnitOfWork, goal_id: str, owner_id: str, project_id: str, intent: str) -> None:
    uow.execute(
        "INSERT INTO panestria.goal (id, owner_id, project_id, intent, status) VALUES (%s, %s, %s, %s, 'CREATED')",
        (goal_id, owner_id, project_id, intent),
    )


def insert_contract(
    uow: UnitOfWork,
    contract_id: str,
    goal_id: str,
    version: int,
    body: str,
    digest: str,
) -> None:
    uow.execute(
        "INSERT INTO panestria.goal_contract (id, goal_id, version, schema_version, body, sha256)"
        " VALUES (%s, %s, %s, 1, %s::jsonb, %s)",
        (contract_id, goal_id, version, body, digest),
    )


def insert_idempotency(
    uow: UnitOfWork,
    owner_id: str,
    project_id: str,
    request_key: str,
    request_hash: str,
    response_ref: str,
) -> None:
    uow.execute(
        "INSERT INTO panestria.idempotency_record"
        " (owner_id, project_id, operation, request_key, request_hash, response_ref)"
        " VALUES (%s, %s, 'goal.submit', %s, %s, %s::jsonb)",
        (owner_id, project_id, request_key, request_hash, response_ref),
    )


def read_goal(uow: UnitOfWork, owner_id: str, project_id: str, goal_id: str) -> tuple[str, str] | None:
    return uow.execute(GOAL_LOOKUP_SQL, (goal_id, owner_id, project_id)).fetchone()


def read_events(
    uow: UnitOfWork,
    owner_id: str,
    project_id: str,
    goal_id: str,
    after: int,
    limit: int,
) -> list[tuple[int, str, dict[str, object]]] | None:
    if read_goal(uow, owner_id, project_id, goal_id) is None:
        return None
    rows = uow.execute(EVENT_LOOKUP_SQL, (goal_id, after, limit)).fetchall()
    return [(int(row[0]), str(row[1]), dict(row[2])) for row in rows]
