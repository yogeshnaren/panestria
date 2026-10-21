"""Real PTY/owner CLI/Postgres/Git; only native generation/certificates are fixtures."""

import curses
import json
import os
import time
from uuid import uuid4

from test_ask_tui import terminal
from test_native_plan_execution import native_plan as native_plan  # noqa: F401
from test_native_plan_execution import prepared_plan as prepared_plan  # noqa: F401
from test_owner_build_cli import contract, invoke, owner_cli, prepare, submit  # noqa: F401 -- fixture
from test_registered_check_authority import git
from typer.testing import CliRunner

from panestria.cli.build_tui import BuildReviewClient, BuildReviewTerminal, BuildUnconfirmed
from panestria.cli.main import app


def pending(f):
    doc = contract(f, prepare(f))
    result = submit(f, doc)
    assert result["task_state"] == "WAITING_APPROVAL"
    return doc, result


def settled(terminal_app, predicate):
    deadline = time.monotonic() + 10
    while not predicate():
        assert time.monotonic() < deadline, terminal_app.view.notice
        terminal_app.drain()
        time.sleep(0.02)


def test_actual_build_terminal_reviews_diff_and_explicitly_merges_exact_candidate(owner_cli, record_property):  # noqa: F811
    f = owner_cli
    record_property("scope", "Actual PTY/PG/Docker/Git/owner CLI; TEST_FIXTURE_NOT_LIVE native/certificates")
    doc, result = pending(f)
    with terminal(f.config, entry=("build", "tui"), arguments=(doc["goal_id"],)) as t:
        t.until(b"WAITING_APPROVAL")
        os.write(t.master, b"\t")
        t.until(b"+value = 43")
        os.write(t.master, b"a")
        t.until(b"Review the frozen preview")
        assert git(f.bare, "rev-parse", "HEAD") == f.base  # Opening review is not approval.
        os.write(t.master, b"MERGE\r")
        t.until(b"COMPLETED", timeout=15)
        assert git(f.bare, "rev-parse", "HEAD") == result["candidate_commit"]
        assert f.dsn.encode() not in t.transcript
        os.write(t.master, b"q")
    assert f.transport.launches == 1  # The view and merge never invoke another model.
    assert git(f.source, "rev-parse", "HEAD") == f.base


def test_actual_build_terminal_stale_frozen_review_cannot_merge_after_cancellation(owner_cli):  # noqa: F811
    f = owner_cli
    doc, result = pending(f)
    with terminal(f.config, entry=("build", "tui"), arguments=(doc["goal_id"],)) as t:
        t.until(b"WAITING_APPROVAL")
        os.write(t.master, b"a")
        t.until(b"Review the frozen preview")
        invoke(f, "cancel", doc["goal_id"], str(result["row_version"]))
        os.write(t.master, b"MERGE\r")
        t.until(b"UNCONFIRMED; view cleared.", timeout=10)
        assert git(f.bare, "rev-parse", "HEAD") == f.base
        curses.setupterm(term="xterm-256color")
        os.write(t.master, curses.tigetstr("kf5"))
        t.until(b"CANCELLED")
        os.write(t.master, b"q")
    assert f.transport.launches == 1


def test_actual_build_terminal_cancellation_needs_separate_explicit_confirmation(owner_cli):  # noqa: F811
    f = owner_cli
    doc, result = pending(f)
    with terminal(f.config, entry=("build", "tui"), arguments=(doc["goal_id"],)) as t:
        t.until(b"WAITING_APPROVAL")
        os.write(t.master, b"c")
        t.until(b"Review the frozen preview")
        assert invoke(f, "status", doc["goal_id"])["row_version"] == result["row_version"]
        os.write(t.master, b"CANCEL\r")
        t.until(b"CANCELLED", timeout=10)
        os.write(t.master, b"q")
    assert git(f.bare, "rev-parse", "HEAD") == f.base


def test_lost_actual_merge_acknowledgement_never_replays_and_refresh_recovers(owner_cli, monkeypatch):  # noqa: F811
    f = owner_cli
    doc, result = pending(f)
    client = BuildReviewClient(f.config, doc["goal_id"])
    terminal_app = BuildReviewTerminal(client)
    original, approvals = client.request, []

    def lose(operation, arguments):
        value = original(operation, arguments)
        if operation == "approve":
            approvals.append(arguments)
            raise BuildUnconfirmed  # Actual protected CAS committed, response lost.
        return value

    monkeypatch.setattr(client, "request", lose)
    try:
        terminal_app.refresh()
        settled(terminal_app, lambda: bool(terminal_app.view.snapshot))
        terminal_app.review("approve")
        frozen_digest = terminal_app.view.frozen["approval"]["effect_digest"]
        terminal_app.view.snapshot["approval"]["effect_digest"] = "ff" * 32
        terminal_app.view.typed = "MERGE"
        terminal_app.confirm()
        settled(terminal_app, lambda: not terminal_app.busy)
        assert not terminal_app.view.snapshot and "UNCONFIRMED" in terminal_app.view.notice
        assert git(f.bare, "rev-parse", "HEAD") == result["candidate_commit"]
        assert len(approvals) == 1 and approvals[0][1] == frozen_digest
        terminal_app.confirm()  # No retained confirmation or automatic retry.
        terminal_app.refresh()
        settled(terminal_app, lambda: bool(terminal_app.view.snapshot))
        assert terminal_app.view.snapshot["task_state"] == "COMPLETED" and len(approvals) == 1
        assert "value = 43" not in repr(terminal_app.view)
        f.config.chmod(0o644)  # Actual CLI access failure clears the retained view.
        terminal_app.refresh()
        settled(terminal_app, lambda: not terminal_app.busy)
        assert not terminal_app.view.snapshot and "UNCONFIRMED" in terminal_app.view.notice
    finally:
        terminal_app.close()


