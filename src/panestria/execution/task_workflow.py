"""Replay-deterministic task workflow. Database writes stay in one datasource transaction."""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

import sqlalchemy as sa
from dbos import DBOS, DBOSConfig, SetWorkflowID, SQLAlchemyDatasource

from panestria.contracts.task import ALLOWED_TRANSITIONS
from panestria.execution.crash_gate import crash_gate
from panestria.execution.dbos_runtime import (
    APPLICATION_NAME,
    DBOS_SCHEMA,
    QUEUE_NAME,
    WORKFLOW_NAME,
    sqlalchemy_url,
)
from panestria.execution.recovery import RecoveryService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.repositories.events import append_domain_event

CHECKPOINT_SCHEMA = "panestria_checkpoint"
_datasource: SQLAlchemyDatasource | None = None


def configure(database_url: str) -> SQLAlchemyDatasource:
    """Create the checkpoint schema on the same database before DBOS.launch."""
    global _datasource
    url = sqlalchemy_url(database_url)
    _datasource = SQLAlchemyDatasource.create(url, schema=CHECKPOINT_SCHEMA)
    return _datasource


def get_datasource() -> SQLAlchemyDatasource:
    if _datasource is None:
        raise RuntimeError("workflow datasource is not configured")
    return _datasource


def _transition_body(task_id: str, contract_sha256: str, attempt_number: int) -> dict[str, str]:
    session = get_datasource().sql_session()
    current = session.execute(
        sa.text(
            "SELECT task.state, task.row_version, task.goal_id::text, contract.sha256"
            " FROM panestria.task AS task"
            " JOIN panestria.goal_contract AS contract ON contract.id = task.contract_id"
            " JOIN panestria.task_attempt AS attempt"
            " ON attempt.task_id = task.id AND attempt.attempt_number = :attempt"
            " WHERE task.id = :task_id"
            " FOR UPDATE OF task"
        ),
        {"task_id": task_id, "attempt": attempt_number},
    ).one()
    state, row_version, goal_id, digest = current
    if str(digest).strip() != contract_sha256:
        raise KernelDenied("invalid_contract")
    if str(state) != "CREATED":
        return {
            "task_id": task_id,
            "state": str(state),
            "row_version": str(int(row_version)),
            "event_seq": "0",
            "skipped": "true",
        }
    target = "VALIDATING"
    if (str(state), target) not in ALLOWED_TRANSITIONS:
        raise KernelDenied("illegal_transition")
    updated = session.execute(
        sa.text(
            "UPDATE panestria.task SET state = :target, row_version = row_version + 1,"
            " updated_at = now() WHERE id = :task_id AND row_version = :version"
            " RETURNING row_version"
        ),
        {"target": target, "task_id": task_id, "version": int(row_version)},
    ).scalar_one_or_none()
    if updated is None:
        raise KernelDenied("version_conflict")
    seq = append_domain_event(
        session.connection(),
        goal_id=str(goal_id),
        task_id=task_id,
        kind="task.transition",
        actor="workflow",
        payload={"from": str(state), "to": target, "cause": "workflow"},
    )
    crash_gate("before-commit")
    return {
        "task_id": task_id,
        "state": target,
        "row_version": str(int(updated)),
        "event_seq": str(seq),
    }


def transition_task_tx(task_id: str, contract_sha256: str, attempt_number: int) -> dict[str, str]:
    """Tracked transaction. The checkpoint commits with the task row and the event."""
    return get_datasource().run_tx_step(
        {"name": "transition_task_tx", "isolation_level": "SERIALIZABLE"},
        _transition_body,
        task_id,
        contract_sha256,
        attempt_number,
    )


@DBOS.step(name="synthetic_observe")
def synthetic_observe(task_id: str) -> str:
    """External to the database transaction. It must not append a task event."""
    return f"observed:{task_id}"


def _record_effect(task_id: str, contract_sha256: str) -> tuple[str, bool]:
    """Commit the external receipt on its own connection, before the step checkpoint."""
    engine = sa.create_engine(sqlalchemy_url(os.environ["PANESTRIA_DATABASE_URL"]))
    try:
        with engine.begin() as connection:
            found = connection.execute(
                sa.text(
                    "SELECT external_ref FROM panestria.side_effect"
                    " WHERE task_id = :task AND effect_key = 'synthetic-observe'"
                ),
                {"task": task_id},
            ).one_or_none()
            if found is not None:
                return str(found[0]), False
            ref = f"synthetic:{task_id}"
            connection.execute(
                sa.text(
                    "INSERT INTO panestria.side_effect"
                    " (id, task_id, effect_key, target, request_hash, state, external_ref,"
                    " reconciliation_note)"
                    " VALUES (:id, :task, 'synthetic-observe', 'synthetic', :digest,"
                    " 'SUCCEEDED', :ref, 'recorded-before-checkpoint')"
                ),
                {"id": str(uuid.uuid4()), "task": task_id, "digest": contract_sha256, "ref": ref},
            )
            return ref, True
    finally:
        engine.dispose()


