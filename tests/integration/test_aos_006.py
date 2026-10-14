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


def _approved_intent(task: dict[str, str], *, classification: str = "reconcile-by-query") -> tuple[object, str]:
    import json
    from datetime import UTC, datetime, timedelta

    from panestria.contracts.approval import ActionPreview, effect_digest
    from panestria.contracts.effects import EffectIntent

    approval_id = str(uuid4())
    preview = ActionPreview(
        action_kind="merge",
        owner_id=task["owner"],
        project_id=task["project"],
        task_id=task["task"],
        contract_sha256="ab" * 32,
        contract_version=1,
        policy_version="test-policy-v1",
        destination="mock:pr",
        expected_base="base",
        candidate_sha256="cd" * 32,
        required_checks=["test"],
        minimum_actor_id=task["owner"],
        expires_at=(datetime.now(UTC) + timedelta(minutes=10)).isoformat(),
    )
    digest = effect_digest(preview)
    with psycopg.connect(task["dsn"]) as c:
        attempt, artifact = str(uuid4()), str(uuid4())
        c.execute(
            "INSERT INTO panestria.task_attempt(id,task_id,attempt_number,lease_epoch,status,adapter)"
            " VALUES (%s,%s,1,0,'SUCCEEDED','synthetic')",
            (attempt, task["task"]),
        )
        c.execute(
            "INSERT INTO panestria.artifact(id,task_id,attempt_id,kind,store_key,sha256,size_bytes)"
            " VALUES (%s,%s,%s,'test','test',%s,1)",
            (artifact, task["task"], attempt, "ef" * 32),
        )
        c.execute(
            "INSERT INTO panestria.check_run"
            " (id,acceptance_check_id,contract_id,task_id,attempt_id,verdict,evidence_artifact_id,candidate_sha256)"
            " VALUES (%s,%s,%s,%s,%s,'PASS',%s,%s)",
            (str(uuid4()), task["check"], task["contract"], task["task"], attempt, artifact, "cd" * 32),
        )
        c.execute(
            "INSERT INTO panestria.approval_request"
            " (id,goal_id,task_id,owner_id,project_id,minimum_actor_id,action_kind,effect_digest,policy_version,"
            " state,expires_at,decided_at,decided_by,preview)"
            " VALUES (%s,%s,%s,%s,%s,%s,'merge',%s,'test-policy-v1','APPROVED',%s,now(),%s,%s::jsonb)",
            (
                approval_id,
                task["goal"],
                task["task"],
                task["owner"],
                task["project"],
                task["owner"],
                digest,
                preview.expires_at,
                task["owner"],
                json.dumps(preview.model_dump()),
            ),
        )
    return EffectIntent(
        task_id=task["task"],
        effect_key="create-pr",
        target="mock:pr",
        request_ref=f"approval:{approval_id}",
        classification=classification,
        policy_version="test-policy-v1",
        effect_digest=digest,
    ), approval_id


def test_effect_response_loss(r1_task: dict[str, str], record_property: pytest.RecordProperty) -> None:
    from panestria.execution.outbox import Confirmed, EffectExecutor
    from panestria.kernel.effects import SideEffectService

    record_property("gate_case_id", "AOS-006-TC02")
    record_property("source_clauses", "AOS-006-F02,AOS-006-F03,AOS-006-AC02,AOS-006-AC03")
    actor = Actor(r1_task["owner"], r1_task["project"])
    intent, approval_id = _approved_intent(r1_task)
    service = SideEffectService()
    with psycopg.connect(r1_task["dsn"]) as c:
        ref = service.prepare(UnitOfWork(c), actor, intent, approval_id)
    with psycopg.connect(r1_task["dsn"]) as c:
        assert service.prepare(UnitOfWork(c), actor, intent, approval_id).replayed

    class Target:
        def __init__(self) -> None:
            self.created: dict[str, str] = {}
            self.calls = 0

        def dispatch(self, claim: object) -> str:
            self.calls += 1
            self.created[claim.fingerprint] = "mock-pr-1"
            raise TimeoutError("receipt was lost after successful creation")

        def query(self, claim: object) -> Confirmed:
            assert claim.fingerprint in self.created
            return Confirmed(self.created[claim.fingerprint])

    target = Target()
    executor = EffectExecutor(lambda: psycopg.connect(r1_task["dsn"]), target)
    executor.dispatch(actor, ref.effect_id)
    with pytest.raises(KernelDenied, match="effect_not_dispatchable"):
        executor.dispatch(actor, ref.effect_id)
    assert executor.reconcile(actor, ref.effect_id).state == "SUCCEEDED"
    assert target.calls == 1 and len(target.created) == 1
    with psycopg.connect(r1_task["dsn"]) as c:
        assert c.execute(
            "SELECT state,external_ref FROM panestria.side_effect WHERE id=%s", (ref.effect_id,)
        ).fetchone() == ("SUCCEEDED", "mock-pr-1")
        assert c.execute(
            "SELECT state FROM panestria.effect_outbox WHERE effect_id=%s", (ref.effect_id,)
        ).fetchone() == ("DONE",)


