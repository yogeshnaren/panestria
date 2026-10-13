"""Lease race and fencing on disposable PostgreSQL."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest

from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.leases import LeaseService
from panestria.kernel.tasks import TaskService
from panestria.kernel.uow import UnitOfWork


def test_lease_race_stale_epoch(r1_task: dict[str, str], record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-006-TC01")
    record_property("source_clauses", "AOS-006-F01,AOS-006-AC01")
    actor = Actor(r1_task["owner"], r1_task["project"])
    service = LeaseService()

    def race() -> str:
        try:
            with psycopg.connect(r1_task["dsn"]) as c:
                return service.acquire(UnitOfWork(c), actor, r1_task["task"], "mock", 0).attempt_id
        except KernelDenied as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        winners = list(pool.map(lambda _: race(), range(2)))
    assert winners.count("version_conflict") == 1
    attempt = next(value for value in winners if value != "version_conflict")
    with psycopg.connect(r1_task["dsn"]) as c:
        with pytest.raises(KernelDenied, match="not_found"), c.transaction():
            service.heartbeat(UnitOfWork(c), Actor(str(uuid4()), actor.project_id), attempt, 1)
        service.heartbeat(UnitOfWork(c), actor, attempt, 1, ttl_seconds=300)
        c.commit()
        c.execute(
            "UPDATE panestria.task_attempt SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=%s",
            (attempt,),
        )
        c.commit()
        with pytest.raises(KernelDenied, match="stale_lease"), c.transaction():
            service.heartbeat(UnitOfWork(c), actor, attempt, 1)
        with pytest.raises(KernelDenied, match="stale_lease"), c.transaction():
            TaskService().transition(
                UnitOfWork(c),
                actor,
                r1_task["task"],
                1,
                1,
                "VERIFYING",
                "done",
                policy_version="test-policy-v1",
                correlation_id=str(uuid4()),
            )
        _publication_denied(c, r1_task, attempt)
        next_lease = service.acquire(UnitOfWork(c), actor, r1_task["task"], "mock", 1)
        c.commit()
        assert next_lease.epoch == 2 and next_lease.attempt_number == 2
        assert c.execute("SELECT status,error_code FROM panestria.task_attempt WHERE id=%s", (attempt,)).fetchone() == (
            "LOST",
            "lease_expired",
        )
        _publication_denied(c, r1_task, attempt)
        with pytest.raises(KernelDenied, match="stale_lease"), c.transaction():
            service.require_current(UnitOfWork(c), actor, attempt, 1)
        service.release(UnitOfWork(c), actor, next_lease.attempt_id, next_lease.epoch)
        c.commit()
        with pytest.raises(KernelDenied, match="stale_lease"), c.transaction():
            service.require_current(UnitOfWork(c), actor, next_lease.attempt_id, 2)
        payload = c.execute(
            "SELECT payload FROM panestria.task_event WHERE task_id=%s AND kind='lease.released'", (r1_task["task"],)
        ).fetchone()
        assert payload is not None and payload[0]["external_cancellation_confirmed"] is False


def _publication_denied(c: psycopg.Connection[tuple[object, ...]], task: dict[str, str], attempt: str) -> None:
    with pytest.raises(psycopg.Error, match="stale attempt publication"), c.transaction():
        c.execute(
            "INSERT INTO panestria.artifact"
            " (id,task_id,attempt_id,kind,store_key,sha256,privacy_class,size_bytes)"
            " VALUES (%s,%s,%s,'test','test',%s,'RESTRICTED',1)",
            (str(uuid4()), task["task"], attempt, "ab" * 32),
        )
    with pytest.raises(psycopg.Error, match="stale attempt publication"), c.transaction():
        c.execute(
            "INSERT INTO panestria.check_run"
            " (id,acceptance_check_id,contract_id,task_id,attempt_id,verdict)"
            " VALUES (%s,%s,%s,%s,%s,'FAIL')",
            (str(uuid4()), task["check"], task["contract"], task["task"], attempt),
        )


def test_lease_acquisition_rolls_back_with_event(r1_task: dict[str, str]) -> None:
    with psycopg.connect(r1_task["dsn"]) as c:
        LeaseService().acquire(UnitOfWork(c), Actor(r1_task["owner"], r1_task["project"]), r1_task["task"], "mock", 0)
        c.rollback()
        assert c.execute(
            "SELECT state,row_version,lease_epoch FROM panestria.task WHERE id=%s", (r1_task["task"],)
        ).fetchone() == ("READY", 0, 0)
        assert c.execute(
            "SELECT count(*) FROM panestria.task_event WHERE task_id=%s", (r1_task["task"],)
        ).fetchone() == (0,)
        assert c.execute(
            "SELECT count(*) FROM panestria.task_attempt WHERE task_id=%s", (r1_task["task"],)
        ).fetchone() == (0,)


def test_lease_migration_roundtrip_preserves_r0_rows(r1_task: dict[str, str]) -> None:
    import os
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    for target in ("0004_check_candidate", "head"):
        result = subprocess.run(
            [
                "uv",
                "run",
                "--frozen",
                "alembic",
                "-c",
                "migrations/alembic.ini",
                "downgrade" if target != "head" else "upgrade",
                target,
            ],
            cwd=root,
            env={**os.environ, "PANESTRIA_DATABASE_URL": r1_task["dsn"]},
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        with psycopg.connect(r1_task["dsn"]) as c:
            assert c.execute("SELECT state FROM panestria.task WHERE id=%s", (r1_task["task"],)).fetchone() == (
                "READY",
            )
