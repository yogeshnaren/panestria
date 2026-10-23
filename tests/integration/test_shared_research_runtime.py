"""One real PG policy/lease + loopback HTTP + reader, synthetic HTTPS/certificate.

No real SearXNG, live public-web qualification, model or semantic support claim.
"""

import json

import psycopg
import pytest
from pydantic import SecretStr
from test_configured_search import search_server  # noqa: F401 -- fixture dependency
from test_fetch_admission import synthetic_https  # noqa: F401 -- synthetic wire observation only
from test_search_admission import admitted_search, query  # noqa: F401 -- fixture dependency

from panestria.contracts.research import ClaimDraft, PassageRef
from panestria.contracts.research_claims import ClaimEvidenceDraft, QuotedPassage
from panestria.contracts.search_admission import SearchPlan
from panestria.execution.research_brief import RetainedBrief
from panestria.execution.research_claims import ClaimStore
from panestria.execution.research_fetch import AdmittedFetch
from panestria.execution.search import AdmittedSearch
from panestria.kernel.errors import KernelDenied
from panestria.kernel.research_sources import SourceRecordService
from panestria.kernel.uow import UnitOfWork
from panestria.policy.profiles import CertificateRejected
from panestria.policy.search import PublicSearchCertificateStore

JOINT = {"combined_runtime": True, "budget": {"max_wall_seconds": 120}}


@pytest.fixture(autouse=True)
def component_scope(record_property):
    record_property("scope", "Actual disposable PG/loopback HTTP/CAS/reader; SYNTHETIC HTTPS/certificate only")


def search_controller(f):
    versions = f.controller.versions
    binding = f.plan.model_dump(exclude={"connection"})
    binding["configuration_sha256"] = versions["search_configuration_sha256"]
    return AdmittedSearch(
        f.dsn,
        f.actor,
        SearchPlan(**binding, max_queries=1),
        f.lease.attempt_id,
        f.lease.epoch,
        f.settings,
        PublicSearchCertificateStore(f.reports.root, versions),
    )


@pytest.mark.parametrize("admitted_search", [JOINT], indirect=True)
def test_same_reviewed_policy_search_fetch_read_retain_quote_and_offline_brief(synthetic_https):  # noqa: F811
    f, calls, _ = synthetic_https
    search = search_controller(f)

    def before_search():
        with psycopg.connect(f.dsn) as c:
            assert c.execute("SELECT count(*) FROM panestria.search_dispatch").fetchone() == (1,)
            assert c.execute("SELECT count(*) FROM panestria.fetch_dispatch").fetchone() == (0,)

    f.server["on_request"] = before_search
    candidates = search.search(query(f))
    assert candidates.source_authority == "NONE_FETCH_AND_VERIFY_SEPARATELY"
    retained = f.controller.collect(candidates.candidates[0].url)
    assert retained.status == "RETAINED" and retained.snapshot_id is not None
    with psycopg.connect(f.dsn) as c:
        source = SourceRecordService().read(
            UnitOfWork(c), f.actor, retained.snapshot_id, request_id=f.plan.request_id, task_id=f.plan.scope.task_id
        )
        text = SourceRecordService().read_bytes(
            UnitOfWork(c),
            f.actor,
            retained.snapshot_id,
            request_id=f.plan.request_id,
            task_id=f.plan.scope.task_id,
            root=f.root,
            role="text",
        )
        ref = PassageRef(
            snapshot_id=retained.snapshot_id,
            request_id=f.plan.request_id,
            text_sha256=source.evidence.snapshot.text.sha256,
            start=0,
            end=len(text.data),
        )
        ClaimStore(f.root, f.actor).record(
            UnitOfWork(c),
            request_id=f.plan.request_id,
            task_id=f.plan.scope.task_id,
            draft=ClaimEvidenceDraft(
                claim=ClaimDraft(text=SecretStr("SYNTHETIC unverified interpretation"), kind="FACT", passages=(ref,)),
                quotes=(QuotedPassage(reference=ref, quote=SecretStr(text.data.decode())),),
            ),
            input_label="PUBLIC",
        )
        # Both plans bind exactly the same request/contract/policy/task and lease.
        assert c.execute(
            "SELECT s.request_id=f.request_id AND s.contract_sha256=f.contract_sha256 "
            "AND s.policy_sha256=f.policy_sha256 FROM panestria.search_plan s "
            "JOIN panestria.fetch_plan f USING(task_id)"
        ).fetchone() == (True,)
        assert c.execute(
            "SELECT s.attempt_id=f.attempt_id AND s.lease_epoch=f.lease_epoch "
            "FROM panestria.search_dispatch s JOIN panestria.fetch_dispatch f USING(task_id)"
        ).fetchone() == (True,)
        assert c.execute("SELECT count(*) FROM panestria.project_policy_revision").fetchone() == (2,)
        assert c.execute("SELECT state FROM panestria.task WHERE id=%s", (f.plan.scope.task_id,)).fetchone() == (
            "RUNNING",
        )
    brief = RetainedBrief(f.root, f.actor).inspect(f.dsn, f.plan.request_id, f.plan.scope.task_id)
    assert brief.claims[0].evidence_verdict == "EVIDENCE_PRESENT" and brief.semantic_support == "NOT_ASSESSED"
    assert brief.claims[0].citations[0].reference.snapshot_id == retained.snapshot_id
    assert len(f.server["requests"]) == len(calls) == 1


