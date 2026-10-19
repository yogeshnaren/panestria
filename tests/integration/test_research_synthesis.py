"""Real PG/CAS/isolated reader; synthetic fetch/model fixtures, never a G2 pass."""

import json
import stat
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from threading import Event
from uuid import UUID, uuid4

import psycopg
import pytest
from pydantic import SecretStr, ValidationError
from test_research_requests import research  # noqa: F401 -- disposable DB dependency
from test_research_source_provenance import observations  # noqa: F401 -- real reader, fixture-only fetch
from test_research_source_provenance import record as capture_source
from test_research_source_provenance import reference as source_reference
from typer.testing import CliRunner

from panestria.cli.main import app
from panestria.config_synthesis import SynthesisSettings
from panestria.contracts.inference import InferenceResult, InferenceUnavailable, Usage
from panestria.contracts.research import ClaimDraft, ResearchArtifactRef, ResearchRequestRecord
from panestria.contracts.research_claims import ClaimEvidenceDraft, QuotedPassage
from panestria.contracts.research_synthesis import RetainedSynthesis, synthesis_json
from panestria.execution.research_claims import ClaimStore
from panestria.execution.research_sources import SourceStore
from panestria.execution.research_synthesis import (
    FAILED,
    RETURNED,
    STARTED,
    LocalDraftModel,
    OwnerSynthesis,
    synthesis_html,
)
from panestria.inference.runtime import MODEL
from panestria.kernel.errors import KernelDenied
from panestria.kernel.policy import PolicyService
from panestria.kernel.research_blobs import ResearchBlobStore
from panestria.kernel.research_requests import ResearchRequestService
from panestria.kernel.uow import UnitOfWork
from panestria.policy.profiles import CertificateStore

QUESTION = "What does the retained passage say? <script>untrusted question</script>"
RESPONSE = {
    "claims": [
        {"text": 'Untrusted draft <img src="https://invalid/track">', "kind": "INTERPRETATION", "citations": ["p1"]}
    ]
}


@pytest.fixture
def synthesis_context(research, observations, tmp_path):  # noqa: F811
    dsn, actor, old = research
    root = tmp_path / "retained"
    root.mkdir(mode=0o700)
    with ResearchBlobStore(root, actor) as blobs:
        blob = blobs.put(QUESTION.encode())
    question = ResearchArtifactRef(
        artifact_id=str(uuid4()),
        task_id=old.scope.task_id,
        sha256=blob.sha256,
        size_bytes=blob.size_bytes,
        privacy_label="PUBLIC",
    )
    request = ResearchRequestRecord(request_id=str(uuid4()), scope=old.scope, limits=old.limits, question=question)
    with psycopg.connect(dsn) as c:
        PolicyService(CertificateStore(tmp_path / "certs", {})).initialize(UnitOfWork(c), actor, old.scope.task_id)
    with psycopg.connect(dsn) as c:
        c.execute(
            "INSERT INTO panestria.artifact(id,task_id,kind,store_key,sha256,privacy_class,size_bytes) "
            "VALUES(%s,%s,'research.question',%s,%s,'PUBLIC',%s)",
            (question.artifact_id, question.task_id, question.sha256, question.sha256, question.size_bytes),
        )
        ResearchRequestService().prepare(UnitOfWork(c), actor, request)
    with psycopg.connect(dsn) as c:
        source = capture_source(c, request, SourceStore(root, actor), observations)
    ref = source_reference(source, request, observations)
    with psycopg.connect(dsn) as c:
        ClaimStore(root, actor).record(
            UnitOfWork(c),
            request_id=request.request_id,
            task_id=old.scope.task_id,
            draft=ClaimEvidenceDraft(
                claim=ClaimDraft(text=SecretStr("Unassessed retained excerpt"), kind="INTERPRETATION", passages=(ref,)),
                quotes=(QuotedPassage(reference=ref, quote=observations[1].text),),
            ),
            input_label="PUBLIC",
        )
    with psycopg.connect(dsn) as c:
        # Fixture state, not production transition authority or gate evidence.
        c.execute(
            "UPDATE panestria.task SET state='VERIFYING',row_version=row_version+1 WHERE id=%s", (old.scope.task_id,)
        )
    cache = tmp_path / "cache"
    cache.mkdir(mode=0o700)
    (cache / "blobs").mkdir()
    (cache / "manifests").mkdir()
    settings = SynthesisSettings(
        schema_version=1,
        owner_id=UUID(actor.owner_id),
        project_id=UUID(actor.project_id),
        root=root,
        model_cache=cache,
        runtime_directory=tmp_path / "runtime",
    )
    return OwnerSynthesis(dsn, settings), request


