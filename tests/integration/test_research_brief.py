"""Actual retained DB/CAS/isolated reader; fetch observations explicitly synthetic, no inference."""

import hashlib
import json
import stat
from html.parser import HTMLParser
from uuid import uuid4

import psycopg
import pytest
from pydantic import SecretStr
from test_research_requests import research  # noqa: F401 -- isolated DB fixture
from test_research_source_provenance import observations  # noqa: F401 -- actual isolated reader, SYNTHETIC fetch
from test_research_source_provenance import record as capture_source
from test_research_source_provenance import reference as source_reference
from typer.testing import CliRunner

from panestria.brokers.research.fetch import PublicHttpsFetcher
from panestria.brokers.research.reader import IsolatedTextReader
from panestria.brokers.research.search import LocalSearxngProvider
from panestria.cli.main import app
from panestria.cli.research import _write_private
from panestria.contracts.research import ClaimDraft, ResearchArtifactRef, ResearchRequestRecord
from panestria.contracts.research_brief import EvidenceBrief
from panestria.contracts.research_claims import ClaimEvidenceDraft, QuotedPassage
from panestria.execution.research_brief import RetainedBrief, brief_json
from panestria.execution.research_claims import ClaimStore
from panestria.execution.research_sources import SourceStore
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.research_blobs import ResearchBlobStore
from panestria.kernel.research_requests import ResearchRequestService
from panestria.kernel.uow import UnitOfWork

QUESTION = 'SYNTHETIC question: café 中文 <script>alert("question")</script>'
UNRELATED = 'SYNTHETIC unrelated assertion: moon is cheese. <img src="https://invalid/track">'


@pytest.fixture
def brief_context(research, observations, tmp_path):  # noqa: F811
    dsn, actor, old = research
    root = tmp_path / "retained"
    root.mkdir(mode=0o700)
    with ResearchBlobStore(root, actor) as blobs:
        receipt = blobs.put(QUESTION.encode())
    artifact_id = str(uuid4())
    request = ResearchRequestRecord(
        request_id=str(uuid4()),
        scope=old.scope,
        limits=old.limits,
        question=ResearchArtifactRef(
            artifact_id=artifact_id,
            task_id=old.scope.task_id,
            sha256=receipt.sha256,
            size_bytes=receipt.size_bytes,
            privacy_label="INTERNAL",
        ),
    )
    with psycopg.connect(dsn) as c:
        c.execute(
            "INSERT INTO panestria.artifact(id,task_id,kind,store_key,sha256,privacy_class,size_bytes) "
            "VALUES (%s,%s,'research.question',%s,%s,'INTERNAL',%s)",
            (artifact_id, old.scope.task_id, receipt.sha256, receipt.sha256, receipt.size_bytes),
        )
        ResearchRequestService().prepare(UnitOfWork(c), actor, request)
        source = capture_source(c, request, SourceStore(root, actor), observations)
    ref = source_reference(source, request, observations)
    return dsn, actor, request, root, ref, observations


def add_claim(context, *, ref=True, quote=True, text=UNRELATED):
    dsn, actor, request, root, reference, pair = context
    references = (reference,) if ref else ()
    quotes = (
        ()
        if quote is False or not ref
        else (
            QuotedPassage(
                reference=reference, quote=SecretStr(pair[1].text.get_secret_value() if quote is True else quote)
            ),
        )
    )
    draft = ClaimEvidenceDraft(claim=ClaimDraft(text=SecretStr(text), kind="FACT", passages=references), quotes=quotes)
    with psycopg.connect(dsn) as c:
        return ClaimStore(root, actor).record(
            UnitOfWork(c),
            request_id=request.request_id,
            task_id=request.scope.task_id,
            draft=draft,
            input_label="PUBLIC",
        )


def inspect(context):
    dsn, actor, request, root, *_ = context
    return RetainedBrief(root, actor).inspect(dsn, request.request_id, request.scope.task_id)


