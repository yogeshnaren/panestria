"""Admit one workflow in the caller's transaction. This object never commits."""

from __future__ import annotations

import hashlib
import json
from typing import Any, cast

import sqlalchemy as sa
from dbos import DBOSClient, EnqueueOptions, WorkflowHandle
from sqlalchemy.exc import IntegrityError

from panestria.execution.dbos_runtime import ADMISSION_LOCK, QUEUE_NAME, WORKFLOW_NAME
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.repositories.events import append_domain_event

_OPERATION = "task.admit"
_DISPATCHABLE = frozenset({"CREATED", "READY"})
_OPEN_ATTEMPT = frozenset({"PENDING", "RUNNING"})


class SqlUnitOfWork:
    """Caller-owned SQLAlchemy transaction. Admission does not commit it."""

    def __init__(self, connection: sa.Connection) -> None:
        self.connection = connection


class AdmissionReceipt:
    def __init__(self, task_id: str, workflow_id: str, event_seq: str | None, replayed: bool) -> None:
        self.task_id = task_id
        self.workflow_id = workflow_id
        self.event_seq = event_seq
        self.replayed = replayed


class DurableAdmission:
    def __init__(self, client: DBOSClient) -> None:
        self._client = client

    def submit(
        self,
        uow: SqlUnitOfWork,
        actor: Actor,
        task_id: str,
        workflow_id: str,
        *,
        attempt_id: str,
        idempotency_key: str,
        contract_sha256: str,
    ) -> AdmissionReceipt:
        connection = uow.connection
        connection.execute(
            sa.text("SELECT pg_advisory_xact_lock(:classid, :objid)"),
            {"classid": ADMISSION_LOCK[0], "objid": ADMISSION_LOCK[1]},
        )
        current = connection.execute(
            sa.text(
                "SELECT task.goal_id::text, task.state, contract.sha256,"
                " attempt.attempt_number, attempt.status"
                " FROM panestria.task AS task"
                " JOIN panestria.goal AS goal ON goal.id = task.goal_id"
                " JOIN panestria.goal_contract AS contract ON contract.id = task.contract_id"
                " JOIN panestria.task_attempt AS attempt"
                " ON attempt.id = :attempt_id AND attempt.task_id = task.id"
                " WHERE task.id = :task_id AND goal.owner_id = :owner_id"
                " AND goal.project_id = :project_id"
                " FOR UPDATE OF task"
            ),
            {
                "attempt_id": attempt_id,
                "task_id": task_id,
                "owner_id": actor.owner_id,
                "project_id": actor.project_id,
            },
        ).fetchone()
        if current is None:
            raise KernelDenied("not_found")
        goal_id, state, stored_digest, attempt_number, attempt_status = current
        fingerprint = _fingerprint(
            task_id=task_id,
            workflow_id=workflow_id,
            attempt_id=attempt_id,
            attempt_number=int(attempt_number),
            contract_sha256=contract_sha256,
        )
        existing = connection.execute(
            sa.text(
                "SELECT request_hash, response_ref FROM panestria.idempotency_record"
                " WHERE owner_id = :owner_id AND project_id = :project_id"
                " AND operation = :operation AND request_key = :request_key"
                " FOR UPDATE"
            ),
            {
                "owner_id": actor.owner_id,
                "project_id": actor.project_id,
                "operation": _OPERATION,
                "request_key": idempotency_key,
            },
        ).fetchone()
        if existing is not None:
            return _replay(existing, fingerprint)
        if str(stored_digest).strip() != contract_sha256:
            raise KernelDenied("invalid_contract")
        if str(state) not in _DISPATCHABLE or str(attempt_status) not in _OPEN_ATTEMPT:
            raise KernelDenied("illegal_transition")
        try:
            connection.execute(
                sa.text(
                    "INSERT INTO panestria.workflow_link (task_id, attempt_id, dbos_workflow_id)"
                    " VALUES (:task_id, :attempt_id, :workflow_id)"
                ),
                {"task_id": task_id, "attempt_id": attempt_id, "workflow_id": workflow_id},
            )
        except IntegrityError:
            raise KernelDenied("idempotency_conflict") from None
        options: EnqueueOptions = {
            "workflow_name": WORKFLOW_NAME,
            "queue_name": QUEUE_NAME,
            "workflow_id": workflow_id,
            "workflow_id_reuse_policy": "reject",
        }
        handle: WorkflowHandle[Any] = self._client.enqueue_in_transaction(
            connection, options, task_id, contract_sha256, int(attempt_number)
        )
        if handle.get_workflow_id() != workflow_id:
            raise KernelDenied("idempotency_conflict")
        response = json.dumps(
            {"task_id": task_id, "workflow_id": workflow_id},
            separators=(",", ":"),
            sort_keys=True,
        )
        try:
            connection.execute(
                sa.text(
                    "INSERT INTO panestria.idempotency_record"
                    " (owner_id, project_id, operation, request_key, request_hash, response_ref)"
                    " VALUES (:owner_id, :project_id, :operation, :request_key, :request_hash,"
                    " CAST(:response_ref AS jsonb))"
                ),
                {
                    "owner_id": actor.owner_id,
                    "project_id": actor.project_id,
                    "operation": _OPERATION,
                    "request_key": idempotency_key,
                    "request_hash": fingerprint,
                    "response_ref": response,
                },
            )
        except IntegrityError:
            raise KernelDenied("idempotency_conflict") from None
        seq = append_domain_event(
            connection,
            goal_id=goal_id,
            task_id=task_id,
            kind="task.admitted",
            actor=actor.owner_id,
            payload={"workflow_id": workflow_id},
        )
        return AdmissionReceipt(task_id, workflow_id, str(seq), False)


def _fingerprint(
    *,
    task_id: str,
    workflow_id: str,
    attempt_id: str,
    attempt_number: int,
    contract_sha256: str,
) -> str:
    body = json.dumps(
        {
            "attempt_id": attempt_id,
            "attempt_number": attempt_number,
            "contract_sha256": contract_sha256,
            "task_id": task_id,
            "workflow_id": workflow_id,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(body.encode()).hexdigest()


def _replay(existing: sa.Row[Any], fingerprint: str) -> AdmissionReceipt:
    stored_hash, response = cast(tuple[Any, Any], existing)
    if str(stored_hash).strip() != fingerprint:
        raise KernelDenied("idempotency_conflict")
    if isinstance(response, str):
        loaded = json.loads(response)
    else:
        loaded = response
    if not isinstance(loaded, dict):
        raise KernelDenied("invalid_contract")
    return AdmissionReceipt(str(loaded["task_id"]), str(loaded["workflow_id"]), None, True)
