"""Explicit owner setup against real PostgreSQL, without a synthetic task."""

from __future__ import annotations

import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from test_memory_restore import _fixture_container
from typer.testing import CliRunner

from panestria.cli.main import app
from panestria.contracts.policy import PolicyRequest
from panestria.kernel.ask import AskService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.local_setup import LocalSetupIntent, LocalSetupService, offline_policy
from panestria.kernel.policy import PolicyService
from panestria.kernel.repositories.policy import current_policy
from panestria.kernel.uow import UnitOfWork
from panestria.policy.engine import PolicyEngine
from panestria.policy.profiles import CertificateStore


def intent():
    return LocalSetupIntent(owner_id=str(uuid4()), project_id=str(uuid4()), intent="OFFLINE_ASK")


def test_setup_permits_only_local_read_and_does_not_create_fake_work(r1_database):
    request = intent()
    with psycopg.connect(r1_database) as c:
        uow = UnitOfWork(c)
        receipt = LocalSetupService().initialize(uow, request)
        assert receipt.replayed is False
        policy = current_policy(uow, request.actor())
        assert policy == offline_policy(request.actor())
        assert policy.trust.runtime_certificate_sha256 is None
        for action in policy.autonomy.actions:
            for destination in ("local", "anthropic-api", "claude-subscription", "openai-api"):
                decision = PolicyEngine().authorize(
                    PolicyRequest(
                        owner_id=receipt.owner_id,
                        project_id=receipt.project_id,
                        action=action,
                        label="RESTRICTED",
                        destination=destination,
                        effect_digest="ab" * 32,
                    ),
                    policy,
                )
                assert decision.outcome == ("PERMIT" if action == "read" and destination == "local" else "DENY")
        assert c.execute(
            "SELECT count(*) FROM panestria.goal WHERE project_id=%s", (receipt.project_id,)
        ).fetchone() == (0,)
        assert (
            c.execute(
                "SELECT seq,policy_sha256 FROM panestria.local_project_setup WHERE project_id=%s",
                (receipt.project_id,),
            )
            .fetchone()[1]
            .strip()
            == policy.sha256()
        )
        assert LocalSetupService().initialize(uow, request).replayed is True
        assert c.execute(
            "SELECT count(*) FROM panestria.project_policy_revision WHERE project_id=%s",
            (receipt.project_id,),
        ).fetchone() == (1,)
        # The actual Ask admission can use this scope; no inference or goal required.
        from panestria.contracts.ask import AskSubmission

        prepared = AskService().prepare(
            uow,
            request.actor(),
            AskSubmission(request_id=str(uuid4()), project_id=receipt.project_id, question="Ready?"),
        )
        assert prepared.inference.offline is True and prepared.inference.label == "RESTRICTED"


def test_setup_rolls_back_identity_policy_and_audit_together(r1_database):
    request = intent()
    with pytest.raises(RuntimeError, match="synthetic_commit_failure"), psycopg.connect(r1_database) as c:
        LocalSetupService().initialize(UnitOfWork(c), request)
        raise RuntimeError("synthetic_commit_failure")
    with psycopg.connect(r1_database) as c:
        assert c.execute("SELECT id FROM panestria.principal WHERE id=%s", (str(request.owner_id),)).fetchone() is None
        assert (
            c.execute(
                "SELECT project_id FROM panestria.local_project_setup WHERE project_id=%s", (str(request.project_id),)
            ).fetchone()
            is None
        )
        assert LocalSetupService().initialize(UnitOfWork(c), request).replayed is False


def test_concurrent_setup_creates_one_receipt(r1_database):
    request, barrier = intent(), Barrier(2)

    def run():
        barrier.wait(timeout=10)
        with psycopg.connect(r1_database) as c:
            return LocalSetupService().initialize(UnitOfWork(c), request)

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _: run(), range(2)))
    assert sorted(result.replayed for result in results) == [False, True]
    assert len({result.policy_ref for result in results}) == 1


def test_setup_cannot_claim_another_owners_project_or_replace_existing_policy(r1_task, tmp_path):
    request = LocalSetupIntent(owner_id=r1_task["owner"], project_id=r1_task["project"], intent="OFFLINE_ASK")
    stranger = intent().model_copy(update={"project_id": request.project_id})
    with psycopg.connect(r1_task["dsn"]) as c:
        uow = UnitOfWork(c)
        with pytest.raises(KernelDenied, match="^not_found$"), c.transaction():
            LocalSetupService().initialize(uow, stranger)
        policy = PolicyService(CertificateStore(tmp_path, {})).initialize(uow, request.actor(), r1_task["task"])
        with pytest.raises(KernelDenied, match="^local_setup_policy_conflict$"), c.transaction():
            LocalSetupService().initialize(uow, request)
        assert current_policy(uow, request.actor()) == policy
        assert (
            c.execute(
                "SELECT project_id FROM panestria.local_project_setup WHERE project_id=%s", (str(request.project_id),)
            ).fetchone()
            is None
        )


