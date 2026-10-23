"""Actual PG/HTTP/CLI grant enforcement; HTTPS and certificates are explicit fixtures."""

# ruff: noqa: F811 -- imported pytest fixtures are injected by name

import json
from dataclasses import replace
from uuid import uuid4

import psycopg
import pytest
from pydantic import SecretStr
from test_configured_search import search_server  # noqa: F401 -- fixture dependency
from test_connection_terminal import connection_server  # noqa: F401 -- actual scoped HTTP server
from test_fetch_admission import synthetic_https  # noqa: F401 -- synthetic HTTPS, actual PG/CAS/reader
from test_owner_research_collection import collected, owner_question, stage, task  # noqa: F401
from test_search_admission import admitted_search  # noqa: F401 -- fixture dependency
from typer.testing import CliRunner

from panestria.brokers.research.fetch import FetchHop, PublicHttpsFetcher
from panestria.cli.main import app
from panestria.contracts.connections import ConnectionManifest, ConnectionReviewRequest, SubmitReview
from panestria.contracts.fetch_connection import (
    HTTP_HOP_RESERVED_BYTES,
    FetchConnectionBinding,
    anonymous_fetch_account,
)
from panestria.kernel.connections import ConnectionReviewService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.uow import UnitOfWork


@pytest.fixture(autouse=True)
def evidence_scope(record_property):
    record_property(
        "scope",
        "Actual disposable PG/HTTP/CLI/CAS; SYNTHETIC HTTPS and TEST_FIXTURE_NOT_LIVE certificates; no release proof",
    )


def approved(f, manifest=None, *, revoke=False):
    service = ConnectionReviewService()
    with psycopg.connect(f.dsn) as c:
        change = ConnectionReviewRequest(
            proposal_id=str(uuid4()),
            policy_ref=f"project-policy:{f.policy.version}:{f.policy.sha256()}",
            grant_id=f.plan.connection.grant_id if revoke else None,
            expected_version=f.plan.connection.version if revoke else 0,
            operation="REVOKE" if revoke else "REPLACE",
            manifest=manifest,
        )
        pending = service.propose(UnitOfWork(c), f.actor, f.plan.scope.task_id, change)
    with psycopg.connect(f.dsn) as c:
        decision = service.decide(UnitOfWork(c), f.actor, pending.proposal_id, pending.effect_digest, "approve")
    return FetchConnectionBinding(grant_id=pending.grant_id, version=decision.granted_version)


