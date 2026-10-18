"""Actual PG/loopback dispatch and crashes; certificate is TEST_FIXTURE_NOT_LIVE.

No installed SearXNG, upstream engine, public-web OS qualification or release
gate is claimed by this deterministic integration suite.
"""

import hashlib
import json
import os
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from pydantic import SecretStr
from test_aos_002_migration import _schema_fingerprint
from test_configured_search import search_server  # noqa: F401
from test_memory_restore import _fixture_container

from panestria.brokers.research.search import SearchUnavailable
from panestria.contracts.goal import contract_sha256, load_contract
from panestria.contracts.policy import AutonomyAxis, PrivacyAxis, TrustAxis
from panestria.contracts.research import ResearchArtifactRef, ResearchLimits, ResearchRequestRecord, ResearchScope
from panestria.contracts.research_admission import FetchPlan
from panestria.contracts.search import LocalSearchSettings, SearchDisclosure, SearchQuery
from panestria.contracts.search_admission import SearchPlan
from panestria.execution.research_fetch import AdmittedFetch, fetch_runtime_versions
from panestria.execution.search import AdmittedSearch, search_runtime_versions
from panestria.kernel.build import BuildEvidenceStore
from panestria.kernel.cancellation import CancellationService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor, GoalService
from panestria.kernel.leases import LeaseService
from panestria.kernel.policy import PolicyService
from panestria.kernel.research_blobs import ResearchBlobStore
from panestria.kernel.research_requests import ResearchRequestService
from panestria.kernel.uow import UnitOfWork
from panestria.policy.profiles import CertificateStore
from panestria.policy.research_fetch import PublicFetchCertificateStore
from panestria.policy.search import PublicSearchCertificateStore

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def component_metadata(record_property):
    record_property("scope", "Actual disposable PG/loopback HTTP; TEST_FIXTURE_NOT_LIVE certificate; no release proof")


