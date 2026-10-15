"""Real PostgreSQL request integrity; no fetch/source/citation authority."""

import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from test_memory_restore import _fixture_container

from panestria.contracts.research import ResearchArtifactRef, ResearchLimits, ResearchRequestRecord, ResearchScope
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.research_requests import ResearchRequestService
from panestria.kernel.uow import UnitOfWork

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def research(r1_task):
    # New database inside our disposable R1 fixture, not the shared audit history.
    name = "panestria_research_" + uuid4().hex
    dsn = r1_task["dsn"].rsplit("/", 1)[0] + "/" + name
    with psycopg.connect(r1_task["dsn"], autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            migration = subprocess.run(
                [str(ROOT / ".venv/bin/alembic"), "-c", "migrations/alembic.ini", "upgrade", "head"],
                cwd=ROOT,
                env={**os.environ, "PANESTRIA_DATABASE_URL": dsn},
                capture_output=True,
                timeout=30,
            )
            assert migration.returncode == 0, "isolated research migration failed"
            with psycopg.connect(dsn) as c:
                c.execute(
                    "INSERT INTO panestria.principal(id,display_name) VALUES (%s,'synthetic research')",
                    (r1_task["owner"],),
                )
                c.execute(
                    "INSERT INTO panestria.project(id,owner_id) VALUES (%s,%s)", (r1_task["project"], r1_task["owner"])
                )
                c.execute(
                    "INSERT INTO panestria.goal(id,owner_id,project_id,intent,status) "
                    "VALUES (%s,%s,%s,'test','ACTIVE')",
                    (r1_task["goal"], r1_task["owner"], r1_task["project"]),
                )
                c.execute(
                    "INSERT INTO panestria.goal_contract(id,goal_id,version,body,sha256) "
                    "VALUES (%s,%s,1,'{}',repeat('ab',32))",
                    (r1_task["contract"], r1_task["goal"]),
                )
                c.execute(
                    "INSERT INTO panestria.task(id,goal_id,contract_id,name,state) "
                    "VALUES (%s,%s,%s,'research','READY')",
                    (r1_task["task"], r1_task["goal"], r1_task["contract"]),
                )
                artifact = str(uuid4())
                c.execute(
                    "INSERT INTO panestria.artifact(id,task_id,kind,store_key,sha256,privacy_class,size_bytes) "
                    "VALUES (%s,%s,'question','synthetic-not-actual-blob',%s,'INTERNAL',4)",
                    (artifact, r1_task["task"], "ab" * 32),
                )
            scope = ResearchScope(**{key + "_id": r1_task[key] for key in ("owner", "project", "goal", "task")})
            request = ResearchRequestRecord(
                request_id=str(uuid4()),
                scope=scope,
                question=ResearchArtifactRef(
                    artifact_id=artifact,
                    task_id=scope.task_id,
                    sha256="ab" * 32,
                    size_bytes=4,
                    privacy_label="INTERNAL",
                ),
                limits=ResearchLimits(),
            )
            yield dsn, Actor(scope.owner_id, scope.project_id), request
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def test_request_commits_one_immutable_receipt_and_event_and_retries(research):
    dsn, actor, request = research
    with psycopg.connect(dsn) as c:
        receipt = ResearchRequestService().prepare(UnitOfWork(c), actor, request)
    with psycopg.connect(dsn) as c:
        repeated = ResearchRequestService().prepare(UnitOfWork(c), actor, request)
        assert repeated.replayed and repeated.seq == receipt.seq and repeated.request_sha256 == receipt.request_sha256
        events = c.execute(
            "SELECT seq,payload FROM panestria.task_event WHERE kind='research.request.prepared'"
        ).fetchall()
        assert len(events) == 1 and events[0][0] > receipt.seq
        assert events[0][1] == {"request_id": request.request_id, "request_sha256": receipt.request_sha256}
        assert c.execute("SELECT count(*) FROM panestria.research_request").fetchone() == (1,)
        assert c.execute("SELECT count(*) FROM panestria.worker_invocation").fetchone() == (0,)
        for statement in (
            "UPDATE panestria.research_request SET max_sources=2",
            "DELETE FROM panestria.research_request",
            "UPDATE panestria.artifact SET sha256=repeat('cd',32)",
            "DELETE FROM panestria.artifact",
        ):
            with pytest.raises(psycopg.Error), c.transaction():
                c.execute(statement)


def test_request_and_event_rollback_together(research):
    dsn, actor, request = research
    with pytest.raises(RuntimeError, match="synthetic failure"), psycopg.connect(dsn) as c:
        ResearchRequestService().prepare(UnitOfWork(c), actor, request)
        raise RuntimeError("synthetic failure")
    with psycopg.connect(dsn) as c:
        assert c.execute("SELECT count(*) FROM panestria.research_request").fetchone() == (0,)
        assert c.execute("SELECT count(*) FROM panestria.task_event").fetchone() == (0,)


@pytest.mark.parametrize(
    "change", [{"sha256": "cd" * 32}, {"size_bytes": 5}, {"artifact_id": str(uuid4())}, {"privacy_label": "PUBLIC"}]
)
def test_question_metadata_cannot_be_forged(research, change):
    dsn, actor, request = research
    question = request.question.model_copy(update=change)
    with pytest.raises(KernelDenied, match="research_artifact_or_scope_mismatch"), psycopg.connect(dsn) as c:
        ResearchRequestService().prepare(UnitOfWork(c), actor, request.model_copy(update={"question": question}))


def test_owner_and_task_scope_deny_and_changed_retry_conflicts(research):
    dsn, actor, request = research
    with psycopg.connect(dsn) as c:
        with pytest.raises(KernelDenied, match="not_found"), c.transaction():
            ResearchRequestService().prepare(UnitOfWork(c), Actor(str(uuid4()), actor.project_id), request)
        with pytest.raises(KernelDenied, match="not_found"), c.transaction():
            wrong = request.scope.model_copy(update={"goal_id": str(uuid4())})
            ResearchRequestService().prepare(UnitOfWork(c), actor, request.model_copy(update={"scope": wrong}))
        ResearchRequestService().prepare(UnitOfWork(c), actor, request)
        with pytest.raises(KernelDenied, match="research_request_conflict"), c.transaction():
            ResearchRequestService().prepare(
                UnitOfWork(c), actor, request.model_copy(update={"limits": ResearchLimits(max_sources=2)})
            )
        with pytest.raises(KernelDenied, match="invalid_research_request"), c.transaction():
            ResearchRequestService().prepare(UnitOfWork(c), actor, request.model_copy(update={"schema_version": True}))


def test_concurrent_retry_returns_one_receipt_and_one_event(research):
    dsn, actor, request = research
    barrier = Barrier(2)

    def prepare(_):
        barrier.wait(timeout=10)
        with psycopg.connect(dsn) as c:
            return ResearchRequestService().prepare(UnitOfWork(c), actor, request)

    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(prepare, range(2)))
    assert sorted(r.replayed for r in receipts) == [False, True]
    assert len({r.seq for r in receipts}) == 1
    with psycopg.connect(dsn) as c:
        assert c.execute("SELECT count(*) FROM panestria.task_event").fetchone() == (1,)