@pytest.mark.parametrize("admitted_search", [{"fetch_runtime": True}], indirect=True)
def test_only_exact_supported_declaration_can_reach_fetch_and_reservations_are_immutable(synthetic_https, monkeypatch):
    f, calls, _ = synthetic_https
    valid = f.plan
    with psycopg.connect(f.dsn) as c:
        base = ConnectionReviewService().current(UnitOfWork(c), f.actor, valid.connection.grant_id).manifest
    candidates = [(None, "fetch_connection_required")]
    for change in (
        {"account_ref": str(uuid4())},
        {"configuration_sha256": "cd" * 32},
        {"conformance_sha256": "de" * 32},
        {"root_refs": ("ab" * 32,)},
        {"actions": ("read",)},
        {"data_classes": ("INTERNAL",)},
    ):
        body = ConnectionManifest.model_validate_json(base.model_copy(update=change).model_dump_json())
        candidates.append((approved(f, body), "fetch_connection_"))
    candidates.append((valid.connection.model_copy(update={"version": 2}), "fetch_connection_not_current"))
    for binding, error in candidates:
        f.controller.plan = valid.model_copy(update={"connection": binding})
        with pytest.raises(KernelDenied, match=error):
            f.controller.collect(SecretStr("https://example.org/blocked"))
    f.controller.plan = valid
    with pytest.raises(KernelDenied, match="fetch_connection_origin_denied"):
        f.controller.collect(SecretStr("https://ungranted.example/blocked"))
    with psycopg.connect(f.dsn) as c:
        assert c.execute("SELECT count(*) FROM panestria.fetch_dispatch").fetchone() == (0,)
        assert c.execute("SELECT count(*) FROM panestria.connection_fetch_reservation").fetchone() == (0,)
    assert calls == []
    reserve = f.controller.service.grants.reserve

    def inconsistent_capacity(uow, actor, plan, dispatch_id, capacity):
        reserve(uow, actor, plan, dispatch_id, replace(capacity, application_bytes=capacity.application_bytes + 1))

    monkeypatch.setattr(f.controller.service.grants, "reserve", inconsistent_capacity)
    with pytest.raises(psycopg.Error, match="fetch connection capacity mismatch"):
        f.controller.collect(SecretStr("https://example.org/allowed"))
    with psycopg.connect(f.dsn) as c:
        assert c.execute("SELECT count(*) FROM panestria.fetch_dispatch").fetchone() == (0,)
        assert c.execute("SELECT count(*) FROM panestria.connection_fetch_reservation").fetchone() == (0,)
        assert c.execute("SELECT count(*) FROM panestria.task_event WHERE kind='fetch.body.reserved'").fetchone() == (
            0,
        )
    assert calls == []
    monkeypatch.setattr(f.controller.service.grants, "reserve", reserve)
    result = f.controller.collect(SecretStr("https://example.org/allowed"))
    assert result.status == "RETAINED" and calls == ["https://example.org/allowed"]
    with psycopg.connect(f.dsn) as c:
        row = c.execute(
            "SELECT r.grant_id::text,r.grant_version,r.reserved_hops,r.reserved_bytes,d.reserved_body_bytes "
            "FROM panestria.connection_fetch_reservation r JOIN panestria.fetch_dispatch d ON d.id=r.dispatch_id"
        ).fetchone()
        assert row[:2] == (valid.connection.grant_id, valid.connection.version)
        assert row[3] == row[4] + row[2] * HTTP_HOP_RESERVED_BYTES
        for statement in (
            "UPDATE panestria.connection_fetch_reservation SET reserved_bytes=49155",
            "DELETE FROM panestria.connection_fetch_reservation",
            "UPDATE panestria.fetch_plan SET connection_grant_version=NULL",
        ):
            with pytest.raises(psycopg.Error), c.transaction():
                c.execute(statement)


@pytest.mark.parametrize(
    "admitted_search",
    [{"combined_runtime": True, "connection_budget": {"max_calls": 1, "max_bytes": HTTP_HOP_RESERVED_BYTES + 128}}],
    indirect=True,
)
def test_lost_commit_ack_keeps_shared_grant_capacity_and_blocks_new_goal_before_search(owner_question, monkeypatch):
    q = owner_question
    f = q.f
    original = f.controller.service.claim

    def lost_ack(uow, *args, **kwargs):
        original(uow, *args, **kwargs)
        uow.connection.commit()
        raise OSError("SYNTHETIC_LOST_ACK_AFTER_REAL_COMMIT")

    monkeypatch.setattr(f.controller.service, "claim", lost_ack)
    with pytest.raises(OSError, match="SYNTHETIC_LOST_ACK"):
        f.controller.collect(SecretStr("https://example.org/uncertain"))
    monkeypatch.setattr(f.controller.service, "claim", original)
    receipt = stage(q)
    with pytest.raises(KernelDenied, match="fetch_connection_budget_exhausted"):
        collected(q, receipt)
    assert task(q, receipt) == "CREATED"
    assert not f.server["requests"] and not q.calls
    with psycopg.connect(f.dsn) as c:
        assert c.execute(
            "SELECT reserved_hops,reserved_bytes FROM panestria.connection_fetch_reservation"
        ).fetchone() == (1, HTTP_HOP_RESERVED_BYTES + 128)
        assert c.execute("SELECT count(*) FROM panestria.fetch_outcome").fetchone() == (0,)
        assert c.execute(
            "SELECT count(*) FROM panestria.task_attempt WHERE task_id=%s", (receipt.task_id,)
        ).fetchone() == (0,)