@DBOS.step(name="synthetic_effect", retries_allowed=False)
def synthetic_effect(task_id: str, contract_sha256: str) -> str:
    """Reconcile a committed effect. A lost checkpoint must not repeat it."""
    ref, created = _record_effect(task_id, contract_sha256)
    if created:
        crash_gate("after-effect")
    return ref


def _mark_failed_body(task_id: str, contract_sha256: str, attempt_number: int) -> dict[str, str]:
    session = get_datasource().sql_session()
    current = session.execute(
        sa.text(
            "SELECT task.state, task.row_version, task.goal_id::text, contract.sha256"
            " FROM panestria.task AS task"
            " JOIN panestria.goal_contract AS contract ON contract.id = task.contract_id"
            " JOIN panestria.task_attempt AS attempt"
            " ON attempt.task_id = task.id AND attempt.attempt_number = :attempt"
            " WHERE task.id = :task_id"
            " FOR UPDATE OF task"
        ),
        {"task_id": task_id, "attempt": attempt_number},
    ).one()
    state, row_version, goal_id, digest = current
    if str(digest).strip() != contract_sha256:
        raise KernelDenied("invalid_contract")
    if str(state) == "FAILED":
        return {"task_id": task_id, "state": "FAILED", "replayed": "true"}
    target = "FAILED"
    if (str(state), target) not in ALLOWED_TRANSITIONS:
        raise KernelDenied("illegal_transition")
    updated = session.execute(
        sa.text(
            "UPDATE panestria.task SET state = :target, row_version = row_version + 1,"
            " updated_at = now() WHERE id = :task_id AND row_version = :version"
            " RETURNING row_version"
        ),
        {"target": target, "task_id": task_id, "version": int(row_version)},
    ).scalar_one_or_none()
    if updated is None:
        raise KernelDenied("version_conflict")
    append_domain_event(
        session.connection(),
        goal_id=str(goal_id),
        task_id=task_id,
        kind="task.transition",
        actor="workflow",
        payload={"from": str(state), "to": target, "cause": "terminal-synthetic-failure"},
    )
    return {"task_id": task_id, "state": target, "row_version": str(int(updated))}


def mark_failed_tx(task_id: str, contract_sha256: str, attempt_number: int) -> dict[str, str]:
    """Commit FAILED before the workflow exception. Replay does not append again."""
    return get_datasource().run_tx_step(
        {"name": "mark_failed_tx", "isolation_level": "SERIALIZABLE"},
        _mark_failed_body,
        task_id,
        contract_sha256,
        attempt_number,
    )


_PAST_READY = frozenset({"LEASED", "RUNNING", "VERIFYING", "WAITING_APPROVAL"})


def _lease_body(task_id: str, contract_sha256: str, attempt_number: int) -> dict[str, str]:
    session = get_datasource().sql_session()
    current = session.execute(
        sa.text(
            "SELECT task.state, task.row_version, task.goal_id::text, contract.sha256"
            " FROM panestria.task AS task"
            " JOIN panestria.goal_contract AS contract ON contract.id = task.contract_id"
            " WHERE task.id = :task_id"
            " FOR UPDATE OF task"
        ),
        {"task_id": task_id},
    ).one()
    state, row_version, goal_id, digest = current
    if str(digest).strip() != contract_sha256:
        raise KernelDenied("invalid_contract")
    if str(state) in _PAST_READY:
        return {"task_id": task_id, "state": str(state), "replayed": "true"}
    if str(state) != "READY":
        raise KernelDenied("illegal_transition")
    updated = session.execute(
        sa.text(
            "UPDATE panestria.task SET state = 'LEASED', row_version = row_version + 1,"
            " updated_at = now() WHERE id = :task_id AND row_version = :version"
            " RETURNING row_version"
        ),
        {"task_id": task_id, "version": int(row_version)},
    ).scalar_one_or_none()
    if updated is None:
        raise KernelDenied("version_conflict")
    session.execute(
        sa.text(
            "UPDATE panestria.task_attempt SET status = 'RUNNING',"
            " started_at = COALESCE(started_at, now())"
            " WHERE task_id = :task_id AND attempt_number = :attempt AND status = 'PENDING'"
        ),
        {"task_id": task_id, "attempt": attempt_number},
    )
    append_domain_event(
        session.connection(),
        goal_id=str(goal_id),
        task_id=task_id,
        kind="task.transition",
        actor="workflow",
        payload={"from": "READY", "to": "LEASED", "cause": "admitted"},
    )
    crash_gate("before-commit")
    return {"task_id": task_id, "state": "LEASED", "row_version": str(int(updated))}


def lease_attempt_tx(task_id: str, contract_sha256: str, attempt_number: int) -> dict[str, str]:
    """Commit the lease with its event. A crash before commit leaves the task READY."""
    return get_datasource().run_tx_step(
        {"name": "lease_attempt_tx", "isolation_level": "SERIALIZABLE"},
        _lease_body,
        task_id,
        contract_sha256,
        attempt_number,
    )


