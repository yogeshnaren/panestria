"""Dev-only R0 loopback server: the product goal API plus the synthetic journey driver.

Start with ``python -m panestria_devkit.api.serve`` and the environment of
``python -m panestria.api.serve``. An accepted goal is continued under
``PANESTRIA_SANDBOX`` through the same admission path the tests use.
"""

from __future__ import annotations

import queue
import sys
import threading
from pathlib import Path

import psycopg

from panestria.api import serve
from panestria.kernel.goals import Actor
from panestria_devkit.execution.synthetic_journey import SyntheticJourney


class JourneyDriver:
    """Continue one goal at a time. HTTP handlers only enqueue the goal id."""

    def __init__(self, database_url: str, owner_id: str, project_id: str, sandbox: Path) -> None:
        self._database_url = database_url
        self._actor = Actor(owner_id, project_id)
        self._sandbox = sandbox
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._thread = threading.Thread(target=self._run, name="panestria-journey", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def submit(self, goal_id: str) -> None:
        self._queue.put(goal_id)

    def stop(self) -> None:
        self._queue.put(None)
        self._thread.join(timeout=2)

    def _run(self) -> None:
        while True:
            goal_id = self._queue.get()
            if goal_id is None:
                return
            pending = [goal_id]
            while True:
                try:
                    nxt = self._queue.get_nowait()
                except queue.Empty:
                    break
                if nxt is None:
                    return
                pending.append(nxt)
            for item in dict.fromkeys(pending):
                self._once(item)

    def _once(self, goal_id: str) -> None:
        sandbox = self._sandbox / goal_id
        sandbox.mkdir(parents=True, exist_ok=True)
        try:
            with psycopg.connect(self._database_url) as connection:
                goal = connection.execute(
                    "SELECT status FROM panestria.goal WHERE id = %s AND owner_id = %s AND project_id = %s",
                    (goal_id, self._actor.owner_id, self._actor.project_id),
                ).fetchone()
                if goal is None or str(goal[0]) in {"CANCELLED", "COMPLETED", "FAILED"}:
                    connection.rollback()
                    return
                count = connection.execute(
                    "SELECT count(*) FROM panestria.task WHERE goal_id = %s",
                    (goal_id,),
                ).fetchone()
                connection.commit()
                journey = SyntheticJourney()
                if count is not None and int(count[0]) == 0:
                    journey.open_contract_wait(connection, self._actor, goal_id, sandbox)
                else:
                    journey.resume(connection, self._actor, goal_id, sandbox)
                connection.commit()
        except Exception:
            sys.stderr.write("journey continuation failed\n")


def main() -> None:
    serve.main(journey=JourneyDriver)


if __name__ == "__main__":
    main()
