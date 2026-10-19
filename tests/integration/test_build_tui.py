"""Real PTY/owner CLI/Postgres/Git; only native generation/certificates are fixtures."""

import curses
import os
import time

from test_ask_tui import terminal
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
        t.until(b"UNCONFIRMED", timeout=10)
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
