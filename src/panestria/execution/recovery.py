"""Resume a launched process and report the workflow's durable status."""

from __future__ import annotations

import time

import sqlalchemy as sa
from dbos import DBOS

from panestria.execution.dbos_runtime import sqlalchemy_url


class RecoveryReport:
    def __init__(self, workflow_id: str, status: str, error: str) -> None:
        self.workflow_id = workflow_id
        self.status = status
        self.error = error


class RecoveryService:
    def recover_pending(self, workflow_id: str, timeout_seconds: float = 20) -> RecoveryReport:
        """Poll after launch. Launch itself resumes an unfinished workflow."""
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            status = DBOS.get_workflow_status(workflow_id)
            if status is not None and status.status in {"SUCCESS", "ERROR"}:
                observed = status.error
                return RecoveryReport(workflow_id, str(status.status), "" if observed is None else str(observed))
            time.sleep(0.2)
        raise TimeoutError(workflow_id)


def connect_for_admission(database_url: str) -> None:
    """Open the database before any admission write. A refusal leaves no task state."""
    engine = sa.create_engine(sqlalchemy_url(database_url), connect_args={"connect_timeout": 2})
    try:
        with engine.connect() as connection:
            connection.execute(sa.text("SELECT 1"))
    finally:
        engine.dispose()
