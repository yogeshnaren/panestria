"""Real canonical PG/HTTP/reader/CAS/terminal; labeled model/HTTPS/certificate fixtures."""

# ruff: noqa: F811 -- imported pytest fixture dependencies

import curses
import json
import os
from uuid import UUID, uuid4

import pytest
from test_ask_tui import terminal
from test_configured_search import search_server  # noqa: F401
from test_fetch_admission import synthetic_https  # noqa: F401
from test_owner_research_collection import JOINT, QUERY, owner_question, stage  # noqa: F401
from test_search_admission import admitted_search  # noqa: F401
from typer.testing import CliRunner

from panestria.cli.main import app
from panestria.cli.research_guide_terminal import ResearchGuideTerminal
from panestria.config_synthesis import SynthesisSettings
from panestria.contracts.inference import InferenceResult, Usage
from panestria.contracts.research import ResearchLimits
from panestria.execution.research_guide import OwnerResearchGuide
from panestria.execution.research_query_plan import STARTED
from panestria.execution.research_synthesis import LocalDraftModel
from panestria.inference.runtime import MODEL
from panestria.kernel.errors import KernelDenied


@pytest.fixture
def guided(owner_question, tmp_path, monkeypatch, record_property):
    q = owner_question
    receipt = stage(q, limits=ResearchLimits(max_sources=1))
    cache = tmp_path / "guide-cache"
    cache.mkdir(mode=0o700)
    (cache / "blobs").mkdir()
    (cache / "manifests").mkdir()
    settings = SynthesisSettings(
        schema_version=1, owner_id=UUID(q.f.actor.owner_id), project_id=UUID(q.f.actor.project_id),
        root=q.root, model_cache=cache, runtime_directory=tmp_path / "guide-model-runtime",
    )
    config = q.root / "guide.json"
    config.write_text(settings.model_dump_json())
    config.chmod(0o600)
    monkeypatch.setenv("PANESTRIA_DATABASE_URL", q.f.dsn)
    calls = []

    def generate(self, request):
        self.before_dispatch()
        calls.append(request)
        body = {"queries": [QUERY]} if request.max_output_tokens == 512 else {
            "claims": [{"text": "Synthetic unverified claim", "kind": "INTERPRETATION", "citations": ["p1"]}]
        }
        return InferenceResult(MODEL, json.dumps(body), Usage(123, 42, 0), 0.2, 0.1)

    monkeypatch.setattr(LocalDraftModel, "generate", generate)
    record_property("scope", "Actual PG/HTTP/reader/CAS/PTY; SYNTHETIC model, HTTPS and certificates; no release proof")
    return q, receipt, config, OwnerResearchGuide(q.f.dsn, settings, q.settings), calls


def confirm(view):
    view.end = True
    assert view.key("v", 16) and view.pending
    view.key("y", 16)


@pytest.mark.parametrize("admitted_search", [JOINT], indirect=True)
def test_same_request_guided_plan_disclosure_collection_draft_and_separate_review(guided):
    q, receipt, _, service, calls = guided
    view = ResearchGuideTerminal(service, receipt.request_id)
    assert view.step.action == "PLAN" and not calls and not q.f.server["requests"]
    view.key("v", 16)
    view.key("y", 16)
    assert not calls and not view.pending  # Scrolling is required before consent.
    confirm(view)
    assert view.step.action == "COLLECT" and len(calls) == 1 and not q.f.server["requests"]
    assert QUERY in "\n".join(view.step.lines) and "may forward" in "\n".join(view.step.lines)
    confirm(view)
    assert view.step.action == "DRAFT" and len(calls) == 1
    assert len(q.f.server["requests"]) == len(q.calls) == 1
    assert b"PUBLIC+synthetic+question" in q.f.server["requests"][0][2]
    assert "Exact model passage" in "\n".join(view.step.lines)
    confirm(view)
    assert view.step.action == "REVIEW" and len(calls) == 2
    assert calls[0].offline and calls[1].offline and all(c.label == "PUBLIC" for c in calls)
    # Reopening reads retained state without repeating any prior model/search/fetch.
    reopened = ResearchGuideTerminal(service, receipt.request_id)
    assert reopened.step.action == "REVIEW"
    confirm(reopened)
    assert reopened.open_review and len(calls) == 2 and len(q.calls) == 1
    draft = service.review.inspect(receipt.request_id)
    assert draft.semantic_support == "NOT_ASSESSED" and draft.task_completion_authority == "NONE"
    with service.review.connect() as c:
        assert c.execute("SELECT count(*) FROM panestria.research_request WHERE project_id=%s",
                         (q.f.actor.project_id,)).fetchone() == (1,)
        assert c.execute("SELECT state,lease_epoch FROM panestria.task WHERE id=%s",
                         (receipt.task_id,)).fetchone() == ("VERIFYING", 2)
        assert c.execute("SELECT count(*) FROM panestria.check_run WHERE task_id=%s",
                         (receipt.task_id,)).fetchone() == (0,)
    assert not service.review.settings.runtime_directory.exists()  # Model fixture, no hidden local/provider call.