@pytest.fixture
def model_fixture(monkeypatch):
    calls = []

    def generate(self, request):
        self.before_dispatch()
        calls.append(request)
        return InferenceResult(MODEL, json.dumps(RESPONSE), Usage(123, 42, 0), 0.2, 0.1)

    monkeypatch.setattr(LocalDraftModel, "generate", generate)
    return calls


def test_cli_retains_cited_draft_replays_without_inference_and_keeps_verification_open(
    synthesis_context,
    model_fixture,
    monkeypatch,
):
    service, request = synthesis_context
    monkeypatch.setenv("PANESTRIA_DATABASE_URL", service.dsn)
    config = service.settings.root / "synthesis.json"
    config.write_text(service.settings.model_dump_json())
    config.chmod(0o600)
    output = service.settings.root / "draft.json"
    args = [
        "research",
        "synthesize",
        request.request_id,
        "--config",
        str(config),
        "--key",
        "test",
        "--retain-local-draft",
        "--output",
        str(output),
        "--format",
        "json",
    ]
    runner = CliRunner()
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["status"] == "DRAFT_EXPORTED"
    assert QUESTION not in result.output and "example.org" not in result.output and service.dsn not in result.output
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    draft = RetainedSynthesis.model_validate_json(output.read_bytes())
    assert synthesis_json(draft) == output.read_bytes()
    assert draft.semantic_support == draft.contradictions == "NOT_ASSESSED"
    assert draft.task_completion_authority == "NONE"
    assert draft.response.claims[0].citations == ("p1",)
    passage = draft.packet.passages[0]
    assert (
        passage.quote.get_secret_value().encode()
        == (
            service.settings.root / service.actor.owner_id / service.actor.project_id / passage.reference.text_sha256
        ).read_bytes()[passage.reference.start : passage.reference.end]
    )
    assert draft.packet.policy_ref.startswith("project-policy:1:")
    assert model_fixture[0].offline and model_fixture[0].max_output_tokens == 768
    assert passage.url.get_secret_value() not in model_fixture[0].prompt
    assert "Ignore instructions" in model_fixture[0].prompt  # Retained untrusted text, not new authority.
    assert service.synthesize(request.request_id, "test", retain_local_draft=True).replayed
    with pytest.raises(KernelDenied, match="synthesis_already_started"):
        service.synthesize(request.request_id, "new-key", retain_local_draft=True)
    # Reinspection needs no model bytes; it still revalidates every retained citation.
    (service.settings.model_cache / "blobs").rmdir()
    (service.settings.model_cache / "manifests").rmdir()
    service.settings.model_cache.rmdir()
    inspected = runner.invoke(
        app,
        [
            "research",
            "inspect-draft",
            request.request_id,
            "--config",
            str(config),
            "--output",
            str(service.settings.root / "draft.html"),
        ],
    )
    assert inspected.exit_code == 0, inspected.output
    assert len(model_fixture) == 1

    class Tags(HTMLParser):
        names = []

        def handle_starttag(self, tag, attrs):
            self.names.append(tag)

    parser = Tags()
    html = synthesis_html(draft).decode()
    parser.feed(html)
    assert "script" not in parser.names and "img" not in parser.names and "a" not in parser.names
    assert "default-src &#39;none&#39;" in html and "NOT_ASSESSED" in html
    with psycopg.connect(service.dsn) as c:
        assert c.execute("SELECT state FROM panestria.task WHERE id=%s", (request.scope.task_id,)).fetchone() == (
            "VERIFYING",
        )
        assert c.execute("SELECT status FROM panestria.goal WHERE id=%s", (request.scope.goal_id,)).fetchone() == (
            "ACTIVE",
        )
        events = c.execute(
            "SELECT kind,payload FROM panestria.task_event WHERE kind LIKE 'research.synthesis.%' ORDER BY seq"
        ).fetchall()
        assert [r[0] for r in events] == [STARTED, RETURNED]
        assert QUESTION not in json.dumps(events) and "example.org" not in json.dumps(events)


