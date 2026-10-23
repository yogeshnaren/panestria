"""Owner journey: real disposable PG/HTTP/CAS/reader; fixture-only HTTPS/certificate."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from pydantic import SecretStr
from test_configured_search import search_server  # noqa: F401 -- fixture dependency
from test_fetch_admission import synthetic_https  # noqa: F401 -- fixture-only HTTPS
from test_search_admission import admitted_search  # noqa: F401 -- fixture dependency
from typer.testing import CliRunner

from panestria.cli.main import app
from panestria.config_research import ResearchSettings
from panestria.contracts.research import ResearchLimits
from panestria.execution.research_brief import RetainedBrief, brief_html
from panestria.execution.research_collection import OwnerCollection
from panestria.execution.research_submission import stage_question
from panestria.kernel.cancellation import CancellationService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.search import SearchAdmissionService
from panestria.kernel.uow import UnitOfWork

JOINT = {"combined_runtime": True, "budget": {"max_wall_seconds": 120}}
QUESTION = "PUBLIC staged question, distinct from selected query: café 中文 <script>never execute</script>"
QUERY = "PUBLIC synthetic question"


@pytest.fixture(autouse=True)
def scope(record_property):
    record_property(
        "scope", "Actual PG/loopback HTTP/reader/CAS/CLI; SYNTHETIC HTTPS and TEST_FIXTURE_NOT_LIVE certificates"
    )


@pytest.fixture
def owner_question(synthetic_https):  # noqa: F811
    f, calls, _ = synthetic_https
    root = f.root / "owner-collection-cas"
    root.mkdir(mode=0o700)
    settings = ResearchSettings.model_validate_json(
        json.dumps(
            {
                "schema_version": 1,
                "owner_id": f.actor.owner_id,
                "project_id": f.actor.project_id,
                "root": str(root),
                "certificates": str(f.reports.root),
                "certificate_sha256": f.policy.trust.runtime_certificate_sha256,
                "search": f.settings.model_dump(mode="json"),
                "fetch_connection": getattr(f.plan, "connection", None).model_dump(mode="json")
                if getattr(f.plan, "connection", None) is not None
                else None,
            }
        )
    )
    with psycopg.connect(f.dsn) as c:
        document = c.execute(
            "SELECT body FROM panestria.goal_contract WHERE goal_id=%s", (f.plan.scope.goal_id,)
        ).fetchone()[0]
    document = {**document, "goal_id": str(uuid4()), "intent": "Owner PUBLIC synthetic collection"}
    return SimpleNamespace(f=f, calls=calls, root=root, settings=settings, document=document)


def stage(q, *, limits=None, document=None):
    return stage_question(
        q.f.dsn,
        q.f.actor,
        q.root,
        document or q.document,
        SecretStr(QUESTION),
        limits or ResearchLimits(),
        "synthetic-owner-collection",
        public_question=True,
    )


def inspect(q, receipt):
    return RetainedBrief(q.root, q.f.actor).inspect(q.f.dsn, receipt.request_id, receipt.task_id)


def task(q, receipt):
    with psycopg.connect(q.f.dsn) as c:
        return c.execute("SELECT state FROM panestria.task WHERE id=%s", (receipt.task_id,)).fetchone()[0]


def collected(q, receipt, *, queries=(QUERY,)):
    return OwnerCollection(q.f.dsn, q.settings).collect(
        receipt.request_id, tuple(SecretStr(query) for query in queries), public_web=True
    )


@pytest.mark.parametrize("admitted_search", [JOINT], indirect=True)
def test_actual_owner_cli_stage_collect_private_export_and_verify_wait(owner_question, monkeypatch):
    q = owner_question
    monkeypatch.setenv("PANESTRIA_DATABASE_URL", q.f.dsn)
    for name, raw in (
        ("settings.json", q.settings.model_dump_json()),
        ("contract.json", json.dumps(q.document)),
        ("question.txt", QUESTION),
        ("limits.json", '{"max_sources":1}'),
        ("queries.json", json.dumps([QUERY, "second PUBLIC query must not send after capacity stop"])),
    ):
        (q.root / name).write_text(raw)
        (q.root / name).chmod(0o600)
    runner = CliRunner()
    staged = runner.invoke(
        app,
        [
            "research",
            "stage",
            q.f.actor.owner_id,
            q.f.actor.project_id,
            "--contract",
            str(q.root / "contract.json"),
            "--question",
            str(q.root / "question.txt"),
            "--limits",
            str(q.root / "limits.json"),
            "--store",
            str(q.root),
            "--key",
            "synthetic-owner-cli",
            "--public-question",
        ],
    )
    assert staged.exit_code == 0, staged.output
    receipt = SimpleNamespace(**json.loads(staged.output))
    args = [
        "research",
        "collect",
        receipt.request_id,
        "--config",
        str(q.root / "settings.json"),
        "--queries",
        str(q.root / "queries.json"),
        "--output",
        str(q.root / "brief.html"),
        "--public-web",
    ]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["status"] == "COLLECTION_STOPPED_AWAITING_SYNTHESIS_AND_SUPPORT"
    assert QUESTION not in result.output and "example.org" not in result.output and q.f.dsn not in result.output
    brief = inspect(q, receipt)
    assert brief.task_state == "VERIFYING" and brief.goal_status == "ACTIVE"
    assert brief.semantic_support == "NOT_ASSESSED" and brief.task_completion_authority == "NONE"
    assert len(brief.claims) == 1 and brief.claims[0].evidence_verdict == "EVIDENCE_PRESENT"
    assert (
        brief.claims[0].kind == "INTERPRETATION" and "not an assessed answer" in brief.claims[0].text.get_secret_value()
    )
    citation = brief.claims[0].citations[0]
    ref = citation.reference
    retained_text = (q.root / q.f.actor.owner_id / q.f.actor.project_id / ref.text_sha256).read_bytes()
    assert citation.quote.get_secret_value().encode() == retained_text[ref.start : ref.end]
    assert b"PUBLIC SYNTHETIC source text" in retained_text
    assert brief.collection.stop_reason == "source_limit"
    assert brief.collection.latest_attempt_status == "SUCCEEDED"
    assert brief.collection.searches[0].status == "RETURNED" and brief.collection.fetches[0].status == "RETAINED"
    output = (q.root / "brief.html").read_text()
    assert "&lt;script&gt;never execute&lt;/script&gt;" in output and "<script>" not in output
    assert "Retained source excerpt" in output and "Collection observations" in output
    assert (q.root / "brief.html").stat().st_mode & 0o777 == 0o600
    with psycopg.connect(q.f.dsn) as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.check_run WHERE task_id=%s", (receipt.task_id,)
        ).fetchone() == (0,)
        assert c.execute(
            "SELECT adapter,status FROM panestria.task_attempt WHERE task_id=%s", (receipt.task_id,)
        ).fetchone() == ("public-research-collection", "SUCCEEDED")
        events = c.execute("SELECT payload FROM panestria.task_event WHERE task_id=%s", (receipt.task_id,)).fetchall()
        assert QUESTION not in json.dumps(events) and "example.org" not in json.dumps(events)
    # Selected query only; the entire question is never automatically exported.
    assert b"PUBLIC+synthetic+question" in q.f.server["requests"][0][2]
    assert QUESTION.encode() not in q.f.server["requests"][0][2]
    assert len(q.f.server["requests"]) == len(q.calls) == 1
    assert runner.invoke(app, args).exit_code == 1  # Existing output refused before dispatch.
    with pytest.raises(KernelDenied):
        collected(q, receipt)
    assert len(q.f.server["requests"]) == len(q.calls) == 1


@pytest.mark.parametrize("admitted_search", [JOINT], indirect=True)
def test_truncated_transfer_consumes_capacity_and_owner_sees_error_without_supported_claim(owner_question):
    q = owner_question
    q.f.server["body"] = json.dumps(
        {"query": QUERY, "results": [{"url": "https://example.org/a"}, {"url": "https://example.org/b"}]}
    ).encode()
    receipt = stage(q, limits=ResearchLimits(max_sources=2, max_source_bytes=64, max_total_bytes=65))
    result = collected(q, receipt)
    assert result.stop_reason == "body_limit" and task(q, receipt) == "VERIFYING"
    brief = inspect(q, receipt)
    assert not brief.claims and brief.collection.fetches[0].diagnostic == "fetch_size_limit"
    assert brief.collection.fetches[0].reserved_body_bytes == 65 and len(q.calls) == 1
    assert b"fetch_size_limit" in brief_html(brief) and brief.semantic_support == "NOT_ASSESSED"


@pytest.mark.parametrize("admitted_search", [JOINT], indirect=True)
def test_unavailable_search_stops_after_one_request_without_provider_retry_or_fallback(owner_question):
    q = owner_question
    q.f.server["status"] = 429
    receipt = stage(q)
    assert collected(q, receipt, queries=(QUERY, "second PUBLIC query")).stop_reason == "search_unavailable"
    brief = inspect(q, receipt)
    assert len(brief.collection.searches) == 1 and brief.collection.searches[0].status == "UNAVAILABLE"
    assert not brief.collection.fetches and not q.calls and len(q.f.server["requests"]) == 1


@pytest.mark.parametrize("admitted_search", [JOINT], indirect=True)
def test_scope_intent_query_configuration_policy_and_question_bytes_denied_before_activation(owner_question):
    q = owner_question
    receipt = stage(q)
    owner = OwnerCollection(q.f.dsn, q.settings)
    with pytest.raises(KernelDenied, match="explicit_bounded_public_collection_required"):
        owner.collect(receipt.request_id, (SecretStr(QUERY),), public_web=False)
    with pytest.raises(ValueError):
        collected(q, receipt, queries=("!unapprovedengine query",))
    with pytest.raises(KernelDenied, match="duplicate_public_query"):
        collected(q, receipt, queries=(QUERY, QUERY))
    for changed in (
        q.settings.model_copy(update={"certificate_sha256": "ef" * 32}),
        q.settings.model_copy(update={"search": q.settings.search.model_copy(update={"max_results": 1})}),
    ):
        with pytest.raises(KernelDenied):
            OwnerCollection(q.f.dsn, changed).collect(receipt.request_id, (SecretStr(QUERY),), public_web=True)
    assert task(q, receipt) == "CREATED" and not q.f.server["requests"] and not q.calls
    path = q.root / q.f.actor.owner_id / q.f.actor.project_id / hashlib.sha256(QUESTION.encode()).hexdigest()
    path.unlink()
    with pytest.raises(KernelDenied, match="research_brief_unavailable"):
        collected(q, receipt)
    assert task(q, receipt) == "CREATED" and not q.f.server["requests"]


@pytest.mark.parametrize("admitted_search", [JOINT], indirect=True)
def test_contract_without_public_web_grant_is_not_upgraded_by_collect_flag(owner_question):
    q = owner_question
    document = {**q.document, "constraints": {**q.document["constraints"], "cloud_egress": "deny"}}
    receipt = stage(q, document=document)
    with pytest.raises(KernelDenied, match="research_collection_contract_or_policy_denied"):
        collected(q, receipt)
    assert task(q, receipt) == "CREATED" and not q.f.server["requests"] and not q.calls


@pytest.mark.parametrize("admitted_search", [JOINT], indirect=True)
def test_activation_takes_goal_lock_before_updating_task_and_cancellation_can_follow(owner_question):
    q = owner_question
    receipt = stage(q)
    owner = OwnerCollection(q.f.dsn, q.settings)

    def goal_is_locked():
        with psycopg.connect(q.f.dsn) as other:
            with pytest.raises(psycopg.errors.LockNotAvailable):
                other.execute("SELECT id FROM panestria.goal WHERE id=%s FOR NO KEY UPDATE NOWAIT", (receipt.goal_id,))

    with owner.connect() as c:
        binding = owner.lifecycle.load(UnitOfWork(c), q.f.actor, receipt.request_id)
        with ThreadPoolExecutor(1) as pool:
            pool.submit(goal_is_locked).result(timeout=3)
        owner.lifecycle.begin(UnitOfWork(c), q.f.actor, binding)
    assert task(q, receipt) == "VALIDATING"
    with psycopg.connect(q.f.dsn) as c:
        version = c.execute("SELECT row_version FROM panestria.task WHERE id=%s", (receipt.task_id,)).fetchone()[0]
        CancellationService().cancel(
            UnitOfWork(c),
            q.f.actor,
            receipt.goal_id,
            version,
            "synthetic cancellation after activation",
            correlation_id=str(uuid4()),
        )
    assert task(q, receipt) == "CANCELLED" and not q.f.server["requests"] and not q.calls


@pytest.mark.parametrize("admitted_search", [JOINT], indirect=True)
def test_actual_outbound_commit_lost_ack_is_reconciling_unknown_and_never_auto_redispatched(
    owner_question, monkeypatch
):
    q = owner_question
    receipt = stage(q)
    original = SearchAdmissionService.claim

    def lost(self, uow, *a, **kw):
        original(self, uow, *a, **kw)
        uow.connection.commit()
        raise OSError("SYNTHETIC_LOST_ACK_AFTER_ACTUAL_QUERY_RESERVATION")

    monkeypatch.setattr(SearchAdmissionService, "claim", lost)
    with pytest.raises(KernelDenied, match="research_collection_outcome_unknown"):
        collected(q, receipt)
    brief = inspect(q, receipt)
    assert brief.task_state == "RECONCILING" and brief.collection.stop_reason == "interrupted"
    assert brief.collection.searches[0].status == "UNKNOWN" and brief.collection.latest_attempt_status == "LOST"
    monkeypatch.setattr(SearchAdmissionService, "claim", original)
    with pytest.raises(KernelDenied, match="research_collection_already_started_inspect_state"):
        collected(q, receipt)
    assert not q.f.server["requests"] and not q.calls


@pytest.mark.parametrize("admitted_search", [JOINT], indirect=True)
@pytest.mark.parametrize("stop", ["cancel", "expire"])
def test_late_cancellation_or_expiry_never_returns_excerpts_or_overwrites_new_state(owner_question, monkeypatch, stop):
    q = owner_question
    receipt = stage(q)
    original = OwnerCollection._excerpt

    def stop_before_excerpt(self, binding, fetch, snapshot):
        with psycopg.connect(q.f.dsn) as c:
            if stop == "cancel":
                version = c.execute(
                    "SELECT row_version FROM panestria.task WHERE id=%s", (receipt.task_id,)
                ).fetchone()[0]
                CancellationService().cancel(
                    UnitOfWork(c),
                    q.f.actor,
                    receipt.goal_id,
                    version,
                    "synthetic late cancellation",
                    correlation_id=str(uuid4()),
                )
            else:
                c.execute(
                    "UPDATE panestria.task_attempt SET lease_expires_at=clock_timestamp()-interval '1 second' "
                    "WHERE task_id=%s",
                    (receipt.task_id,),
                )
        return original(self, binding, fetch, snapshot)

    monkeypatch.setattr(OwnerCollection, "_excerpt", stop_before_excerpt)
    with pytest.raises(KernelDenied, match="stale_lease"):
        collected(q, receipt)
    brief = inspect(q, receipt)
    assert not brief.claims and brief.collection.fetches[0].status == "RETAINED"
    assert brief.task_state == ("CANCELLED" if stop == "cancel" else "RECONCILING")
    if stop == "expire":
        assert brief.collection.latest_attempt_status == "LOST" and not brief.collection.lease_unexpired
    assert len(q.calls) == 1