def test_approval_consume_and_unknown_effect(r1_task: dict[str, str], record_property: pytest.RecordProperty) -> None:
    from panestria.kernel.effects import SideEffectService

    record_property("gate_case_id", "AOS-006-TC03")
    record_property("source_clauses", "AOS-006-F02,AOS-006-F03,AOS-006-AC02,AOS-006-AC03")
    actor = Actor(r1_task["owner"], r1_task["project"])
    intent, approval_id = _approved_intent(r1_task, classification="non-retryable")
    service = SideEffectService()
    with psycopg.connect(r1_task["dsn"]) as c:
        with pytest.raises(KernelDenied, match="approval_mismatch"), c.transaction():
            service.prepare(UnitOfWork(c), actor, intent.model_copy(update={"target": "other"}), approval_id)
        ref = service.prepare(UnitOfWork(c), actor, intent, approval_id)
        c.commit()
        with pytest.raises(KernelDenied, match="approval_consumed"), c.transaction():
            service.prepare(UnitOfWork(c), actor, intent.model_copy(update={"effect_key": "another"}), approval_id)
        claim = service.claim(UnitOfWork(c), actor, ref.effect_id)
        c.commit()
        with pytest.raises(KernelDenied, match="dispatch_active"), c.transaction():
            service.begin_reconciliation(UnitOfWork(c), actor, ref.effect_id)
        service.finish(UnitOfWork(c), actor, claim, None)
        c.commit()
        reconciling = service.begin_reconciliation(UnitOfWork(c), actor, ref.effect_id)
        c.commit()
        assert service.reconciled(UnitOfWork(c), actor, reconciling, None).state == "RECONCILING"
        c.commit()
        with pytest.raises(KernelDenied, match="stale_dispatch"), c.transaction():
            service.finish(UnitOfWork(c), actor, claim, "late-receipt")
        with pytest.raises(KernelDenied, match="effect_not_dispatchable"), c.transaction():
            service.claim(UnitOfWork(c), actor, ref.effect_id)
        assert c.execute("SELECT state FROM panestria.task WHERE id=%s", (r1_task["task"],)).fetchone() == (
            "RECONCILING",
        )
        assert c.execute(
            "SELECT count(*) FROM panestria.approval_consumption WHERE approval_request_id=%s", (approval_id,)
        ).fetchone() == (1,)
        assert c.execute(
            "SELECT state FROM panestria.effect_outbox WHERE effect_id=%s", (ref.effect_id,)
        ).fetchone() == ("PAUSED",)


