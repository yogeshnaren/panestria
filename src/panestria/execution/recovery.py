"""Resume a launched process and report the workflow's durable status."""

from __future__ import annotations

import time

from dbos import DBOS


class RecoveryReport:
    def __init__(self, workflow_id: str, status: str) -> None:
        self.workflow_id = workflow_id
        self.status = status


class RecoveryService:
    def recover_pending(self, workflow_id: str, timeout_seconds: float = 20) -> RecoveryReport:
        """Poll after launch. Launch itself resumes an unfinished workflow."""
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            status = DBOS.get_workflow_status(workflow_id)
            if status is not None and status.status in {"SUCCESS", "ERROR"}:
                return RecoveryReport(workflow_id, str(status.status))
            time.sleep(0.2)
        raise TimeoutError(workflow_id)