@pytest.mark.parametrize("admitted_search", [{"fetch_runtime": True}], indirect=True)
def test_actual_owner_revocation_after_first_hop_prevents_redirect_and_source_publication(synthetic_https, monkeypatch):
    f, calls, one = synthetic_https

    def redirected(self, target, url, cap, deadline, cancel):
        hop, *_ = one(self, target, url, cap, deadline, cancel)
        approved(f, revoke=True)  # Actual owner decision, not a mocked authority failure.
        return (
            FetchHop(hop.url_sha256, hop.address, 302, hop.certificate_sha256),
            "https://example.net/next",
            None,
            b"",
            False,
        )

    monkeypatch.setattr(PublicHttpsFetcher, "_one", redirected)
    with pytest.raises(KernelDenied, match="fetch_connection_not_current|fetch_cancelled"):
        f.controller.collect(SecretStr("https://example.org/start"))
    assert calls == ["https://example.org/start"]
    with psycopg.connect(f.dsn) as c:
        assert c.execute("SELECT count(*) FROM panestria.fetch_hop").fetchone() == (1,)
        assert c.execute("SELECT count(*) FROM panestria.research_source_capture").fetchone() == (0,)
        assert c.execute("SELECT status FROM panestria.fetch_outcome").fetchone() == ("UNKNOWN",)
        assert c.execute("SELECT count(*) FROM panestria.connection_fetch_reservation").fetchone() == (1,)


def test_cli_private_fetch_template_is_separate_from_proposal_consent_and_account_enrollment(
    connection_server, tmp_path
):
    f = connection_server
    private = tmp_path / "fetch-private"
    private.mkdir(mode=0o700)
    root, certs = private / "cas", private / "certificates"
    root.mkdir(mode=0o700)
    certs.mkdir(mode=0o700)
    document = {
        "schema_version": 1,
        "owner_id": f.actor.owner_id,
        "project_id": f.actor.project_id,
        "root": str(root),
        "certificates": str(certs),
        "certificate_sha256": "ab" * 32,
        "search": {"provider": "searxng-local", "origin": "http://127.0.0.1:54321"},
    }
    settings = private / "research.json"
    settings.write_text(json.dumps(document))
    settings.chmod(0o600)
    output = private / "proposal.json"
    args = [
        "connections",
        "prepare-public-fetch",
        "--config",
        str(f.config),
        "--research-config",
        str(settings),
        "--task-id",
        f.task["task"],
        "--proposal-id",
        str(uuid4()),
        "--origin",
        "https://example.org",
        "--output",
        str(output),
        "--max-calls",
        "2",
        "--max-bytes",
        "100000",
    ]
    runner = CliRunner()
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["status"] == "TEMPLATE_CREATED_UNVERIFIED"
    raw = output.read_bytes()
    body = SubmitReview.model_validate_json(raw)
    grant = body.change.manifest
    assert output.stat().st_mode & 0o777 == 0o600
    assert grant.actions == ("read", "send") and grant.data_classes == ("PUBLIC",)
    assert not grant.root_refs and grant.budget.max_cash_microusd == 0
    assert grant.account_ref == anonymous_fetch_account(
        f.actor.owner_id, f.actor.project_id, grant.configuration_sha256
    )
    assert f.state.proposals == f.state.decisions == 0
    assert runner.invoke(app, args).exit_code != 0 and output.read_bytes() == raw
    proposed = runner.invoke(app, ["connections", "propose", "--config", str(f.config), "--request-file", str(output)])
    assert proposed.exit_code == 0, proposed.output
    view = json.loads(proposed.output)
    assert view["state"] == "PENDING" and view["runtime_available"] is False
    assert f.state.proposals == 1 and f.state.decisions == 0
    document["project_id"] = str(uuid4())
    settings.write_text(json.dumps(document))
    other = private / "wrong-scope.json"
    args[args.index(str(output))] = str(other)
    assert runner.invoke(app, args).exit_code != 0 and not other.exists()
    assert f.state.proposals == 1 and f.state.decisions == 0


@pytest.mark.parametrize(
    "admitted_search",
    [{"combined_runtime": True, "connection_budget": {"max_calls": 1, "max_bytes": HTTP_HOP_RESERVED_BYTES + 128}}],
    indirect=True,
)
def test_collection_stops_before_more_queries_when_shared_connection_capacity_is_consumed(owner_question):
    q = owner_question
    receipt = stage(q)
    result = collected(q, receipt, queries=("PUBLIC synthetic question", "must not send second PUBLIC query"))
    assert result.stop_reason == "connection_limit" and task(q, receipt) == "VERIFYING"
    assert len(q.f.server["requests"]) == len(q.calls) == 1
    with psycopg.connect(q.f.dsn) as c:
        assert c.execute("SELECT status FROM panestria.fetch_outcome").fetchone() == ("RETAINED",)
