"""Real queue/PG/Git/MCP/Docker/CLI with explicit native/account/resource fixtures."""

import json
import threading

import pytest
from test_background_queue import cli
from test_background_run import setup
from test_background_selection import another
from test_native_plan_execution import native_plan as native_plan  # noqa: F401
from test_native_plan_execution import prepared_plan as prepared_plan  # noqa: F401
from test_owner_build_cli import owner_cli as owner_cli  # noqa: F401
from test_registered_check_authority import git
from typer.testing import CliRunner

from panestria.cli.main import app
from panestria.execution.background_controller import work_queue
from panestria.kernel.errors import KernelDenied


def test_connected_controller_emits_progress_and_stops_at_one_exact_owner_review(
    prepared_plan, native_plan, monkeypatch
):
    f, owner, plan, state, request, _ = setup(prepared_plan, native_plan, monkeypatch)
    another(f, owner, plan, request, priority=1)
    result = CliRunner().invoke(
        app,
        [
            "background",
            "work",
            "--config",
            str(f.config),
            "--ticks",
            "2",
            "--jobs",
            "1",
            "--allow-background-subscription-run",
        ],
    )
    assert result.exit_code == 0, result.output
    lines = [json.loads(line) for line in result.output.splitlines()]
    assert [r.get("kind") for r in lines] == ["QUEUE_TICK", "QUEUE_JOB_RETURNED", None]
    assert lines[0]["item_id"] == request.item_id and lines[1]["status"] == "WAITING_APPROVAL"
    assert lines[0]["candidate_count"] == 2
    assert lines[-1]["status"] == "FINISHED" and lines[-1]["reason"] == "job_limit_reached"
    assert len(lines[-1]["items"]) == 1 and state["launches"] == 2 and state["peak"] == 1
    assert git(owner.settings.repository, "rev-parse", "refs/heads/main") == f.base
    assert owner.status(plan.goal_id)["task_state"] == "WAITING_APPROVAL"
    assert lines[-1]["automatic_merge"] is lines[-1]["implicit_resume"] is False
    with owner.connect() as c:
        before = c.execute("SELECT count(*) FROM panestria.task_event").fetchone()
    metadata = state["metadata"]
    observations = []
    idle = work_queue(
        owner,
        allow_background_subscription_run=True,
        maximum_ticks=2,
        maximum_jobs=2,
        on_observation=observations.append,
    )
    assert idle["reason"] == "tick_limit_reached" and idle["ticks"] == 2 and idle["items"] == []
    assert state["launches"] == 2 and state["metadata"] == metadata
    assert len(observations) == 2 and all(v["candidate_count"] == 0 for v in observations)
    with owner.connect() as c:
        assert c.execute("SELECT count(*) FROM panestria.task_event").fetchone() == before


def test_connected_controller_stops_on_selection_race_without_alternate_job_or_implicit_resume(
    prepared_plan, native_plan, monkeypatch
):
    f, owner, plan, state, original, _ = setup(prepared_plan, native_plan, monkeypatch)
    another(f, owner, plan, original, priority=1)
    with pytest.raises(KernelDenied, match="explicit_background"):
        work_queue(owner, allow_background_subscription_run=False)

    def withdraw(view):
        if view["kind"] == "QUEUE_TICK" and view["item_id"]:
            binding = cli(f, "show", view["item_id"])["binding_sha256"]
            cli(f, "withdraw", view["item_id"], binding)

    stopped = work_queue(
        owner, allow_background_subscription_run=True, maximum_ticks=2, maximum_jobs=2, on_observation=withdraw
    )
    assert stopped["status"] == "STOPPED" and stopped["ticks"] == 1 and len(stopped["items"]) == 1
    assert state["launches"] == 0
    cancel = threading.Event()
    cancel.set()
    with owner.connect() as c:
        before = c.execute("SELECT count(*) FROM panestria.task_event").fetchone()
    assert work_queue(owner, allow_background_subscription_run=True, cancel=cancel)["status"] == "CANCELLED"
    with owner.connect() as c:
        assert c.execute("SELECT count(*) FROM panestria.task_event").fetchone() == before