@pytest.mark.parametrize("admitted_search", [JOINT], indirect=True)
def test_joint_certificate_requires_correct_purpose_and_both_component_case_sets(synthetic_https):  # noqa: F811
    f, calls, _ = synthetic_https
    stores = (search_controller(f).service.certificates, f.controller.service.certificates)
    for store in stores:
        store.validate(f.policy.trust)
        for mutation in ("purpose", "AOS-019-TC04", "AOS-020-TC01"):
            body = json.loads(json.dumps(f.certificate))
            if mutation == "purpose":
                body["purpose"] = "PUBLIC_FETCH_READER_RUNTIME_ONLY"
            else:
                body["cases"] = [case for case in body["cases"] if case["case_id"] != mutation]
            digest = f.reports.write_report(json.dumps(body).encode())
            with pytest.raises(CertificateRejected):
                store.validate(f.policy.trust.model_copy(update={"runtime_certificate_sha256": digest}))
    assert not f.server["requests"] and not calls


@pytest.mark.parametrize("admitted_search", [JOINT], indirect=True)
def test_joint_settings_or_plan_substitution_denied_before_any_dispatch(synthetic_https):  # noqa: F811
    f, calls, _ = synthetic_https
    certificates = f.controller.service.certificates
    for settings in (None, f.settings.model_copy(update={"origin": "http://127.0.0.1:9099"})):
        with pytest.raises(KernelDenied, match="public_fetch_(search_settings|runtime)_mismatch"):
            AdmittedFetch(
                f.dsn,
                f.actor,
                f.plan,
                f.lease.attempt_id,
                f.lease.epoch,
                certificates,
                f.root,
                search_settings=settings,
            )
    search = search_controller(f)
    with pytest.raises(KernelDenied, match="public_search_runtime_mismatch"):
        AdmittedSearch(
            f.dsn,
            f.actor,
            search.plan,
            f.lease.attempt_id,
            f.lease.epoch,
            f.settings.model_copy(update={"max_results": 1}),
            search.service.certificates,
        )
    # Aggregate configuration identity cannot replace either component's plan identity.
    changed = f.plan.model_copy(update={"configuration_sha256": certificates.runtime_versions["configuration_sha256"]})
    with pytest.raises(KernelDenied, match="public_fetch_runtime_mismatch"):
        AdmittedFetch(
            f.dsn,
            f.actor,
            changed,
            f.lease.attempt_id,
            f.lease.epoch,
            certificates,
            f.root,
            search_settings=f.settings,
        )
    # The kernel also enforces component identity if a trusted caller bypasses
    # controller construction; a certificate's aggregate hash is not a plan.
    with psycopg.connect(f.dsn) as c:
        with pytest.raises(KernelDenied, match="search_contract_or_policy_mismatch"):
            f.controller.service.current(UnitOfWork(c), f.actor, changed, f.lease.attempt_id, f.lease.epoch)
    assert not f.server["requests"] and not calls