@DBOS.step(name="execute_admitted_attempt", retries_allowed=False)
def execute_admitted_attempt(task_id: str, attempt_number: int) -> str:
    """Run the mock worker for an admitted attempt. A non-mock attempt is skipped."""
    import psycopg

    from panestria.execution.synthetic_journey import SyntheticJourney
    from panestria.kernel.goals import Actor

    with psycopg.connect(os.environ["PANESTRIA_DATABASE_URL"]) as connection:
        row = connection.execute(
            "SELECT goal.id::text, goal.owner_id::text, goal.project_id::text,"
            " attempt.external_ref, attempt.adapter"
            " FROM panestria.task AS task"
            " JOIN panestria.goal AS goal ON goal.id = task.goal_id"
            " JOIN panestria.task_attempt AS attempt"
            " ON attempt.task_id = task.id AND attempt.attempt_number = %s"
            " WHERE task.id = %s",
            (attempt_number, task_id),
        ).fetchone()
        if row is None or str(row[4]) != "mock" or row[3] is None:
            return "skipped"
        SyntheticJourney()._finish_dispatch(
            connection,
            Actor(str(row[1]), str(row[2])),
            str(row[0]),
            Path(str(row[3])),
        )
    return "done"


@DBOS.workflow(name=WORKFLOW_NAME)
def run_task_workflow(task_id: str, contract_sha256: str, attempt_number: int) -> dict[str, str]:
    result = transition_task_tx(task_id, contract_sha256, attempt_number)
    if result.get("skipped") == "true":
        lease_attempt_tx(task_id, contract_sha256, attempt_number)
        crash_gate("before-worker")
        result["journey"] = execute_admitted_attempt(task_id, attempt_number)
        return result
    crash_gate("after-commit")
    result["observed"] = synthetic_observe(task_id)
    return result


@DBOS.workflow(name="run_effect_workflow")
def run_effect_workflow(task_id: str, contract_sha256: str, attempt_number: int) -> dict[str, str]:
    transition_task_tx(task_id, contract_sha256, attempt_number)
    ref = synthetic_effect(task_id, contract_sha256)
    return {"task_id": task_id, "external_ref": ref}


@DBOS.workflow(name="run_failing_workflow")
def run_failing_workflow(task_id: str, contract_sha256: str, attempt_number: int) -> dict[str, str]:
    mark_failed_tx(task_id, contract_sha256, attempt_number)
    raise RuntimeError("terminal-synthetic-failure")


def _runtime_config(database_url: str) -> DBOSConfig:
    return {
        "name": APPLICATION_NAME,
        "system_database_url": sqlalchemy_url(database_url),
        "dbos_system_schema": DBOS_SCHEMA,
        "enable_otlp": False,
        "log_level": "ERROR",
        "use_listen_notify": True,
    }


def _start(database_url: str, *, listen: bool = False) -> None:
    configure(database_url)
    DBOS(config=_runtime_config(database_url))
    if listen:
        DBOS.listen_queues([QUEUE_NAME])
    DBOS.launch()


def main() -> None:
    database_url = os.environ["PANESTRIA_DATABASE_URL"]
    mode = os.environ.get("PANESTRIA_MODE", "run")
    _start(database_url, listen=mode == "consume")
    try:
        workflow_id = os.environ["PANESTRIA_WORKFLOW_ID"]
        if mode == "consume":
            report = RecoveryService().recover_pending(workflow_id, timeout_seconds=45)
            if report.status != "SUCCESS":
                raise SystemExit(2)
            return
        if mode == "recover":
            report = RecoveryService().recover_pending(workflow_id)
            if report.status != "SUCCESS":
                raise SystemExit(2)
            return
        task_id = os.environ["PANESTRIA_TASK_ID"]
        digest = os.environ["PANESTRIA_CONTRACT_SHA256"]
        attempt = int(os.environ["PANESTRIA_ATTEMPT"])
        if mode == "effect":
            function = run_effect_workflow
        elif mode == "fail":
            function = run_failing_workflow
        else:
            function = run_task_workflow
        with SetWorkflowID(workflow_id, workflow_id_reuse_policy="return-existing"):
            handle = DBOS.start_workflow(function, task_id, digest, attempt)
        if mode == "fail":
            try:
                handle.get_result()
            except Exception:
                report = RecoveryService().recover_pending(workflow_id)
            else:
                raise SystemExit(4)
            if report.status != "ERROR" or "terminal-synthetic-failure" not in report.error:
                raise SystemExit(4)
            return
        if mode == "duplicate":
            handle.get_result()
            with SetWorkflowID(workflow_id, workflow_id_reuse_policy="return-existing"):
                again = DBOS.start_workflow(run_task_workflow, task_id, digest, attempt)
            if again.get_workflow_id() != workflow_id:
                raise SystemExit(3)
            again.get_result()
            return
        if os.environ.get("PANESTRIA_CRASH_AT"):
            while True:
                time.sleep(0.2)
        handle.get_result()
    finally:
        DBOS.destroy(destroy_registry=True, workflow_completion_timeout_sec=0)


if __name__ == "__main__":
    main()
