"""Dev-only DBOS task worker: the product worker with the scripted "mock" adapter registered.

Start with ``python -m panestria_devkit.execution.task_worker`` and the same
environment as ``python -m panestria.execution.task_workflow``. The product
worker skips mock attempts; this one finishes them through the synthetic journey.
"""

from __future__ import annotations

from pathlib import Path

from panestria.execution import task_workflow
from panestria.kernel.goals import Actor
from panestria_devkit.execution.synthetic_journey import Conn, SyntheticJourney


def finish_mock_attempt(connection: Conn, actor: Actor, goal_id: str, sandbox: Path) -> None:
    SyntheticJourney()._finish_dispatch(connection, actor, goal_id, sandbox)


def register() -> None:
    task_workflow.register_attempt_executor("mock", finish_mock_attempt)


def main() -> None:
    register()
    task_workflow.main()


if __name__ == "__main__":
    main()