def test_setup_audit_is_immutable_and_binds_exact_scoped_policy(r1_database):
    request, other = intent(), intent()
    with psycopg.connect(r1_database) as c:
        receipt = LocalSetupService().initialize(UnitOfWork(c), request)
        LocalSetupService().initialize(UnitOfWork(c), other)
        for command in (
            "UPDATE panestria.local_project_setup SET intent='OFFLINE_ASK' WHERE project_id=%s",
            "DELETE FROM panestria.local_project_setup WHERE project_id=%s",
        ):
            with pytest.raises(psycopg.Error, match="immutable"), c.transaction():
                c.execute(command, (receipt.project_id,))
        c.execute("DELETE FROM panestria.local_project_setup WHERE false")
        with pytest.raises(psycopg.Error, match="local_setup_policy_mismatch"), c.transaction():
            c.execute(
                "INSERT INTO panestria.local_project_setup"
                " (project_id,owner_id,schema_version,intent,policy_version,policy_sha256)"
                " VALUES (%s,%s,1,'OFFLINE_ASK',1,%s)",
                (str(uuid4()), receipt.owner_id, "ff" * 32),
            )


def test_cli_setup_requires_explicit_intent_and_redacts_failures(r1_database, monkeypatch):
    request = intent()
    monkeypatch.setenv("PANESTRIA_DATABASE_URL", r1_database)
    args = ["local", "setup", "--owner-id", str(request.owner_id), "--project-id", str(request.project_id)]
    runner = CliRunner()
    denied = runner.invoke(app, args)
    assert denied.exit_code == 2 and json.loads(denied.output)["code"] == "offline_ask_intent_required"
    created = runner.invoke(app, [*args, "--offline-ask"])
    assert created.exit_code == 0, created.output
    assert json.loads(created.output)["replayed"] is False
    assert json.loads(runner.invoke(app, [*args, "--offline-ask"]).output)["replayed"] is True
    monkeypatch.setenv("PANESTRIA_DATABASE_URL", "postgresql://private-sentinel:private-sentinel@127.0.0.1:1/test")
    failed = runner.invoke(app, [*args, "--offline-ask"])
    assert failed.exit_code == 2 and json.loads(failed.output)["code"] == "database_unavailable"
    assert "private-sentinel" not in failed.output
    invalid = runner.invoke(app, [*args, "--owner-id", "private-sentinel", "--offline-ask"])
    assert invalid.exit_code == 2 and "private-sentinel" not in invalid.output


def test_setup_dump_restore_and_populated_downgrade_guard(r1_database):
    request = intent()
    with psycopg.connect(r1_database) as c:
        receipt = LocalSetupService().initialize(UnitOfWork(c), request)
    container = _fixture_container()
    dump = subprocess.run(
        ["docker", "exec", container, "pg_dump", "-U", "panestria_synthetic", "-d", "panestria_synthetic", "-Fc"],
        capture_output=True,
        check=True,
        timeout=60,
    )
    params = conninfo_to_dict(r1_database)
    params["dbname"] = "panestria_setup_restore_" + uuid4().hex
    with psycopg.connect(r1_database, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(params["dbname"])))
        try:
            restored = subprocess.run(
                ["docker", "exec", "-i", container, "pg_restore", "-U", "panestria_synthetic", "-d", params["dbname"]],
                input=dump.stdout,
                capture_output=True,
                timeout=60,
            )
            assert restored.returncode == 0, "synthetic_setup_restore_failed"
            with psycopg.connect(make_conninfo(**params)) as c:
                assert LocalSetupService().initialize(UnitOfWork(c), request) == receipt.__class__(
                    receipt.owner_id,
                    receipt.project_id,
                    receipt.policy_ref,
                    True,
                )
                grant_history = c.execute("SELECT EXISTS(SELECT 1 FROM panestria.connection_grant)").fetchone()[0]
            # Use URI form for Alembic, never show credentials in assertion output.
            restored_url = r1_database.rsplit("/", 1)[0] + "/" + params["dbname"]
            guarded = subprocess.run(
                ["uv", "run", "--frozen", "alembic", "-c", "migrations/alembic.ini", "downgrade", "0021_profile_ask"],
                env={**os.environ, "PANESTRIA_DATABASE_URL": restored_url},
                capture_output=True,
                text=True,
                timeout=30,
            )
            # The newest populated audit layer must stop downgrade first.
            # Verify the exact expected guard and unchanged setup/head below.
            expected_guard = "connection grant audit exists" if grant_history else "local setup audit exists"
            assert guarded.returncode != 0 and expected_guard in guarded.stderr
            with psycopg.connect(make_conninfo(**params)) as c:
                from panestria.api.local_server import SCHEMA_HEAD

                assert c.execute("SELECT version_num FROM alembic_version").fetchone() == (SCHEMA_HEAD,)
                assert LocalSetupService().initialize(UnitOfWork(c), request).replayed is True
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(params["dbname"])))