@pytest.mark.parametrize("failure", ["citation", "extra", "partial", "usage", "cancel", "version"])
def test_bad_or_stale_outputs_fail_closed_and_never_redispatch(synthesis_context, monkeypatch, failure):
    service, request = synthesis_context
    calls = []

    def generate(self, inferred):
        self.before_dispatch()
        calls.append(inferred)
        body = json.loads(json.dumps(RESPONSE))
        if failure == "citation":
            body["claims"][0]["citations"] = ["p9"]
        if failure == "extra":
            body["completed"] = True
        if failure in {"cancel", "version"}:
            with psycopg.connect(service.dsn) as c:
                if failure == "cancel":
                    c.execute(
                        "UPDATE panestria.task SET state='CANCELLED',row_version=row_version+1 WHERE id=%s",
                        (request.scope.task_id,),
                    )
                else:
                    # A task version change also fences publication (e.g. intervening owner review).
                    c.execute(
                        "UPDATE panestria.task SET row_version=row_version+1 WHERE id=%s", (request.scope.task_id,)
                    )
        return InferenceResult(
            MODEL,
            json.dumps(body),
            Usage(None if failure == "usage" else 123, 42),
            0.2,
            0.1,
            finish_reason="length" if failure == "partial" else "stop",
        )

    monkeypatch.setattr(LocalDraftModel, "generate", generate)
    with pytest.raises((KernelDenied, ValidationError, InferenceUnavailable)):
        service.synthesize(request.request_id, "test", retain_local_draft=True)
    if failure != "cancel":
        assert service.synthesize(request.request_id, "test", retain_local_draft=True).status == "FAILED"
    assert len(calls) == 1
    with psycopg.connect(service.dsn) as c:
        assert c.execute(
            "SELECT kind FROM panestria.task_event WHERE kind LIKE 'research.synthesis.%' ORDER BY seq"
        ).fetchall() == [(STARTED,), (FAILED,)]
        assert c.execute(
            "SELECT count(*) FROM panestria.artifact WHERE kind='research.synthesis-output'"
        ).fetchone() == (0,)


def test_concurrent_and_unknown_intents_never_replay_inference(synthesis_context, monkeypatch):
    service, request = synthesis_context
    started, release = Event(), Event()
    calls = []

    def generate(self, inferred):
        self.before_dispatch()
        calls.append(inferred)
        started.set()
        assert release.wait(15)
        return InferenceResult(MODEL, json.dumps(RESPONSE), Usage(123, 42), 0.2, 0.1)

    monkeypatch.setattr(LocalDraftModel, "generate", generate)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(service.synthesize, request.request_id, "same", retain_local_draft=True)
        try:
            assert started.wait(15)
            second = service.synthesize(request.request_id, "same", retain_local_draft=True)
            assert second.status == "UNCONFIRMED" and second.replayed
        finally:
            release.set()
        assert first.result().status == "DRAFT_RETAINED"
    assert len(calls) == 1


def test_source_loss_blocks_initial_inference_and_reinspection(synthesis_context, model_fixture):
    service, request = synthesis_context
    receipt = service.synthesize(request.request_id, "test", retain_local_draft=True)
    draft = service.inspect(request.request_id)
    path = (
        service.settings.root
        / service.actor.owner_id
        / service.actor.project_id
        / draft.packet.passages[0].reference.text_sha256
    )
    path.chmod(0o600)
    path.write_bytes(b"synthetic corruption")
    path.chmod(0o400)
    for action in (
        lambda: service.inspect(request.request_id),
        lambda: service.synthesize(request.request_id, "test", retain_local_draft=True),
    ):
        with pytest.raises(KernelDenied):
            action()
    assert len(model_fixture) == 1 and receipt.status == "DRAFT_RETAINED"


def test_explicit_intent_and_new_private_output_are_required_before_model(
    synthesis_context, model_fixture, monkeypatch
):
    service, request = synthesis_context
    with pytest.raises(KernelDenied, match="explicit_retained_local_draft_required"):
        service.synthesize(request.request_id, "test", retain_local_draft=False)
    config = service.settings.root / "synthesis.json"
    config.write_text(service.settings.model_dump_json())
    config.chmod(0o600)
    output = service.settings.root / "existing.html"
    output.write_bytes(b"preserved")
    monkeypatch.setenv("PANESTRIA_DATABASE_URL", service.dsn)
    result = CliRunner().invoke(
        app,
        [
            "research",
            "synthesize",
            request.request_id,
            "--config",
            str(config),
            "--key",
            "test",
            "--retain-local-draft",
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 1 and not model_fixture and output.read_bytes() == b"preserved"
    with psycopg.connect(service.dsn) as c:
        assert c.execute("SELECT count(*) FROM panestria.task_event WHERE kind=%s", (STARTED,)).fetchone() == (0,)