def test_connected_inspection_rechecks_citations_offline_and_never_promotes_unrelated_fact(brief_context, monkeypatch):
    dsn, _, request, _, _, _ = brief_context
    valid = add_claim(brief_context)
    bad_quote = add_claim(brief_context, quote="SYNTHETIC fabricated quote")
    uncited = add_claim(brief_context, ref=False)
    forged_context = (
        *brief_context[:4],
        brief_context[4].model_copy(update={"snapshot_id": str(uuid4())}),
        brief_context[5],
    )
    invented = add_claim(forged_context)
    with psycopg.connect(dsn) as c:
        before = c.execute("SELECT count(*),max(seq) FROM panestria.task_event").fetchone()
        state = c.execute(
            "SELECT state,row_version FROM panestria.task WHERE id=%s", (request.scope.task_id,)
        ).fetchone()

    def forbidden(*_args, **_kwargs):
        raise AssertionError("offline inspection cannot search, fetch or extract")

    monkeypatch.setattr(PublicHttpsFetcher, "fetch", forbidden)
    monkeypatch.setattr(LocalSearxngProvider, "search", forbidden)
    monkeypatch.setattr(IsolatedTextReader, "extract", forbidden)
    brief = inspect(brief_context)
    assert [claim.claim_id for claim in brief.claims] == [
        valid.claim_id,
        bad_quote.claim_id,
        uncited.claim_id,
        invented.claim_id,
    ]
    assert [claim.evidence_verdict for claim in brief.claims] == [
        "EVIDENCE_PRESENT",
        "INVALID_EVIDENCE",
        "NO_EVIDENCE",
        "INVALID_EVIDENCE",
    ]
    assert brief.claims[1].diagnostics == ("quote_mismatch",)
    assert brief.claims[3].diagnostics == ("source_unavailable",)
    assert all(not claim.citations for claim in brief.claims[1:])
    citation = brief.claims[0].citations[0]
    assert citation.quote == brief_context[5][1].text and citation.url.get_secret_value() == "https://example.org/"
    assert citation.reference == brief_context[4] and citation.quote_was_supplied
    assert citation.limitations == ("html-tokenizer-only", "html-layout-unverified")
    assert all(claim.support_status == "NOT_ASSESSED" for claim in brief.claims)
    assert brief.semantic_support == brief.contradictions == "NOT_ASSESSED"
    assert brief.task_completion_authority == "NONE" and brief.privacy_label == "RESTRICTED"
    assert QUESTION not in repr(brief) and UNRELATED not in repr(brief)
    exported = brief_json(brief)
    assert EvidenceBrief.model_validate_json(exported) == brief
    assert json.loads(exported)["question"] == QUESTION
    assert brief.claims[0].historical_report_sha256 == brief.claims[0].current_report_sha256
    with psycopg.connect(dsn) as c:
        assert c.execute("SELECT count(*),max(seq) FROM panestria.task_event").fetchone() == before
        assert (
            c.execute("SELECT state,row_version FROM panestria.task WHERE id=%s", (request.scope.task_id,)).fetchone()
            == state
        )


@pytest.mark.parametrize("role", ["source", "claim"])
def test_current_corruption_is_visible_without_historical_pass_or_url_leak(brief_context, role):
    dsn, actor, request, root, ref, _ = brief_context
    add_claim(brief_context)
    before = inspect(brief_context)
    assert before.claims[0].evidence_verdict == "EVIDENCE_PRESENT"
    with psycopg.connect(dsn) as c:
        if role == "source":
            digest = (
                SourceStore(root, actor)
                .records.read(
                    UnitOfWork(c), actor, ref.snapshot_id, request_id=request.request_id, task_id=request.scope.task_id
                )
                .evidence.snapshot.raw.sha256
            )
        else:
            digest = str(c.execute("SELECT payload_sha256 FROM panestria.research_claim").fetchone()[0]).strip()
    path = root / actor.owner_id / actor.project_id / digest
    path.chmod(0o600)
    path.write_bytes(b"SYNTHETIC corrupt retained bytes")
    path.chmod(0o400)
    after = inspect(brief_context)
    assert after.privacy_label == "RESTRICTED"
    assert after.claims[0].historical_report_sha256 == before.claims[0].historical_report_sha256
    if role == "source":
        assert after.claims[0].evidence_verdict == "INVALID_EVIDENCE"
        assert after.claims[0].current_report_sha256 != before.claims[0].current_report_sha256
        assert after.claims[0].diagnostics == ("source_unavailable",)
    else:
        assert after.claims[0].evidence_verdict == "UNAVAILABLE" and after.claims[0].text is None
    assert not after.claims[0].citations
    assert b"example.org" not in brief_json(after)


