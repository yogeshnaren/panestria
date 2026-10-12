"""Replay-deterministic task workflow. Database writes stay in one datasource transaction."""

from __future__ import annotations

import os
import time
from pathlib import Path

import sqlalchemy as sa
from dbos import DBOS, DBOSConfig, SetWorkflowID, SQLAlchemyDatasource

from panestria.contracts.task import ALLOWED_TRANSITIONS
from panestria.execution.dbos_runtime import (
    APPLICATION_NAME,
    DBOS_SCHEMA,
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


def _crash_gate(point: str) -> None:
    """Test-only pause. Unset the variable and this is a no-op, including on replay."""
    if os.environ.get("PANESTRIA_CRASH_AT") != point:
        return
    Path(os.environ["PANESTRIA_READY_FILE"]).write_text(point)
    while True:
        time.sleep(0.2)


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
    _crash_gate("before-commit")
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


@DBOS.workflow(name=WORKFLOW_NAME)
def run_task_workflow(task_id: str, contract_sha256: str, attempt_number: int) -> dict[str, str]:
    result = transition_task_tx(task_id, contract_sha256, attempt_number)
    _crash_gate("after-commit")
    result["observed"] = synthetic_observe(task_id)
    return result


def _runtime_config(database_url: str) -> DBOSConfig:
    return {
        "name": APPLICATION_NAME,
        "system_database_url": sqlalchemy_url(database_url),
        "dbos_system_schema": DBOS_SCHEMA,
        "enable_otlp": False,
        "log_level": "ERROR",
        "use_listen_notify": True,
    }


def _start(database_url: str) -> None:
    configure(database_url)
    DBOS(config=_runtime_config(database_url))
    DBOS.launch()


def main() -> None:
    database_url = os.environ["PANESTRIA_DATABASE_URL"]
    mode = os.environ.get("PANESTRIA_MODE", "run")
    _start(database_url)
    try:
        if mode == "recover":
            report = RecoveryService().recover_pending(os.environ["PANESTRIA_WORKFLOW_ID"])
            if report.status != "SUCCESS":
                raise SystemExit(2)
            return
        workflow_id = os.environ["PANESTRIA_WORKFLOW_ID"]
        task_id = os.environ["PANESTRIA_TASK_ID"]
        digest = os.environ["PANESTRIA_CONTRACT_SHA256"]
        attempt = int(os.environ["PANESTRIA_ATTEMPT"])
        with SetWorkflowID(workflow_id, workflow_id_reuse_policy="return-existing"):
            handle = DBOS.start_workflow(run_task_workflow, task_id, digest, attempt)
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