def test_database_enforces_limits_without_service_and_guard_preserves_receipt(research):
    dsn, actor, request = research
    with psycopg.connect(dsn) as c:
        ResearchRequestService().prepare(UnitOfWork(c), actor, request)
        for column, value in (
            ("max_sources", 0),
            ("max_source_bytes", 2097153),
            ("max_total_bytes", 1),
            ("max_redirects", 6),
            ("deadline_seconds", "NaN"),
        ):
            # Immutable row update denies independently too; insert a distinct row
            # via JSON reconstruction to exercise column constraints themselves.
            row = c.execute("SELECT to_jsonb(r) FROM panestria.research_request r").fetchone()[0]
            row.update(id=str(uuid4()), seq=100000)
            row[column] = value
            with pytest.raises(psycopg.errors.CheckViolation), c.transaction():
                c.execute(
                    "INSERT INTO panestria.research_request SELECT "
                    "(jsonb_populate_record(NULL::panestria.research_request,%s::jsonb)).*",
                    (json.dumps(row, default=str),),
                )
    before = subprocess.run(
        [str(ROOT / ".venv/bin/alembic"), "-c", "migrations/alembic.ini", "downgrade", "0022_local_setup"],
        cwd=ROOT,
        env={**os.environ, "PANESTRIA_DATABASE_URL": dsn},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert before.returncode != 0 and "research request audit exists" in before.stderr
    with psycopg.connect(dsn) as c:
        assert c.execute("SELECT version_num FROM alembic_version").fetchone() == ("0023_research_request",)
        assert ResearchRequestService().prepare(UnitOfWork(c), actor, request).replayed


def test_sql_foreign_scope_cannot_bypass_kernel(research):
    dsn, actor, request = research
    with psycopg.connect(dsn) as c:
        ResearchRequestService().prepare(UnitOfWork(c), actor, request)
        for column in ("owner_id", "project_id", "goal_id", "task_id"):
            row = c.execute("SELECT to_jsonb(r) FROM panestria.research_request r").fetchone()[0]
            row.update(id=str(uuid4()), seq=100000)
            row[column] = str(uuid4())
            with pytest.raises(psycopg.errors.ForeignKeyViolation), c.transaction():
                c.execute(
                    "INSERT INTO panestria.research_request SELECT "
                    "(jsonb_populate_record(NULL::panestria.research_request,%s::jsonb)).*",
                    (json.dumps(row, default=str),),
                )


def test_actual_dump_restore_preserves_receipts_events_and_global_sequence(research):
    dsn, actor, request = research
    with psycopg.connect(dsn) as c:
        receipt = ResearchRequestService().prepare(UnitOfWork(c), actor, request)
    container = _fixture_container()
    source_name = dsn.rsplit("/", 1)[1]
    backup = subprocess.run(
        ["docker", "exec", container, "pg_dump", "-U", "panestria_synthetic", "-d", source_name, "-Fc"],
        capture_output=True,
        check=True,
        timeout=30,
    )
    name = "panestria_research_restore_" + uuid4().hex
    restored_dsn = dsn.rsplit("/", 1)[0] + "/" + name
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            restored = subprocess.run(
                ["docker", "exec", "-i", container, "pg_restore", "-U", "panestria_synthetic", "-d", name],
                input=backup.stdout,
                capture_output=True,
                timeout=30,
            )
            assert restored.returncode == 0, "research restore failed"
            with psycopg.connect(restored_dsn) as c:
                retry = ResearchRequestService().prepare(UnitOfWork(c), actor, request)
                assert retry.replayed and retry.seq == receipt.seq
                assert c.execute("SELECT count(*) FROM panestria.task_event").fetchone() == (1,)
                next_request = request.model_copy(update={"request_id": str(uuid4())})
                following = ResearchRequestService().prepare(UnitOfWork(c), actor, next_request)
                assert following.seq > receipt.seq and not following.replayed
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def test_upgrade_preserves_existing_artifact_and_empty_downgrade_reapplies(research):
    dsn, _, _ = research
    with psycopg.connect(dsn) as c:
        before = c.execute("SELECT to_jsonb(a) FROM panestria.artifact a").fetchall()
    for direction, revision in (("downgrade", "0022_local_setup"), ("upgrade", "head")):
        result = subprocess.run(
            [str(ROOT / ".venv/bin/alembic"), "-c", "migrations/alembic.ini", direction, revision],
            cwd=ROOT,
            env={**os.environ, "PANESTRIA_DATABASE_URL": dsn},
            capture_output=True,
            timeout=30,
        )
        assert result.returncode == 0, "empty research migration failed"
        with psycopg.connect(dsn) as c:
            assert c.execute("SELECT to_jsonb(a) FROM panestria.artifact a").fetchall() == before