@pytest.fixture
def admitted_search(r1_migration_task, search_server, tmp_path, request):  # noqa: F811
    changes = getattr(request, "param", {})
    is_fetch = changes.get("fetch_runtime", False)
    r1_task = r1_migration_task  # Isolated DB: do not add audit to another test's downgrade fixture.
    actor = Actor(r1_task["owner"], r1_task["project"])
    settings = LocalSearchSettings(provider="searxng-local", origin=search_server["origin"])
    versions = fetch_runtime_versions() if is_fetch else search_runtime_versions(settings)
    reports = BuildEvidenceStore(tmp_path / "search-cert-FIXTURE-NOT-LIVE")
    report = reports.write_report(b'{"scope":"TEST_FIXTURE_NOT_LIVE"}')
    body = {
        "schema_version": 1,
        "profile": "PERSONAL_SANDBOX",
        "verdict": "PASS",
        "purpose": "PUBLIC_FETCH_READER_RUNTIME_ONLY" if is_fetch else "PUBLIC_SEARCH_RUNTIME_ONLY",
        "scope": "TEST_FIXTURE_NOT_LIVE",
        "runtime_versions": versions,
        "candidate_commit": "ab" * 20,
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "allowed_actions": ["read", "external-send"],
        "cases": [
            {"case_id": case, "verdict": "PASS", "execution_mode": "OS_BOUNDARY", "report_sha256": report}
            for case in (
                ("AOS-008-TC03", "AOS-010-TC03", "AOS-019-TC02", "AOS-019-TC03", "AOS-020-TC01")
                if is_fetch
                else ("AOS-008-TC03", "AOS-010-TC03", "AOS-019-TC04")
            )
        ],
    }
    digest = reports.write_report(json.dumps(body).encode())
    certificates = (
        PublicFetchCertificateStore(reports.root, versions)
        if is_fetch
        else PublicSearchCertificateStore(reports.root, versions)
    )
    service = PolicyService(certificates)
    dsn = r1_task["dsn"]
    with psycopg.connect(dsn) as c:
        old = service.initialize(UnitOfWork(c), actor, r1_task["task"])
    actions = dict(old.autonomy.actions)
    actions["external-send"] = "act-and-report"
    proposed = old.model_copy(
        update={
            "version": 2,
            "trust": TrustAxis(
                version=2,
                profile="PERSONAL_SANDBOX",
                allowed_actions=["read", "external-send"],
                runtime_certificate_sha256=digest,
            ),
            "privacy": PrivacyAxis(version=2, cloud_destinations=["public-web"]),
            "autonomy": AutonomyAxis(version=2, actions=actions),
        }
    )
    with psycopg.connect(dsn) as c:
        review = service.propose(UnitOfWork(c), actor, r1_task["task"], proposed)
    with psycopg.connect(dsn) as c:
        service.decide(UnitOfWork(c), actor, review.review_id, review.effect_digest, "approve")
    with psycopg.connect(dsn) as c:
        policy = service.apply(UnitOfWork(c), actor, review.review_id, review.effect_digest)
    scope = ResearchScope(
        owner_id=actor.owner_id, project_id=actor.project_id, goal_id=str(uuid4()), task_id=str(uuid4())
    )
    document = {
        "schema_version": 1,
        "goal_id": scope.goal_id,
        "contract_version": 1,
        "owner_id": actor.owner_id,
        "project_id": actor.project_id,
        "intent": "PUBLIC synthetic search",
        "privacy_class": "PUBLIC",
        "trust_profile_id": "PERSONAL_SANDBOX",
        "autonomy_profile_ref": f"project-policy:{policy.version}:{policy.sha256()}",
        "constraints": {
            "allowed_paths": ["brief"],
            "forbidden_paths": [".git/**"],
            "permitted_capabilities": ["public-fetch" if is_fetch else "public-search"],
            "cloud_egress": "allow",
        },
        "budget": {"max_attempts_per_task": 2, "max_wall_seconds": 60, "max_api_usd": "0"},
        "acceptance": [
            {
                "id": "brief",
                "description": "Brief exists",
                "required": True,
                "evidence": {"required": True, "kind": "artifact"},
                "verifier": {"type": "artifact-exists", "artifact_ref": "brief", "expected_sha256": "ab" * 32},
            }
        ],
        "non_goals": [],
    }
    for key in ("privacy_class", "trust_profile_id"):
        if key in changes:
            document[key] = changes[key]
    document["constraints"].update(changes.get("constraints", {}))
    document["budget"].update(changes.get("budget", {}))
    contract = load_contract(document)
    with psycopg.connect(dsn) as c:
        GoalService().submit(UnitOfWork(c), actor, document, "synthetic-search")
    with psycopg.connect(dsn) as c:
        c.execute("UPDATE panestria.goal SET status='ACTIVE' WHERE id=%s", (scope.goal_id,))
        cid = c.execute("SELECT id FROM panestria.goal_contract WHERE goal_id=%s", (scope.goal_id,)).fetchone()[0]
        c.execute(
            "INSERT INTO panestria.task(id,goal_id,contract_id,name,state) VALUES(%s,%s,%s,'search','READY')",
            (scope.task_id, scope.goal_id, cid),
        )
        artifact = str(uuid4())
        question_sha, question_size, store_key = "ab" * 32, 25, "synthetic-metadata-only"
        if is_fetch:
            with ResearchBlobStore(tmp_path, actor) as blobs:
                blob = blobs.put(b"PUBLIC synthetic fetch question")
            question_sha, question_size, store_key = blob.sha256, blob.size_bytes, blob.sha256
        c.execute(
            "INSERT INTO panestria.artifact(id,task_id,kind,store_key,sha256,privacy_class,size_bytes) "
            "VALUES(%s,%s,'question',%s,%s,%s,%s)",
            (artifact, scope.task_id, store_key, question_sha, changes.get("question_label", "PUBLIC"), question_size),
        )
    request = ResearchRequestRecord(
        request_id=str(uuid4()),
        scope=scope,
        limits=ResearchLimits(**changes.get("research_limits", {})),
        question=ResearchArtifactRef(
            artifact_id=artifact,
            task_id=scope.task_id,
            sha256=question_sha,
            size_bytes=question_size,
            privacy_label=changes.get("question_label", "PUBLIC"),
        ),
    )
    with psycopg.connect(dsn) as c:
        prepared = ResearchRequestService().prepare(UnitOfWork(c), actor, request)
    with psycopg.connect(dsn) as c:
        lease = LeaseService().acquire(UnitOfWork(c), actor, scope.task_id, "configured-search", 0, ttl_seconds=60)
    binding = dict(
        scope=scope,
        request_id=request.request_id,
        request_sha256=prepared.request_sha256,
        contract_sha256=contract_sha256(contract),
        policy_sha256=policy.sha256(),
        configuration_sha256=certificates.runtime_versions["configuration_sha256"],
    )
    plan = FetchPlan(**binding) if is_fetch else SearchPlan(**binding, max_queries=2)
    controller = (
        AdmittedFetch(dsn, actor, plan, lease.attempt_id, lease.epoch, certificates, tmp_path)
        if is_fetch
        else AdmittedSearch(dsn, actor, plan, lease.attempt_id, lease.epoch, settings, certificates)
    )
    yield SimpleNamespace(
        controller=controller,
        root=tmp_path,
        dsn=dsn,
        actor=actor,
        plan=plan,
        lease=lease,
        policy=policy,
        certificate=body,
        reports=reports,
        settings=settings,
        request=request,
        server=search_server,
    )


