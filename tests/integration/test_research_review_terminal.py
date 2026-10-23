"""Actual PG/CAS/PTY owner review; retained synthesis uses an explicit model fixture."""

# ruff: noqa: F811 -- pytest injects imported fixtures by name

import curses
import hashlib
import json
import os

import psycopg
import pytest
from pydantic import SecretStr
from test_ask_tui import terminal
from test_research_requests import research  # noqa: F401 -- fixture dependency
from test_research_source_provenance import observations  # noqa: F401 -- actual reader/source fixture
from test_research_synthesis import RESPONSE, model_fixture, synthesis_context  # noqa: F401 -- model fixture explicit
from typer.testing import CliRunner

from panestria.cli.main import app
from panestria.cli.research_review_terminal import ResearchReviewTerminal
from panestria.contracts.research_review import review_json
from panestria.execution.research_review import RECORDED, OwnerResearchReview


@pytest.fixture(autouse=True)
def evidence_scope(record_property):
    record_property("scope", "Actual PG/CAS/reader/PTY; SYNTHETIC fetch/model retained draft; no release proof")


def review_count(service, request):
    with psycopg.connect(service.dsn) as c:
        return c.execute(
            "SELECT count(*) FROM panestria.task_event WHERE task_id=%s AND kind=%s",
            (request.scope.task_id, RECORDED),
        ).fetchone()[0]


@pytest.mark.parametrize("decision", ["record", "cancel_before_confirm"])
def test_keyboard_exact_sources_rationale_confirmation_and_fresh_canonical_fence(
    synthesis_context, model_fixture, monkeypatch, decision
):
    synthesis, request = synthesis_context
    body = [
        {
            "text": "Untrusted draft control \x1b]52;c;UNTRUSTED_CLIPBOARD\x07 \u202e literal",
            "kind": "INTERPRETATION",
            "citations": ["p1"],
        }
    ]
    monkeypatch.setitem(RESPONSE, "claims", body)
    synthesis.synthesize(request.request_id, "terminal-review", retain_local_draft=True)
    service = OwnerResearchReview(synthesis.dsn, synthesis.settings)
    config = service.settings.root / "terminal.json"
    config.write_text(service.settings.model_dump_json())
    config.chmod(0o600)
    monkeypatch.setenv("PANESTRIA_DATABASE_URL", service.dsn)
    # Refuse redirected/noninteractive invocation without a write or model startup.
    no_tty = CliRunner().invoke(app, ["research", "review-draft", request.request_id, "--config", str(config)])
    assert no_tty.exit_code == 1 and review_count(service, request) == 0
    with terminal(config, entry=("research", "review-draft"), arguments=(request.request_id,)) as t:
        t.until(b"RESEARCH CLAIM REVIEW")
        os.write(t.master, b"vy")
        t.until(b"Read to the end first")
        assert review_count(service, request) == 0
        os.write(t.master, b"s1ePRIVATE_OWNER_RATIONALE\r")
        t.until(b"Rationale changed locally")
        curses.setupterm(term="xterm-256color")
        scroll_start = len(t.transcript)
        os.write(t.master, curses.tigetstr("knp") * 12)
        t.until(b"END OF EXACT DRAFT AND OWNER JUDGMENTS", after=scroll_start)
        assert b"\x1b]52" not in t.transcript and "\u202e".encode() not in t.transcript
        assert service.dsn.encode() not in t.transcript
        os.write(t.master, b"v")
        t.until(b"CONFIRM EXACT OWNER JUDGMENTS")
        assert review_count(service, request) == 0
        if decision == "cancel_before_confirm":
            with psycopg.connect(service.dsn) as c:
                c.execute(
                    "UPDATE panestria.task SET state='CANCELLING',row_version=row_version+1 WHERE id=%s",
                    (request.scope.task_id,),
                )
        os.write(t.master, b"y")
        t.until(b"OWNER REVIEW RECORDED" if decision == "record" else b"REVIEW UNCONFIRMED")
        os.write(t.master, b"yyvysq")  # No repeated decision or local editing after the one attempted write.
    assert len(model_fixture) == 1
    assert review_count(service, request) == (1 if decision == "record" else 0)
    if decision == "record":
        review = service.inspect_review(request.request_id)
        assert review.claims[0].verdict == "SUPPORTED" and review.claims[0].citations == ("p1",)
        assert review.claims[0].rationale.get_secret_value() == "PRIVATE_OWNER_RATIONALE"
        with psycopg.connect(service.dsn) as c:
            event = c.execute("SELECT payload FROM panestria.task_event WHERE kind=%s", (RECORDED,)).fetchone()[0]
            assert "PRIVATE_OWNER_RATIONALE" not in json.dumps(event)
            assert event["assessment_source"] == "OWNER_REPORTED" and event["task_completion_authority"] == "NONE"
            assert c.execute("SELECT state FROM panestria.task WHERE id=%s", (request.scope.task_id,)).fetchone() == (
                "VERIFYING",
            )


def test_real_commit_then_lost_review_reply_never_repeats_confirmation(synthesis_context, model_fixture, monkeypatch):
    synthesis, request = synthesis_context
    synthesis.synthesize(request.request_id, "uncertain-review", retain_local_draft=True)
    service = OwnerResearchReview(synthesis.dsn, synthesis.settings)
    view = ResearchReviewTerminal(service, service.inspect(request.request_id))
    view.change(verdict="INSUFFICIENT", rationale=SecretStr("Synthetic exact owner uncertainty"))
    view.end = True
    view.key("v", 16)
    assert view.pending is not None and view.digest == hashlib.sha256(review_json(view.review)).hexdigest()
    record = service.record_review
    attempts = []

    def lost_reply(*args, **kwargs):
        result = record(*args, **kwargs)  # Actual committed immutable CAS/artifact/event.
        attempts.append(result)
        raise OSError("SYNTHETIC_LOST_REPLY_AFTER_COMMIT")

    monkeypatch.setattr(service, "record_review", lost_reply)
    view.key("y", 16)
    assert "UNCONFIRMED" in view.notice and view.pending is None and view.digest is None
    for key in ("y", "v", "s", "y"):
        view.key(key, 16)
    assert len(attempts) == review_count(service, request) == 1
    assert service.inspect_review(request.request_id).claims[0].verdict == "INSUFFICIENT"
    assert len(model_fixture) == 1
