"""Approval locks and writes. These functions do not commit."""

from __future__ import annotations

import json
from typing import Any

from panestria.kernel.uow import UnitOfWork

_DECISION = "approval.decide"


def lock_task_row(
    uow: UnitOfWork,
    owner_id: str,
    project_id: str,
    task_id: str,
) -> tuple[str, str, int, str] | None:
    row = uow.execute(
        "SELECT task.goal_id::text, task.state, task.row_version, task.contract_id::text"
        " FROM panestria.task AS task"
        " JOIN panestria.goal AS goal ON goal.id = task.goal_id"
        " WHERE task.id = %s AND goal.owner_id = %s AND goal.project_id = %s"
        " FOR UPDATE OF task",
        (task_id, owner_id, project_id),
    ).fetchone()
    if row is None:
        return None
    goal_id, state, row_version, contract_id = row
    return str(goal_id), str(state), int(row_version), str(contract_id)


def peek_request_task(
    uow: UnitOfWork,
    owner_id: str,
    project_id: str,
    request_id: str,
) -> str | None:
    row = uow.execute(
        "SELECT task_id::text FROM panestria.approval_request"
        " WHERE id = %s AND owner_id = %s AND project_id = %s",
        (request_id, owner_id, project_id),
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return str(row[0])


def lock_request(
    uow: UnitOfWork,
    owner_id: str,
    project_id: str,
    request_id: str,
) -> tuple[Any, ...] | None:
    return uow.execute(
        "SELECT goal_id::text, task_id::text, minimum_actor_id::text, action_kind,"
        " effect_digest, state, preview"
        " FROM panestria.approval_request"
        " WHERE id = %s AND owner_id = %s AND project_id = %s"
        " FOR UPDATE",
        (request_id, owner_id, project_id),
    ).fetchone()


def insert_request(
    uow: UnitOfWork,
    request_id: str,
    goal_id: str,
    task_id: str,
    owner_id: str,
    project_id: str,
    minimum_actor_id: str,
    action_kind: str,
    digest: str,
    policy_version: str,
    expires_at: str,
    preview: str,
) -> None:
    uow.execute(
        "INSERT INTO panestria.approval_request ("
        " id, goal_id, task_id, owner_id, project_id, minimum_actor_id, action_kind,"
        " effect_digest, policy_version, state, expires_at, preview)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'PENDING', %s::timestamptz, %s::jsonb)",
        (
            request_id,
            goal_id,
            task_id,
            owner_id,
            project_id,
            minimum_actor_id,
            action_kind,
            digest,
            policy_version,
            expires_at,
            preview,
        ),
    )


def mark_wait(
    uow: UnitOfWork,
    task_id: str,
    expected_version: int,
    state: str,
    continuation_kind: str,
    resume_phase: str,
) -> int | None:
    row = uow.execute(
        "UPDATE panestria.task SET state = %s, continuation_kind = %s, resume_phase = %s,"
        " row_version = row_version + 1, updated_at = now()"
        " WHERE id = %s AND row_version = %s RETURNING row_version",
        (state, continuation_kind, resume_phase, task_id, expected_version),
    ).fetchone()
    if row is None:
        return None
    return int(row[0])


def mark_decision(uow: UnitOfWork, request_id: str, state: str, actor_id: str) -> int:
    return uow.execute(
        "UPDATE panestria.approval_request"
        " SET state = %s, decided_at = now(), decided_by = %s"
        " WHERE id = %s AND state = 'PENDING'",
        (state, actor_id, request_id),
    ).rowcount


def mark_expired(uow: UnitOfWork, request_id: str) -> int:
    return uow.execute(
        "UPDATE panestria.approval_request SET state = 'EXPIRED'"
        " WHERE id = %s AND state = 'PENDING'",
        (request_id,),
    ).rowcount


def bump_version(uow: UnitOfWork, task_id: str, expected_version: int) -> int | None:
    row = uow.execute(
        "UPDATE panestria.task SET row_version = row_version + 1, updated_at = now()"
        " WHERE id = %s AND row_version = %s RETURNING row_version",
        (task_id, expected_version),
    ).fetchone()
    if row is None:
        return None
    return int(row[0])


def database_now(uow: UnitOfWork) -> str:
    row = uow.execute("SELECT to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"+00:00')").fetchone()
    if row is None:
        raise RuntimeError("database clock missing")
    return str(row[0])


def request_expired(uow: UnitOfWork, request_id: str) -> bool:
    row = uow.execute(
        "SELECT expires_at <= now() FROM panestria.approval_request WHERE id = %s",
        (request_id,),
    ).fetchone()
    return row is not None and bool(row[0])


def lock_idempotency(
    uow: UnitOfWork,
    owner_id: str,
    project_id: str,
    request_key: str,
) -> tuple[str, object] | None:
    return uow.execute(
        "SELECT request_hash, response_ref FROM panestria.idempotency_record"
        " WHERE owner_id = %s AND project_id = %s AND operation = %s AND request_key = %s"
        " FOR UPDATE",
        (owner_id, project_id, _DECISION, request_key),
    ).fetchone()


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
        " VALUES (%s, %s, %s, %s, %s, %s::jsonb)",
        (owner_id, project_id, _DECISION, request_key, request_hash, response_ref),
    )


def required_verdicts(
    uow: UnitOfWork,
    task_id: str,
    candidate_sha256: str | None = None,
) -> list[tuple[str, str | None]]:
    """Latest run on the current attempt. A missing artifact does not reveal an older PASS."""
    rows = uow.execute(
        "SELECT check_row.check_key, latest.verdict, latest.evidence_artifact_id::text,"
        " latest.candidate_sha256"
        " FROM panestria.acceptance_check AS check_row"
        " JOIN panestria.task AS task ON task.contract_id = check_row.contract_id"
        " JOIN LATERAL ("
        " SELECT attempt.id FROM panestria.task_attempt AS attempt"
        " WHERE attempt.task_id = task.id AND attempt.lease_epoch = task.lease_epoch"
        " ORDER BY attempt.attempt_number DESC LIMIT 1"
        " ) AS current_attempt ON true"
        " LEFT JOIN LATERAL ("
        " SELECT run.verdict, run.evidence_artifact_id, run.candidate_sha256"
        " FROM panestria.check_run AS run"
        " WHERE run.acceptance_check_id = check_row.id"
        " AND run.attempt_id = current_attempt.id"
        " AND run.task_id = task.id"
        " AND run.contract_id = check_row.contract_id"
        " ORDER BY run.checked_at DESC LIMIT 1"
        " ) AS latest ON true"
        " WHERE task.id = %s AND check_row.required"
        " ORDER BY check_row.check_key",
        (task_id,),
    ).fetchall()
    return [
        (str(key), _authoritative(verdict, evidence_id, stored_candidate, candidate_sha256))
        for key, verdict, evidence_id, stored_candidate in rows
    ]


def _authoritative(
    verdict: object,
    evidence_id: object,
    stored_candidate: object,
    expected_candidate: str | None,
) -> str | None:
    if verdict is None:
        return None
    recorded = str(verdict)
    if recorded != "PASS":
        return recorded
    if evidence_id is None or stored_candidate is None:
        return None
    if expected_candidate is not None and str(stored_candidate).strip() != expected_candidate:
        return None
    return "PASS"


def consumption(uow: UnitOfWork, request_id: str) -> tuple[bool, str | None]:
    row = uow.execute(
        "SELECT side_effect_id::text FROM panestria.approval_consumption"
        " WHERE approval_request_id = %s",
        (request_id,),
    ).fetchone()
    if row is None:
        return False, None
    return True, None if row[0] is None else str(row[0])


def insert_effect(
    uow: UnitOfWork,
    effect_id: str,
    task_id: str,
    effect_key: str,
    target: str,
    digest: str,
    request_id: str,
) -> None:
    uow.execute(
        "INSERT INTO panestria.side_effect ("
        " id, task_id, effect_key, target, request_hash, state, effect_digest, approval_request_id)"
        " VALUES (%s, %s, %s, %s, %s, 'PREPARED', %s, %s)",
        (effect_id, task_id, effect_key, target, digest, digest, request_id),
    )


def insert_consumption(
    uow: UnitOfWork,
    request_id: str,
    effect_id: str | None,
    actor_id: str,
    digest: str,
) -> None:
    uow.execute(
        "INSERT INTO panestria.approval_consumption"
        " (approval_request_id, side_effect_id, consumed_by, effect_digest)"
        " VALUES (%s, %s, %s, %s)",
        (request_id, effect_id, actor_id, digest),
    )


def effect_count(uow: UnitOfWork, task_id: str) -> int:
    row = uow.execute(
        "SELECT count(*) FROM panestria.side_effect WHERE task_id = %s",
        (task_id,),
    ).fetchone()
    return 0 if row is None else int(row[0])


def preview_json(preview: dict[str, Any]) -> str:
    return json.dumps(preview, separators=(",", ":"), sort_keys=True)