def test_retry_and_reservation_limits(r1_task: dict[str, str], record_property: pytest.RecordProperty) -> None:
    from panestria.kernel.budgets import BudgetService
    from panestria.kernel.retries import RetryService, retry_delay

    record_property("gate_case_id", "AOS-006-TC04")
    record_property("source_clauses", "AOS-006-F04,AOS-006-AC03")
    actor = Actor(r1_task["owner"], r1_task["project"])
    leases, retries, budgets = LeaseService(), RetryService(), BudgetService()
    with psycopg.connect(r1_task["dsn"]) as c:
        budgets.configure(UnitOfWork(c), actor, r1_task["task"], None)
        c.commit()
        with pytest.raises(KernelDenied, match="cash_cap_unknown"), c.transaction():
            budgets.reserve(UnitOfWork(c), actor, r1_task["task"], "unknown-cap", 1)
        with pytest.raises(KernelDenied, match="budget_not_authorized"), c.transaction():
            budgets.configure(UnitOfWork(c), actor, r1_task["task"], 1_000_001, expected_version=1)
        budgets.configure(UnitOfWork(c), actor, r1_task["task"], 1_000_000, expected_version=1)
        c.commit()
        with pytest.raises(KernelDenied, match="cost_unknown_approval_required"), c.transaction():
            budgets.reserve(UnitOfWork(c), actor, r1_task["task"], "unknown-cost", None)
        with pytest.raises(KernelDenied, match="invalid_money"), c.transaction():
            budgets.reserve(UnitOfWork(c), actor, r1_task["task"], "boolean", True)
        second_task = str(uuid4())
        c.execute(
            "INSERT INTO panestria.task(id,goal_id,contract_id,name,state) VALUES (%s,%s,%s,'other','READY')",
            (second_task, r1_task["goal"], r1_task["contract"]),
        )
        c.commit()

    def reserve(task_id: str) -> str:
        try:
            with psycopg.connect(r1_task["dsn"]) as c:
                return budgets.reserve(UnitOfWork(c), actor, task_id, task_id, 750_000).reservation_id
        except KernelDenied as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, [r1_task["task"], second_task]))
    assert results.count("cash_cap_exceeded") == 1
    reservation = next(value for value in results if value != "cash_cap_exceeded")
    with psycopg.connect(r1_task["dsn"]) as c:
        budgets.settle(UnitOfWork(c), actor, reservation, None)
        c.commit()
        with pytest.raises(KernelDenied, match="cash_cap_exceeded"), c.transaction():
            budgets.reserve(UnitOfWork(c), actor, r1_task["task"], "unknown-exposure", 250_001)
        with pytest.raises(KernelDenied, match="not_found"), c.transaction():
            budgets.settle(UnitOfWork(c), Actor(str(uuid4()), actor.project_id), reservation, 0)
        with pytest.raises(KernelDenied, match="reservation_exceeded"), c.transaction():
            budgets.settle(UnitOfWork(c), actor, reservation, 750_001)
        budgets.settle(UnitOfWork(c), actor, reservation, 400_000)
        c.commit()
        budgets.settle(UnitOfWork(c), actor, reservation, 400_000)  # exact duplicate is idempotent
        c.commit()
        new = budgets.reserve(UnitOfWork(c), actor, r1_task["task"], "remaining", 600_000)
        c.commit()
        assert budgets.reserve(UnitOfWork(c), actor, r1_task["task"], "remaining", 600_000).replayed
        c.commit()
        with pytest.raises(KernelDenied, match="idempotency_conflict"), c.transaction():
            budgets.reserve(UnitOfWork(c), actor, r1_task["task"], "remaining", 599_999)
        with pytest.raises(KernelDenied, match="cash_cap_exceeded"), c.transaction():
            budgets.reserve(UnitOfWork(c), actor, second_task, "one-more", 1)
        budgets.settle(UnitOfWork(c), actor, new.reservation_id, None, confirmed_no_effect=True)
        c.commit()
        for attempt_number in range(1, 4):
            version = c.execute("SELECT row_version FROM panestria.task WHERE id=%s", (r1_task["task"],)).fetchone()[0]
            lease = leases.acquire(UnitOfWork(c), actor, r1_task["task"], "mock", version)
            c.commit()
            assert lease.attempt_number == attempt_number
            retry_at = retries.schedule(
                UnitOfWork(c), actor, lease.attempt_id, lease.epoch, "rate_limited", jitter=0.5, retry_after_seconds=30
            )
            c.commit()
            if attempt_number < 3:
                assert retry_at is not None
                version = c.execute(
                    "SELECT row_version FROM panestria.task WHERE id=%s", (r1_task["task"],)
                ).fetchone()[0]
                with pytest.raises(KernelDenied, match="retry_not_due"), c.transaction():
                    leases.acquire(UnitOfWork(c), actor, r1_task["task"], "mock", version)
                c.execute(
                    "UPDATE panestria.task SET retry_at=clock_timestamp()-interval '1 second' WHERE id=%s",
                    (r1_task["task"],),
                )
                c.commit()
            else:
                assert retry_at is None
                assert c.execute("SELECT state FROM panestria.task WHERE id=%s", (r1_task["task"],)).fetchone() == (
                    "FAILED",
                )
            with pytest.raises(KernelDenied, match="stale_lease"), c.transaction():
                leases.require_current(UnitOfWork(c), actor, lease.attempt_id, lease.epoch)
        assert c.execute(
            "SELECT count(*) FROM panestria.task_attempt WHERE task_id=%s", (r1_task["task"],)
        ).fetchone() == (3,)
    assert all(1 <= retry_delay(number, jitter=1) <= 60 for number in range(1, 21))
    assert retry_delay(1, jitter=0, retry_after_seconds=30) == 30
    for jitter in (-1, 2, float("nan")):
        with pytest.raises(KernelDenied, match="invalid_retry"):
            retry_delay(1, jitter=jitter)


@pytest.mark.parametrize("failure", ["policy_denied", "auth_invalid", "invalid_scope", "unrecognized"])
def test_denials_do_not_retry(r1_task: dict[str, str], failure: str) -> None:
    from panestria.kernel.retries import RetryService

    actor = Actor(r1_task["owner"], r1_task["project"])
    with psycopg.connect(r1_task["dsn"]) as c:
        lease = LeaseService().acquire(UnitOfWork(c), actor, r1_task["task"], "mock", 0)
        c.commit()
        assert RetryService().schedule(UnitOfWork(c), actor, lease.attempt_id, lease.epoch, failure, jitter=0) is None
        c.commit()
        assert c.execute("SELECT state,retry_at FROM panestria.task WHERE id=%s", (r1_task["task"],)).fetchone() == (
            "FAILED",
            None,
        )