def query(f, text="PUBLIC synthetic question"):
    return SearchQuery(
        request_id=UUID(f.plan.request_id), scope=f.plan.scope, query=SecretStr(text), privacy_class="PUBLIC"
    )


def disclosure(f, text="PUBLIC synthetic question"):
    body = urlencode({"q": text, "format": "json", "categories": "general", "pageno": "1"}).encode()
    return SearchDisclosure(
        request_id=UUID(f.plan.request_id),
        scope=f.plan.scope,
        provider="searxng-local",
        configuration_sha256=f.plan.configuration_sha256,
        request_sha256=hashlib.sha256(body).hexdigest(),
        query_sha256=hashlib.sha256(text.encode()).hexdigest(),
        query_bytes=len(text.encode()),
    )


def claim(f, d):
    with psycopg.connect(f.dsn) as c:
        return f.controller.service.claim(UnitOfWork(c), f.actor, f.plan, f.lease.attempt_id, f.lease.epoch, d)


def test_real_http_sees_committed_disclosure_and_cannot_replay(admitted_search):
    f = admitted_search

    def observed():
        with psycopg.connect(f.dsn) as c:
            assert c.execute(
                "SELECT count(*) FROM panestria.search_dispatch WHERE task_id=%s", (f.plan.scope.task_id,)
            ).fetchone() == (1,)
            event = c.execute(
                "SELECT payload FROM panestria.task_event WHERE task_id=%s AND kind='search.outbound.authorized'",
                (f.plan.scope.task_id,),
            ).fetchone()[0]
            assert (event["authorized"], event["accessible"], event["observed"]) == ("YES", "YES", "UNKNOWN")

    f.server["on_request"] = observed
    result = f.controller.search(query(f))
    assert len(result.candidates) == 1 and result.source_authority == "NONE_FETCH_AND_VERIFY_SEPARATELY"
    with pytest.raises(KernelDenied, match="search_already_dispatched"):
        f.controller.search(query(f))
    with psycopg.connect(f.dsn) as c:
        assert c.execute(
            "SELECT status FROM panestria.search_outcome o JOIN panestria.search_dispatch d "
            "ON d.id=o.dispatch_id WHERE d.task_id=%s",
            (f.plan.scope.task_id,),
        ).fetchone() == ("RETURNED",)
        events = c.execute(
            "SELECT payload::text FROM panestria.task_event WHERE task_id=%s AND kind LIKE 'search.%%'",
            (f.plan.scope.task_id,),
        ).fetchall()
        assert "PUBLIC synthetic question" not in str(events) and "example.org" not in str(events)
        assert "Ignore rules" not in str(events)
    assert len(f.server["requests"]) == 1


