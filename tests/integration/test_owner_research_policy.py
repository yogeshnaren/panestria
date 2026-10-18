"""Actual PG/owner CLI; TEST_FIXTURE_NOT_LIVE certificates and synthetic HTTPS."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from test_configured_search import search_server  # noqa: F401 -- shared fixture dependency
from test_fetch_admission import synthetic_https  # noqa: F401 -- synthetic HTTPS only
from test_search_admission import admitted_search  # noqa: F401 -- joint fixture dependency
from typer.testing import CliRunner

from panestria.cli.main import app
from panestria.config_research import ResearchSettings
from panestria.contracts.policy import PolicyContext, PrivacyAxis
from panestria.execution.research_policy import OwnerResearchPolicy
from panestria.kernel.errors import KernelDenied
from panestria.kernel.local_setup import LocalSetupIntent, LocalSetupService, offline_policy
from panestria.kernel.policy import PolicyService
from panestria.kernel.repositories.policy import current_policy
from panestria.kernel.uow import UnitOfWork

pytestmark = pytest.mark.parametrize("admitted_search", [{"combined_runtime": True}], indirect=True)


@pytest.fixture
def owner_policy(synthetic_https, tmp_path, monkeypatch, record_property):  # noqa: F811
    f, calls, _ = synthetic_https
    root = tmp_path / "dedicated-owner-research"
    root.mkdir(mode=0o700)
    settings = ResearchSettings.model_validate_json(
        json.dumps(
            {
                "schema_version": 1,
                "owner_id": f.actor.owner_id,
                "project_id": str(uuid4()),
                "root": str(root),
                "certificates": str(f.reports.root),
                "certificate_sha256": f.policy.trust.runtime_certificate_sha256,
                "search": f.settings.model_dump(mode="json"),
            }
        )
    )
    config = root / "research.json"
    config.write_text(settings.model_dump_json())
    config.chmod(0o600)
    monkeypatch.setenv("PANESTRIA_DATABASE_URL", f.dsn)
    record_property("scope", "Actual PG/CLI; TEST_FIXTURE_NOT_LIVE certificates; no live qualification")
    return SimpleNamespace(
        f=f,
        calls=calls,
        root=root,
        config=config,
        settings=settings,
        service=OwnerResearchPolicy(f.dsn, settings),
    )


def invoke(q, command, *args, expected=0):
    result = CliRunner().invoke(app, ["research", command, "--config", str(q.config), *args])
    assert result.exit_code == expected, (result.output, result.exception)
    return json.loads(result.output)


def current(q):
    with psycopg.connect(q.f.dsn) as c:
        return current_policy(UnitOfWork(c), q.service.actor)


def prepare(q):
    return invoke(q, "prepare-policy", "--public-web-policy")


def confirm(q, review, *, expected=0):
    return invoke(
        q, "confirm-policy", review["review_id"], review["effect_digest"], "--public-web-policy", expected=expected
    )


def certificate(q, **changes):
    digest = q.f.reports.write_report(json.dumps({**q.f.certificate, **changes}).encode())
    q.settings = q.settings.model_copy(update={"certificate_sha256": digest})
    q.config.write_text(q.settings.model_dump_json())
    q.service = OwnerResearchPolicy(q.f.dsn, q.settings)
    return digest


def test_owner_review_then_actual_stage_collect_export_with_exact_public_scope(owner_policy):
    q = owner_policy
    denied = invoke(q, "prepare-policy", expected=1)
    assert denied["reason"] == "explicit_public_web_policy_required"
    review = prepare(q)
    assert review["state"] == "PENDING" and current(q) == offline_policy(q.service.actor)
    proposed = PolicyContext.model_validate(review["proposed_policy"])
    assert proposed.trust.allowed_actions == ["external-send", "read"]
    assert proposed.privacy.cloud_destinations == ["public-web"] and not proposed.privacy.allow_private_cloud
    assert {k: v for k, v in proposed.autonomy.actions.items() if v != "observe"} == {
        "read": "act-and-report",
        "external-send": "act-and-report",
    }
    assert not q.f.server["requests"] and not q.calls
    invoke(q, "confirm-policy", review["review_id"], review["effect_digest"], expected=1)
    invoke(q, "confirm-policy", review["review_id"], "ff" * 32, "--public-web-policy", expected=1)
    assert current(q) == offline_policy(q.service.actor)
    receipt = confirm(q, review)
    assert receipt["state"] == "APPLIED" and current(q) == proposed
    assert confirm(q, review)["replayed"] and prepare(q)["state"] == "CURRENT"
    with psycopg.connect(q.f.dsn) as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.project_policy_revision WHERE project_id=%s", (q.service.actor.project_id,)
        ).fetchone() == (2,)
        assert c.execute(
            "SELECT g.status,t.state,t.lease_epoch FROM panestria.goal g JOIN panestria.task t "
            "ON t.goal_id=g.id WHERE g.id=%s",
            (q.service.goal_id,),
        ).fetchone() == ("CREATED", "CREATED", 0)
        document = c.execute(
            "SELECT body FROM panestria.goal_contract WHERE goal_id=%s", (q.f.plan.scope.goal_id,)
        ).fetchone()[0]
    assert not q.f.server["requests"] and not q.calls  # Reviews themselves disclose no query.
    document.update(
        {
            "goal_id": str(uuid4()),
            "project_id": q.service.actor.project_id,
            "autonomy_profile_ref": receipt["policy_ref"],
            "trust_profile_id": proposed.trust.profile,
        }
    )
    for name, raw in (
        ("contract.json", json.dumps(document)),
        ("question.txt", "PUBLIC owner question"),
        ("limits.json", '{"max_sources":1}'),
        ("queries.json", '["PUBLIC synthetic question"]'),
    ):
        (q.root / name).write_text(raw)
        (q.root / name).chmod(0o600)
    staged = CliRunner().invoke(
        app,
        [
            "research",
            "stage",
            q.service.actor.owner_id,
            q.service.actor.project_id,
            "--contract",
            str(q.root / "contract.json"),
            "--question",
            str(q.root / "question.txt"),
            "--limits",
            str(q.root / "limits.json"),
            "--store",
            str(q.root),
            "--key",
            "owner-policy-reviewed-collection",
            "--public-question",
        ],
    )
    assert staged.exit_code == 0, (staged.output, staged.exception)
    request = json.loads(staged.output)
    collected = invoke(
        q,
        "collect",
        request["request_id"],
        "--queries",
        str(q.root / "queries.json"),
        "--output",
        str(q.root / "retained.html"),
        "--public-web",
    )
    assert collected["retained_excerpts"] == 1 and collected["semantic_support"] == "NOT_ASSESSED"
    assert len(q.f.server["requests"]) == len(q.calls) == 1 and (q.root / "retained.html").is_file()
    with psycopg.connect(q.f.dsn) as c:
        assert c.execute("SELECT state FROM panestria.task WHERE id=%s", (request["task_id"],)).fetchone() == (
            "VERIFYING",
        )
        assert c.execute(
            "SELECT count(*) FROM panestria.check_run WHERE task_id=%s", (request["task_id"],)
        ).fetchone() == (0,)


def test_existing_offline_ask_and_other_owner_projects_are_preserved(owner_policy):
    q = owner_policy
    with psycopg.connect(q.f.dsn) as c:
        LocalSetupService().initialize(
            UnitOfWork(c),
            LocalSetupIntent(owner_id=q.settings.owner_id, project_id=q.settings.project_id, intent="OFFLINE_ASK"),
        )
    before = current(q)
    assert (
        invoke(q, "prepare-policy", "--public-web-policy", expected=1)["reason"]
        == "dedicated_research_project_required"
    )
    assert current(q) == before
    q.settings = q.settings.model_copy(update={"owner_id": uuid4()})
    q.config.write_text(q.settings.model_dump_json())
    assert invoke(q, "prepare-policy", "--public-web-policy", expected=1)["reason"] == "not_found"
    with psycopg.connect(q.f.dsn) as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.policy_review WHERE project_id=%s", (q.settings.project_id,)
        ).fetchone() == (0,)
        assert c.execute("SELECT 1 FROM panestria.principal WHERE id=%s", (q.settings.owner_id,)).fetchone() is None


@pytest.mark.parametrize("invalid", ["purpose", "runtime", "expiry", "missing_report"])
def test_invalid_joint_qualification_creates_no_project(owner_policy, invalid):
    q = owner_policy
    if invalid == "purpose":
        certificate(q, purpose="PUBLIC_SEARCH_RUNTIME_ONLY")
    elif invalid == "runtime":
        certificate(q, runtime_versions={**q.f.certificate["runtime_versions"], "source_sha256": "ff" * 32})
    elif invalid == "expiry":
        certificate(q, expires_at=(datetime.now(UTC) - timedelta(seconds=1)).isoformat())
    else:
        report = q.f.certificate["cases"][-1]["report_sha256"]
        (q.f.reports.root / report).unlink()
    invoke(q, "prepare-policy", "--public-web-policy", expected=1)
    with psycopg.connect(q.f.dsn) as c:
        assert c.execute("SELECT 1 FROM panestria.project WHERE id=%s", (q.settings.project_id,)).fetchone() is None


def test_certificate_renewal_uses_stable_marker_and_only_changes_trust_axis(owner_policy):
    q = owner_policy
    review = prepare(q)
    original = confirm(q, review)
    digest = certificate(q, qualification_observation="SECOND TEST_FIXTURE_NOT_LIVE")
    assert confirm(q, review, expected=1)["reason"] == "research_policy_certificate_changed"
    renewed = prepare(q)
    result = confirm(q, renewed)
    old, new = PolicyContext.model_validate(original["policy"]), PolicyContext.model_validate(result["policy"])
    assert new.version == 3 and new.trust.version == 3 and new.trust.runtime_certificate_sha256 == digest
    assert new.privacy == old.privacy and new.autonomy == old.autonomy
    assert prepare(q)["state"] == "CURRENT"
    with psycopg.connect(q.f.dsn) as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.goal WHERE project_id=%s", (q.settings.project_id,)
        ).fetchone() == (1,)


def test_approval_commit_then_interruption_keeps_grant_off_until_revalidated_retry(owner_policy, monkeypatch):
    q = owner_policy
    review = prepare(q)
    apply = PolicyService.apply
    monkeypatch.setattr(
        PolicyService, "apply", lambda *_a, **_k: (_ for _ in ()).throw(OSError("SYNTHETIC_LOST_PHASE"))
    )
    assert confirm(q, review, expected=1)["reason"] == "research_policy_not_confirmed"
    assert current(q) == offline_policy(q.service.actor)
    with psycopg.connect(q.f.dsn) as c:
        assert c.execute(
            "SELECT state FROM panestria.policy_review WHERE id=%s", (review["review_id"],)
        ).fetchone() == ("APPROVED",)
    monkeypatch.setattr(PolicyService, "apply", apply)
    assert confirm(q, review)["state"] == "APPLIED"
    assert confirm(q, review)["replayed"]


def test_concurrent_preparation_and_stale_or_broader_reviews_cannot_widen_scope(owner_policy):
    q = owner_policy
    with ThreadPoolExecutor(max_workers=2) as pool:
        reviews = list(pool.map(lambda _: q.service.prepare(public_web_policy=True), range(2)))
    assert all(review["state"] == "PENDING" for review in reviews)
    proposed = PolicyContext.model_validate(reviews[0]["proposed_policy"])
    broader = proposed.model_copy(
        update={
            "privacy": PrivacyAxis(
                version=proposed.privacy.version, cloud_destinations=["public-web"], allow_private_cloud=True
            )
        }
    )
    with psycopg.connect(q.f.dsn) as c:
        other = PolicyService(q.service.search).propose(UnitOfWork(c), q.service.actor, q.service.task_id, broader)
    assert (
        invoke(q, "confirm-policy", other.review_id, other.effect_digest, "--public-web-policy", expected=1)["reason"]
        == "research_policy_review_changed"
    )
    confirm(q, reviews[0])
    with pytest.raises(KernelDenied, match="research_policy_review_changed"):
        q.service.confirm(reviews[1]["review_id"], reviews[1]["effect_digest"], public_web_policy=True)
    assert current(q) == proposed
    assert not q.calls and not q.f.server["requests"]
