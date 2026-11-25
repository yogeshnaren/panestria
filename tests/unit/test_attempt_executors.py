"""The product task worker finishes only attempts whose adapter has a registered executor."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from panestria.execution import task_workflow


def _executor(_connection: Any, _actor: Any, _goal_id: str, _sandbox: Path) -> None:
    return None


def test_product_entry_points_register_no_executor_and_load_no_devkit() -> None:
    probe = (
        "import json, sys\n"
        "import panestria.api.serve, panestria.cli.main\n"
        "from panestria.execution import task_workflow\n"
        "print(json.dumps([sorted(task_workflow._attempt_executors),"
        " sorted(m for m in sys.modules if m.split('.')[0] == 'panestria_devkit')]))\n"
    )
    completed = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, timeout=60, check=True)
    assert json.loads(completed.stdout) == [[], []]


def test_registration_is_idempotent_but_cannot_be_replaced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(task_workflow, "_attempt_executors", {})
    task_workflow.register_attempt_executor("mock", _executor)
    task_workflow.register_attempt_executor("mock", _executor)
    with pytest.raises(ValueError, match="already registered: mock"):
        task_workflow.register_attempt_executor("mock", lambda *_args: None)
    assert task_workflow._attempt_executors == {"mock": _executor}