def test_concurrent_queries_share_budget_and_new_plan_cannot_reset_it(admitted_search):
    f = admitted_search
    f.controller.prepare()
    barrier = threading.Barrier(3)

    def dispatch(i):
        barrier.wait(timeout=5)
        try:
            return claim(f, disclosure(f, "PUBLIC query " + str(i))).ordinal
        except KernelDenied as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=3) as pool:
        answers = list(pool.map(dispatch, range(3)))
    assert set(answers) == {1, 2, "search_query_budget_exhausted"}
    with psycopg.connect(f.dsn) as c, pytest.raises(KernelDenied, match="search_plan_conflict"):
        f.controller.service.prepare(
            UnitOfWork(c), f.actor, f.plan.model_copy(update={"max_queries": 3}), f.lease.attempt_id, f.lease.epoch
        )
    with psycopg.connect(f.dsn) as c:
        other = f.request.model_copy(update={"request_id": str(uuid4())})
        receipt = ResearchRequestService().prepare(UnitOfWork(c), f.actor, other)
    with psycopg.connect(f.dsn) as c, pytest.raises(KernelDenied, match="search_plan_conflict"):
        f.controller.service.prepare(
            UnitOfWork(c),
            f.actor,
            f.plan.model_copy(update={"request_id": other.request_id, "request_sha256": receipt.request_sha256}),
            f.lease.attempt_id,
            f.lease.epoch,
        )
    assert not f.server["requests"]


def test_rollback_releases_reservation_but_lost_commit_ack_consumes_it(admitted_search, monkeypatch):
    f = admitted_search
    f.controller.prepare()
    with pytest.raises(RuntimeError, match="rollback"), psycopg.connect(f.dsn) as c:
        f.controller.service.claim(UnitOfWork(c), f.actor, f.plan, f.lease.attempt_id, f.lease.epoch, disclosure(f))
        raise RuntimeError("rollback")
    original = f.controller.connect
    failed = False

    @contextmanager
    def lost_ack():
        nonlocal failed
        with original() as c:
            before = c.execute(
                "SELECT count(*) FROM panestria.search_dispatch WHERE task_id=%s", (f.plan.scope.task_id,)
            ).fetchone()[0]
            yield c
            after = c.execute(
                "SELECT count(*) FROM panestria.search_dispatch WHERE task_id=%s", (f.plan.scope.task_id,)
            ).fetchone()[0]
        if after > before and not failed and threading.current_thread() is threading.main_thread():
            failed = True
            raise RuntimeError("commit acknowledgement lost")

    monkeypatch.setattr(f.controller, "connect", lost_ack)
    with pytest.raises(RuntimeError, match="acknowledgement lost"):
        f.controller.search(query(f))
    monkeypatch.setattr(f.controller, "connect", original)
    with pytest.raises(KernelDenied, match="search_already_dispatched"):
        f.controller.search(query(f))
    assert not f.server["requests"]
    with psycopg.connect(f.dsn) as c:
        assert c.execute(
            "SELECT status FROM panestria.search_outcome o JOIN panestria.search_dispatch d "
            "ON d.id=o.dispatch_id WHERE d.task_id=%s",
            (f.plan.scope.task_id,),
        ).fetchone() == ("UNKNOWN",)


@pytest.mark.parametrize("status", [403, 429])
def test_failed_setup_or_quota_consumes_dispatch_without_fallback(admitted_search, status):
    f = admitted_search
    f.server["status"] = status
    with pytest.raises(SearchUnavailable, match="search_json_disabled_or_denied|search_quota_unavailable"):
        f.controller.search(query(f))
    with pytest.raises(KernelDenied, match="search_already_dispatched"):
        f.controller.search(query(f))
    assert len(f.server["requests"]) == 1