def test_build_terminal_headless_refusal_never_prints_private_config_path():
    result = CliRunner().invoke(app, ["build", "tui", "--config", "/PRIVATE_SENTINEL", "not-a-goal"])
    assert result.exit_code == 2 and "PRIVATE_SENTINEL" not in result.output


def test_actual_canonical_plan_progress_is_visible_in_terminal_without_starting_or_merging(native_plan, prepared_plan):
    owner, runner, plan, state = native_plan
    f = prepared_plan[0]
    assert runner.run(plan.plan_id, public_subscription_run=True)["status"] == "WAITING_APPROVAL"
    progress = invoke(f, "progress", plan.goal_id)
    assert progress["required_checks_passed"] == progress["required_checks_total"] > 0
    assert progress["owner_merge"] == "PENDING" and progress["dispatch_authority"] == "NONE"
    launches = state["launches"]
    with terminal(f.config, entry=("build", "tui"), arguments=(plan.goal_id,)) as t:
        t.until(b"WAITING_APPROVAL")
        os.write(t.master, b"p")
        # One PTY read can contain both lines; waiting again from a new cursor
        # would incorrectly discard the already received attention line.
        t.until(b"release acceptance: NOT_ASSESSED")
        assert b"OWNER_MERGE_REVIEW_REQUIRED" in t.transcript
        assert f.dsn.encode() not in t.transcript
        assert git(f.bare, "rev-parse", "HEAD") == f.base
        os.write(t.master, b"q")
    assert state["launches"] == launches == 2
    assert owner.status(plan.goal_id)["task_state"] == "WAITING_APPROVAL"


def test_actual_goal_browser_scopes_public_list_and_opens_unstarted_plan(native_plan, prepared_plan):
    f, owner, _, plan = prepared_plan
    state = native_plan[3]
    # Real canonical metadata for two other scopes and a non-PUBLIC goal.
    # No execution, acceptance or successful evidence is synthesized for these rows.
    with owner.connect() as c:
        other_owner, other_project = str(uuid4()), str(uuid4())
        c.execute("INSERT INTO panestria.principal(id,display_name) VALUES (%s,'other owner')", (other_owner,))
        c.execute("INSERT INTO panestria.project(id,owner_id) VALUES (%s,%s)", (other_project, other_owner))
        same_owner_project = str(uuid4())
        c.execute(
            "INSERT INTO panestria.project(id,owner_id) VALUES (%s,%s)", (same_owner_project, owner.actor.owner_id)
        )
        for who, project, privacy in (
            (other_owner, other_project, "PUBLIC"),
            (owner.actor.owner_id, same_owner_project, "PUBLIC"),
            (owner.actor.owner_id, owner.actor.project_id, "RESTRICTED"),
        ):
            gid, cid = str(uuid4()), str(uuid4())
            c.execute(
                "INSERT INTO panestria.goal(id,owner_id,project_id,intent,status) "
                "VALUES (%s,%s,%s,'HIDDEN_GOAL_SENTINEL','CREATED')",
                (gid, who, project),
            )
            c.execute(
                "INSERT INTO panestria.goal_contract(id,goal_id,version,body,sha256) VALUES (%s,%s,1,%s::jsonb,%s)",
                (cid, gid, json.dumps({"privacy_class": privacy}), "ab" * 32),
            )
            c.execute(
                "INSERT INTO panestria.task(id,goal_id,contract_id,name,state) "
                "VALUES (%s,%s,%s,'Owner PUBLIC native Build','CREATED')",
                (str(uuid4()), gid, cid),
            )
        before = c.execute("SELECT count(*) FROM panestria.task_event").fetchone()
    index = invoke(f, "goals")
    assert index["authority"] == "READ_ONLY_METADATA"
    assert [g["goal_id"] for g in index["goals"]] == [plan.goal_id]
    assert index["goals"][0]["review_available"] is True
    assert index["goals"][0]["running_tasks"] == index["goals"][0]["waiting_reviews"] == 0
    assert "HIDDEN_GOAL_SENTINEL" not in json.dumps(index)
    with terminal(f.config, entry=("build", "tui")) as t:
        t.until(b"Latest 32 PUBLIC Builds")
        os.write(t.master, b"\r")
        t.until(b"Canonical task: CREATED")
        os.write(t.master, b"p")
        t.until(b"release acceptance: NOT_ASSESSED")
        assert b"VERIFIED BUILD PROGRESS" in t.transcript
        os.write(t.master, b"q")
        t.until(b"Returned from review")
        os.write(t.master, b"q")
        assert b"HIDDEN_GOAL_SENTINEL" not in t.transcript and f.dsn.encode() not in t.transcript
    assert state["launches"] == 0
    assert git(f.bare, "rev-parse", "HEAD") == f.base
    with owner.connect() as c:
        assert c.execute("SELECT count(*) FROM panestria.task_event").fetchone() == before
    assert owner.status(plan.goal_id)["task_state"] == "CREATED"