@pytest.mark.parametrize("admitted_search", [JOINT], indirect=True)
@pytest.mark.parametrize("phase", ["PLAN", "COLLECT", "DRAFT"])
def test_locked_stage_rejects_changed_review_before_any_new_effect(guided, phase):
    q, receipt, _, service, calls = guided
    while service.prepare(receipt.request_id).action != phase:
        service.execute(receipt.request_id, service.prepare(receipt.request_id))
    reviewed = service.prepare(receipt.request_id)
    before = (len(calls), len(q.f.server["requests"]), len(q.calls))
    # Simulate a change after the outer guide review, before the original service's
    # lock/dispatch. Direct stage calls exercise the inner guard, not just the UI.
    with service.review.connect() as c:
        c.execute("UPDATE panestria.task SET row_version=row_version+1 WHERE id=%s", (receipt.task_id,))
    with pytest.raises(KernelDenied, match="review_changed"):
        if phase == "PLAN":
            service.planner.plan(receipt.request_id, "stale", retain_local_plan=True,
                                 expected_input_sha256=reviewed.input_sha256)
        elif phase == "COLLECT":
            service.collection.collect(receipt.request_id, reviewed.queries, public_web=True,
                                       expected_review_sha256=reviewed.input_sha256)
        else:
            service.review.synthesize(receipt.request_id, "stale", retain_local_draft=True,
                                      expected_input_sha256=reviewed.input_sha256)
    assert before == (len(calls), len(q.f.server["requests"]), len(q.calls))
    with pytest.raises(KernelDenied, match="research_guide_review_changed"):
        service.execute(receipt.request_id, reviewed)


@pytest.mark.parametrize("admitted_search", [JOINT], indirect=True)
def test_committed_plan_lost_reply_stops_same_view_and_resume_reads_original_receipt(guided, monkeypatch):
    q, receipt, _, service, calls = guided
    view = ResearchGuideTerminal(service, receipt.request_id)
    original = service.planner.plan

    def lost(*args, **kwargs):
        original(*args, **kwargs)  # Actual committed input/output/event.
        raise OSError("SYNTHETIC_LOST_REPLY_AFTER_PLAN_COMMIT")

    monkeypatch.setattr(service.planner, "plan", lost)
    confirm(view)
    assert view.stopped and "unconfirmed" in view.notice
    for key in ("v", "y", "v", "y"):
        view.key(key, 16)
    assert len(calls) == 1 and not q.calls and not q.f.server["requests"]
    assert ResearchGuideTerminal(service, receipt.request_id).step.action == "COLLECT"
    with service.review.connect() as c:
        assert c.execute("SELECT count(*) FROM panestria.task_event WHERE task_id=%s AND kind=%s",
                         (receipt.task_id, STARTED)).fetchone() == (1,)


@pytest.mark.parametrize("admitted_search", [JOINT], indirect=True)
def test_setup_scope_missing_collection_and_cancelled_request_never_infer_or_grant(guided):
    q, receipt, _, service, calls = guided
    with pytest.raises(KernelDenied, match="configuration_scope_mismatch"):
        OwnerResearchGuide(q.f.dsn, service.review.settings, q.settings.model_copy(update={"owner_id": uuid4()}))
    service.execute(receipt.request_id, service.prepare(receipt.request_id))
    no_search = OwnerResearchGuide(q.f.dsn, service.review.settings)
    stopped = no_search.prepare(receipt.request_id)
    assert stopped.action == "STOP" and QUERY in "\n".join(stopped.lines)
    old = service.prepare(receipt.request_id)
    with service.review.connect() as c:
        c.execute("UPDATE panestria.task SET state='CANCELLED',row_version=row_version+1 WHERE id=%s",
                  (receipt.task_id,))
    with pytest.raises(KernelDenied, match="review_changed"):
        service.execute(receipt.request_id, old)
    assert service.prepare(receipt.request_id).action == "STOP"
    assert len(calls) == 1 and not q.calls and not q.f.server["requests"]


@pytest.mark.parametrize("admitted_search", [JOINT], indirect=True)
def test_real_cli_pty_exact_query_preview_cancel_confirmation_and_terminal_restoration(guided):
    q, receipt, config, service, calls = guided
    service.execute(receipt.request_id, service.prepare(receipt.request_id))
    collection = q.root / "collection.json"
    collection.write_text(q.settings.model_dump_json())
    collection.chmod(0o600)
    args = (receipt.request_id, "--collection-config", str(collection))
    redirected = CliRunner().invoke(app, ["research", "guide", "--config", str(config), *args])
    assert redirected.exit_code == 1 and not q.calls and len(calls) == 1
    with terminal(config, entry=("research", "guide"), arguments=args) as t:
        t.until(b"GUIDED RESEARCH")
        os.write(t.master, b"vy")
        t.until(b"No action attempted")  # Curses can retain the unchanged leading words from the prior notice.
        curses.setupterm(term="xterm-256color")
        start = len(t.transcript)
        os.write(t.master, curses.tigetstr("knp") * 30)
        t.until(b"END OF EXACT STAGE REVIEW", after=start)
        os.write(t.master, b"v")
        t.until(b"CONFIRM COLLECT")
        assert service.prepare(receipt.request_id).digest.encode() in t.transcript
        os.write(t.master, b"\x1b")
        t.until(b"Confirmation cancelled")
        os.write(t.master, b"q")
    assert len(calls) == 1 and not q.calls and not q.f.server["requests"]
    assert q.f.dsn.encode() not in t.transcript