def test_actual_cancellation_stops_pending_http_and_does_not_restore_authority(admitted_search):
    f = admitted_search
    f.server["delay"] = 0.05
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(f.controller.search, query(f))
        deadline = time.monotonic() + 5
        while not f.server["requests"] and time.monotonic() < deadline:
            time.sleep(0.01)
        assert f.server["requests"]
        with psycopg.connect(f.dsn) as c:
            CancellationService().cancel(
                UnitOfWork(c),
                f.actor,
                f.plan.scope.goal_id,
                f.lease.row_version,
                "synthetic cancellation",
                correlation_id=str(uuid4()),
            )
        with pytest.raises((SearchUnavailable, KernelDenied)):
            future.result(timeout=5)
    with pytest.raises(KernelDenied, match="stale_lease"):
        f.controller.search(query(f))
    with psycopg.connect(f.dsn) as c:
        assert c.execute("SELECT status FROM panestria.goal WHERE id=%s", (f.plan.scope.goal_id,)).fetchone() == (
            "CANCELLED",
        )
        assert c.execute(
            "SELECT count(*) FROM panestria.search_dispatch WHERE task_id=%s", (f.plan.scope.task_id,)
        ).fetchone() == (1,)


def test_cancellation_during_receipt_commit_fences_a_returned_response(admitted_search, monkeypatch):
    f = admitted_search
    original = f.controller.service.finish

    def finish_then_cancel(uow, *args, **kwargs):
        original(uow, *args, **kwargs)
        uow.connection.commit()  # Actual acknowledged receipt commit, then concurrent owner action.
        with psycopg.connect(f.dsn) as c:
            CancellationService().cancel(
                UnitOfWork(c),
                f.actor,
                f.plan.scope.goal_id,
                f.lease.row_version,
                "synthetic late cancellation",
                correlation_id=str(uuid4()),
            )

    monkeypatch.setattr(f.controller.service, "finish", finish_then_cancel)
    with pytest.raises(KernelDenied, match="stale_lease"):
        f.controller.search(query(f))
    assert len(f.server["requests"]) == 1
    with psycopg.connect(f.dsn) as c:
        assert c.execute("SELECT status FROM panestria.search_outcome").fetchone() == ("RETURNED",)


def test_revoked_policy_owner_scope_and_expired_lease_deny_before_http(admitted_search):
    f = admitted_search
    f.controller.prepare()
    with psycopg.connect(f.dsn) as c, pytest.raises(KernelDenied, match="not_found"):
        f.controller.service.claim(
            UnitOfWork(c),
            Actor(str(uuid4()), f.actor.project_id),
            f.plan,
            f.lease.attempt_id,
            f.lease.epoch,
            disclosure(f),
        )
    # Use the actual owner review/apply path rather than mutating a stored policy.
    policy_service = PolicyService(f.controller.service.certificates)
    revocation = f.policy.model_copy(update={"version": 3, "privacy": PrivacyAxis(version=3)})
    with psycopg.connect(f.dsn) as c:
        review = policy_service.propose(UnitOfWork(c), f.actor, f.plan.scope.task_id, revocation)
    with psycopg.connect(f.dsn) as c:
        policy_service.decide(UnitOfWork(c), f.actor, review.review_id, review.effect_digest, "approve")
    with psycopg.connect(f.dsn) as c:
        policy_service.apply(UnitOfWork(c), f.actor, review.review_id, review.effect_digest)
    with pytest.raises(KernelDenied, match="search_contract_or_policy_mismatch"):
        f.controller.search(query(f))
    with psycopg.connect(f.dsn) as c:
        c.execute(
            "UPDATE panestria.task_attempt SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=%s",
            (f.lease.attempt_id,),
        )
    with pytest.raises(KernelDenied, match="stale_lease"):
        f.controller.search(query(f))
    assert not f.server["requests"]