def test_scope_and_question_bytes_fail_closed_and_no_claims_do_not_complete_task(brief_context):
    dsn, actor, request, root, *_ = brief_context
    empty = inspect(brief_context)
    assert empty.claims == () and empty.task_completion_authority == "NONE" and empty.privacy_label == "INTERNAL"
    for other, req, task in (
        (Actor(str(uuid4()), actor.project_id), request.request_id, request.scope.task_id),
        (Actor(actor.owner_id, str(uuid4())), request.request_id, request.scope.task_id),
        (actor, str(uuid4()), request.scope.task_id),
        (actor, request.request_id, str(uuid4())),
    ):
        with pytest.raises(KernelDenied, match="not_found"):
            RetainedBrief(root, other).inspect(dsn, req, task)
    (root / actor.owner_id / actor.project_id / request.question.sha256).unlink()
    with pytest.raises(KernelDenied, match="research_brief_unavailable"):
        inspect(brief_context)


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.text.append(data)


def test_real_owner_cli_exports_escaped_inert_private_html_and_json(brief_context, tmp_path, monkeypatch):
    dsn, actor, request, root, *_ = brief_context
    add_claim(brief_context)
    output_root = tmp_path / "exports"
    output_root.mkdir(mode=0o700)
    monkeypatch.setenv("PANESTRIA_DATABASE_URL", dsn)
    base = [
        "research",
        "inspect",
        actor.owner_id,
        actor.project_id,
        request.request_id,
        request.scope.task_id,
        "--store",
        str(root),
    ]
    html = output_root / "evidence.html"
    result = CliRunner().invoke(app, [*base, "--output", str(html)])
    assert result.exit_code == 0, result.output
    metadata = json.loads(result.output)
    assert metadata["status"] == "EXPORTED" and metadata["semantic_support"] == "NOT_ASSESSED"
    assert QUESTION not in result.output and UNRELATED not in result.output and "example.org" not in result.output
    assert metadata["sha256"] == hashlib.sha256(html.read_bytes()).hexdigest()
    assert stat.S_IMODE(html.stat().st_mode) == 0o600
    parsed = Tags()
    parsed.feed(html.read_text())
    assert not ({t for t, _ in parsed.tags} & {"script", "img", "iframe", "a", "form", "link", "style"})
    assert QUESTION in parsed.text and UNRELATED in parsed.text
    assert any(attrs.get("http-equiv") == "Content-Security-Policy" for _, attrs in parsed.tags)
    assert b"NOT_ASSESSED" in html.read_bytes()
    protected = html.read_bytes()
    repeated = CliRunner().invoke(app, [*base, "--output", str(html)])
    assert repeated.exit_code == 1 and html.read_bytes() == protected
    json_path = output_root / "evidence.json"
    result = CliRunner().invoke(app, [*base, "--output", str(json_path), "--format", "json"])
    assert result.exit_code == 0
    assert EvidenceBrief.model_validate_json(json_path.read_bytes()) == inspect(brief_context).model_copy(
        update={"observed_at": EvidenceBrief.model_validate_json(json_path.read_bytes()).observed_at}
    )


def test_private_export_rejects_symlinks_public_parents_and_existing_files(tmp_path):
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    target = private / "preserve"
    target.write_bytes(b"owner bytes")
    link = private / "link"
    link.symlink_to(target)
    for path in (target, link):
        with pytest.raises(FileExistsError):
            _write_private(path, b"replacement")
    assert target.read_bytes() == b"owner bytes"
    public = tmp_path / "public"
    public.mkdir(mode=0o755)
    public.chmod(0o755)  # Explicit regardless of the caller's private umask.
    with pytest.raises(ValueError, match="private_output_directory_required"):
        _write_private(public / "output", b"bytes")
    assert not (public / "output").exists()