def test_native_build_certificate_cannot_authorize_search(admitted_search):
    f = admitted_search
    body = {**f.certificate, "purpose": "PUBLIC_BASH_RUNTIME_ONLY"}
    digest = f.reports.write_report(json.dumps(body).encode())
    trust = f.policy.trust.model_copy(update={"runtime_certificate_sha256": digest})
    # Generic runtime validation alone is deliberately insufficient.
    CertificateStore(f.reports.root, search_runtime_versions(f.settings)).validate(trust)
    with pytest.raises(Exception, match="public_search_runtime_uncertified"):
        f.controller.service.certificates.validate(trust)
    with pytest.raises(KernelDenied, match="public_search_certificate_store_required"):
        from panestria.kernel.search import SearchAdmissionService

        SearchAdmissionService(CertificateStore(f.reports.root, search_runtime_versions(f.settings)))


@pytest.mark.parametrize(
    "admitted_search",
    [
        {"privacy_class": "INTERNAL"},
        {"question_label": "RESTRICTED"},
        {"constraints": {"cloud_egress": "deny"}},
        {"constraints": {"permitted_capabilities": ["read"]}},
        {"budget": {"max_api_usd": "1"}},
        {"trust_profile_id": "SYNTHETIC_DEV"},
    ],
    indirect=True,
)
def test_contract_or_question_cannot_downgrade_scope_or_expand_permission(admitted_search):
    f = admitted_search
    with pytest.raises(KernelDenied, match="search_contract_or_policy_mismatch"):
        f.controller.search(query(f))
    assert not f.server["requests"]


def test_replacement_lease_does_not_reset_query_or_wall_budgets(admitted_search):
    f = admitted_search
    f.controller.prepare()
    claim(f, disclosure(f))
    with psycopg.connect(f.dsn) as c:
        LeaseService().release(UnitOfWork(c), f.actor, f.lease.attempt_id, f.lease.epoch)
    with psycopg.connect(f.dsn) as c:
        version = c.execute("SELECT row_version FROM panestria.task WHERE id=%s", (f.plan.scope.task_id,)).fetchone()[0]
        lease = LeaseService().acquire(UnitOfWork(c), f.actor, f.plan.scope.task_id, "search", version)
    f.lease = lease
    with pytest.raises(KernelDenied, match="search_already_dispatched"):
        claim(f, disclosure(f))
    assert claim(f, disclosure(f, "second PUBLIC query")).ordinal == 2
    with pytest.raises(KernelDenied, match="search_query_budget_exhausted"):
        claim(f, disclosure(f, "third PUBLIC query"))
    with psycopg.connect(f.dsn) as c:
        c.execute(
            "UPDATE panestria.task_attempt SET started_at=clock_timestamp()-interval '61 seconds' "
            "WHERE task_id=%s AND id<>%s",
            (f.plan.scope.task_id, lease.attempt_id),
        )
    with pytest.raises(KernelDenied, match="search_deadline"):
        claim(f, disclosure(f, "fourth PUBLIC query"))
    assert not f.server["requests"]


def test_ledger_is_immutable_and_autocommit_cannot_split_event(admitted_search):
    f = admitted_search
    f.controller.prepare()
    with (
        psycopg.connect(f.dsn, autocommit=True) as c,
        pytest.raises(KernelDenied, match="search_caller_transaction_required"),
    ):
        f.controller.service.claim(UnitOfWork(c), f.actor, f.plan, f.lease.attempt_id, f.lease.epoch, disclosure(f))
    receipt = claim(f, disclosure(f))
    with psycopg.connect(f.dsn) as c:
        f.controller.service.finish(UnitOfWork(c), f.actor, f.plan.scope.task_id, receipt.dispatch_id, "UNKNOWN")
    with psycopg.connect(f.dsn) as c:
        f.controller.service.finish(UnitOfWork(c), f.actor, f.plan.scope.task_id, receipt.dispatch_id, "UNKNOWN")
        for table in ("search_plan", "search_dispatch", "search_outcome"):
            with pytest.raises(psycopg.Error), c.transaction():
                c.execute("DELETE FROM panestria." + table)
        with pytest.raises(KernelDenied, match="search_outcome_conflict"), c.transaction():
            f.controller.service.finish(
                UnitOfWork(c), f.actor, f.plan.scope.task_id, receipt.dispatch_id, "UNAVAILABLE"
            )


def migrate(dsn, direction, target):
    return subprocess.run(
        [str(ROOT / ".venv/bin/alembic"), "-c", "migrations/alembic.ini", direction, target],
        cwd=ROOT,
        env={**os.environ, "PANESTRIA_DATABASE_URL": dsn},
        capture_output=True,
        timeout=30,
    )


def test_empty_search_migration_roundtrip_preserves_old_rows_and_schema(r1_migration_task):
    dsn = r1_migration_task["dsn"]
    with psycopg.connect(dsn) as c:
        before = c.execute("SELECT to_jsonb(t) FROM panestria.task t").fetchall()
    for direction, target in (("downgrade", "0029_quota_observations"), ("upgrade", "head")):
        result = migrate(dsn, direction, target)
        assert result.returncode == 0, "search_schema_roundtrip_failed"
    with psycopg.connect(dsn) as c:
        assert c.execute("SELECT to_jsonb(t) FROM panestria.task t").fetchall() == before
        assert _schema_fingerprint(c) == (ROOT / "migrations/schema_fingerprint.txt").read_text()


def test_actual_backup_restore_retains_query_fence_and_global_events(admitted_search, record_property):
    f = admitted_search
    f.controller.prepare()
    receipt = claim(f, disclosure(f))
    with psycopg.connect(f.dsn) as c:
        f.controller.service.finish(UnitOfWork(c), f.actor, f.plan.scope.task_id, receipt.dispatch_id, "UNKNOWN")
    refused = migrate(f.dsn, "downgrade", "0029_quota_observations")
    assert refused.returncode != 0 and b"search admission audit exists" in refused.stderr
    with psycopg.connect(f.dsn) as c:
        assert c.execute("SELECT version_num FROM alembic_version").fetchone() == ("0031_fetch_admission",)
        row = c.execute("SELECT to_jsonb(d) FROM panestria.search_dispatch d").fetchone()[0]
        for change in ({"query_bytes": 0}, {"privacy_class": "INTERNAL"}, {"request_id": str(uuid4())}):
            malformed = {
                **row,
                "id": str(uuid4()),
                "ordinal": 2,
                "query_sha256": "cd" * 32,
                "disclosure": {**row["disclosure"], "query_sha256": "cd" * 32, **change},
            }
            with pytest.raises(psycopg.Error), c.transaction():
                c.execute(
                    "INSERT INTO panestria.search_dispatch SELECT "
                    "(jsonb_populate_record(NULL::panestria.search_dispatch,%s::jsonb)).*",
                    (json.dumps(malformed, default=str),),
                )
    container = _fixture_container()
    dump = subprocess.run(
        ["docker", "exec", container, "pg_dump", "-U", "panestria_synthetic", "-d", f.dsn.rsplit("/", 1)[1], "-Fc"],
        capture_output=True,
        check=True,
        timeout=30,
    )
    record_property("backup_sha256", hashlib.sha256(dump.stdout).hexdigest())
    name = "panestria_search_restore_" + uuid4().hex
    restored = f.dsn.rsplit("/", 1)[0] + "/" + name
    with psycopg.connect(f.dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            subprocess.run(
                [
                    "docker",
                    "exec",
                    "-i",
                    container,
                    "pg_restore",
                    "-U",
                    "panestria_synthetic",
                    "-d",
                    name,
                    "--exit-on-error",
                ],
                input=dump.stdout,
                capture_output=True,
                check=True,
                timeout=30,
            )
            original = f.dsn
            f.dsn = restored
            with psycopg.connect(restored) as c:
                before = c.execute("SELECT max(seq) FROM panestria.task_event").fetchone()[0]
            with pytest.raises(KernelDenied, match="search_already_dispatched"):
                claim(f, disclosure(f))
            assert claim(f, disclosure(f, "second PUBLIC query")).ordinal == 2
            with psycopg.connect(restored) as c:
                assert c.execute("SELECT max(seq) FROM panestria.task_event").fetchone()[0] > before
            f.dsn = original
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
