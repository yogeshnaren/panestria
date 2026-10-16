"""Actual PostgreSQL transactions, source lanes and independent window interpretation."""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import uuid4

import psycopg
import pytest

from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.quota import QuotaService
from panestria.kernel.uow import UnitOfWork
from quota_support import observation


@pytest.fixture
def quota(r1_task):
    return r1_task, Actor(r1_task["owner"], r1_task["project"]), QuotaService()


def record(quota, value, *, unit=UnitOfWork):
    task, actor, service = quota
    with psycopg.connect(task["dsn"]) as c:
        return service.record(unit(c), actor, task["task"], value)


def latest(quota, scope):
    task, actor, service = quota
    with psycopg.connect(task["dsn"]) as c:
        return service.latest(UnitOfWork(c), actor, scope)


def test_actual_owner_report_roundtrip_replay_and_nullable_unknown(quota):
    task, actor, service = quota
    body = observation()
    first, replay = record(quota, body), record(quota, body)
    assert first.authority == "OBSERVATION_ONLY" and not first.replayed and replay.replayed
    assert first.effective_remaining == "40" and first.confidence == "REPORTED"
    assert first.recorded_at == replay.recorded_at
    with psycopg.connect(task["dsn"]) as c:
        assert service.read(UnitOfWork(c), actor, body.observation_id).observation == body
        rows = c.execute("SELECT kind,payload FROM panestria.task_event WHERE task_id=%s", (task["task"],)).fetchall()
        assert [row[0] for row in rows] == ["quota.observed"]
        assert body.scope.account_ref not in json.dumps(rows)
        assert set(rows[0][1]) == {"observation_id", "body_sha256"}
        assert c.execute(
            "SELECT count(*) FROM panestria.budget_reservation WHERE task_id=%s", (task["task"],)
        ).fetchone() == (0,)
        assert c.execute(
            "SELECT count(*) FROM panestria.worker_invocation WHERE task_id=%s", (task["task"],)
        ).fetchone() == (0,)
    with pytest.raises(KernelDenied, match="quota_observation_conflict"):
        record(quota, observation(**{**body.model_dump(mode="json"), "remaining": "41"}))
    unknown = observation(scope=body.scope.model_dump(), remaining=None, observed_at=datetime.now(UTC).isoformat())
    record(quota, unknown)
    view = latest(quota, body.scope)
    assert len(view) == 1 and view[0].observation.observation_id == unknown.observation_id
    assert view[0].effective_remaining is None and view[0].confidence == "UNKNOWN"


@pytest.mark.parametrize("source", ["PROVIDER_REPORTED", "ESTIMATED", "UNKNOWN"])
def test_trusted_ingestion_lanes_retain_source_and_hash_without_a_provider_claim(quota, source):
    owner = observation()
    record(quota, owner)
    value = observation(
        scope=owner.scope.model_dump(),
        source=source,
        remaining=None if source == "UNKNOWN" else "12.5",
        source_sha256="ab" * 32 if source != "UNKNOWN" else None,
    )
    # Synthetic inputs exercise provenance preservation, not an actual collector.
    record(quota, value)
    lanes = latest(quota, owner.scope)
    assert {v.observation.source for v in lanes} == {source, "OWNER_REPORTED"}
    assert all(v.authority == "OBSERVATION_ONLY" for v in lanes)
    found = next(v for v in lanes if v.observation.source == source)
    assert found.confidence == (
        "UNKNOWN" if source == "UNKNOWN" else "ESTIMATED" if source == "ESTIMATED" else "REPORTED"
    )


def test_late_reports_do_not_replace_newer_observed_time_and_windows_do_not_mix(quota):
    fresh = observation()
    record(quota, fresh)
    old = observation(
        scope=fresh.scope.model_dump(),
        remaining="100",
        observed_at=(fresh.observed_at - timedelta(hours=1)).isoformat(),
    )
    record(quota, old)
    weekly = observation(scope={**fresh.scope.model_dump(), "window_ref": "weekly"}, remaining="0")
    model = observation(scope={**fresh.scope.model_dump(), "model_ref": "haiku-4.5"}, remaining="1")
    account = observation()
    for value in (weekly, model, account):
        record(quota, value)
    assert latest(quota, fresh.scope)[0].observation == fresh
    assert latest(quota, weekly.scope)[0].effective_remaining == "0"
    assert latest(quota, model.scope)[0].observation == model
    assert latest(quota, account.scope)[0].observation == account


@pytest.mark.parametrize("kind", ["STALE", "RESET_PASSED"])
def test_stale_reset_and_replay_preserve_report_but_expose_unknown_capacity(quota, kind):
    now = datetime.now(UTC)
    body = observation(
        observed_at=(now - timedelta(seconds=20)).isoformat(),
        resets_at=(now + timedelta(days=1) if kind == "STALE" else now - timedelta(seconds=1)).isoformat(),
        fresh_for_seconds=1 if kind == "STALE" else 900,
    )
    view = record(quota, body)
    assert view.freshness == kind and view.effective_remaining is None and view.confidence == "UNKNOWN"
    assert view.observation.remaining == "40" and record(quota, body).freshness == kind


def test_actual_server_time_expiry_without_mutating_the_observation(quota):
    body = observation(observed_at=datetime.now(UTC).isoformat(), fresh_for_seconds=1)
    assert record(quota, body).freshness == "FRESH"
    time.sleep(1.05)
    view = latest(quota, body.scope)[0]
    assert view.freshness == "STALE" and view.effective_remaining is None and view.observation == body


def test_future_and_wrong_scope_records_are_denied_before_event(quota):
    task, actor, service = quota
    future = observation(observed_at=(datetime.now(UTC) + timedelta(hours=1)).isoformat())
    with pytest.raises(KernelDenied, match="quota_observed_in_future"):
        record(quota, future)
    good = observation()
    record(quota, good)
    for wrong in (Actor(str(uuid4()), actor.project_id), Actor(actor.owner_id, str(uuid4()))):
        with psycopg.connect(task["dsn"]) as c:
            with pytest.raises(KernelDenied, match="not_found"):
                service.read(UnitOfWork(c), wrong, good.observation_id)
            assert service.latest(UnitOfWork(c), wrong, good.scope) == ()
            with pytest.raises(KernelDenied, match="not_found"):
                service.record(UnitOfWork(c), wrong, task["task"], observation())
    with psycopg.connect(task["dsn"]) as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.quota_observation WHERE owner_id=%s", (actor.owner_id,)
        ).fetchone() == (1,)


def test_transaction_rollback_and_autocommit_never_leave_phantom_observations(quota):
    task, actor, service = quota
    body = observation()
    with psycopg.connect(task["dsn"]) as c:
        with pytest.raises(RuntimeError), c.transaction():
            service.record(UnitOfWork(c), actor, task["task"], body)
            raise RuntimeError("injected_before_commit")
        assert c.execute(
            "SELECT count(*) FROM panestria.quota_observation WHERE id=%s", (body.observation_id,)
        ).fetchone() == (0,)
        assert c.execute("SELECT count(*) FROM panestria.task_event WHERE task_id=%s", (task["task"],)).fetchone() == (
            0,
        )
    with psycopg.connect(task["dsn"], autocommit=True) as c:
        with pytest.raises(KernelDenied, match="quota_caller_transaction_required"):
            service.record(UnitOfWork(c), actor, task["task"], body)
        with c.transaction():
            assert not service.record(UnitOfWork(c), actor, task["task"], body).replayed


def test_concurrent_identical_reports_append_one_event_and_changed_body_conflicts(quota):
    barrier, body = Barrier(2), observation()

    def submit(_):
        barrier.wait(timeout=5)
        return record(quota, body).replayed

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(submit, range(2))) == [False, True]
    task, _, _ = quota
    with psycopg.connect(task["dsn"]) as c:
        assert c.execute("SELECT count(*) FROM panestria.task_event WHERE task_id=%s", (task["task"],)).fetchone() == (
            1,
        )


def test_immutable_db_rows_and_hash_corruption_are_rejected(quota):
    task, actor, service = quota
    body = observation()
    record(quota, body)
    with psycopg.connect(task["dsn"]) as c:
        for query in (
            "UPDATE panestria.quota_observation SET body=body WHERE id=%s",
            "DELETE FROM panestria.quota_observation WHERE id=%s",
        ):
            with pytest.raises(psycopg.Error, match="immutable"), c.transaction():
                c.execute(query, (body.observation_id,))
        with pytest.raises(RuntimeError), c.transaction():
            c.execute("ALTER TABLE panestria.quota_observation DISABLE TRIGGER immutable_quota_observation")
            c.execute(
                "UPDATE panestria.quota_observation SET body_sha256=%s WHERE id=%s", ("00" * 32, body.observation_id)
            )
            with pytest.raises(KernelDenied, match="quota_observation_corrupt"):
                service.read(UnitOfWork(c), actor, body.observation_id)
            raise RuntimeError("rollback_test_corruption_and_trigger_state")
    assert latest(quota, body.scope)[0].observation == body


def test_entity_write_precedes_global_event_lock_and_event_failure_rolls_back(quota):
    task, actor, service = quota

    class EventLast(UnitOfWork):
        locked = False

        def execute(self, query, params=()):
            if "pg_advisory_xact_lock" in query:
                self.locked = True
            if query.startswith("INSERT") and "task_event" not in query:
                assert not self.locked
            return super().execute(query, params)

    record(quota, observation(), unit=EventLast)

    class EventFailure(UnitOfWork):
        def execute(self, query, params=()):
            if "INSERT INTO panestria.task_event" in query:
                raise RuntimeError("injected_event_failure")
            return super().execute(query, params)

    body = observation()
    with pytest.raises(RuntimeError, match="injected_event_failure"):
        record(quota, body, unit=EventFailure)
    with psycopg.connect(task["dsn"]) as c:
        with pytest.raises(KernelDenied, match="not_found"):
            service.read(UnitOfWork(c), actor, body.observation_id)


def test_same_global_id_racing_between_projects_has_one_scoped_winner(quota):
    task, actor, service = quota
    other = {name: str(uuid4()) for name in ("project", "goal", "contract", "task")}
    second = Actor(actor.owner_id, other["project"])
    with psycopg.connect(task["dsn"]) as c:
        c.execute("INSERT INTO panestria.project(id,owner_id) VALUES (%s,%s)", (other["project"], actor.owner_id))
        c.execute(
            "INSERT INTO panestria.goal(id,owner_id,project_id,intent,status) "
            "VALUES (%s,%s,%s,'quota fixture','ACTIVE')",
            (other["goal"], actor.owner_id, other["project"]),
        )
        c.execute(
            "INSERT INTO panestria.goal_contract(id,goal_id,version,body,sha256) VALUES (%s,%s,1,'{}',%s)",
            (other["contract"], other["goal"], "ab" * 32),
        )
        c.execute(
            "INSERT INTO panestria.task(id,goal_id,contract_id,name,state) VALUES (%s,%s,%s,'quota fixture','READY')",
            (other["task"], other["goal"], other["contract"]),
        )
    barrier, body = Barrier(2), observation()

    class CrossProject(UnitOfWork):
        def execute(self, query, params=()):
            if "INSERT INTO panestria.quota_observation" in query:
                barrier.wait(timeout=5)
            return super().execute(query, params)

    def submit(item):
        who, identifier = item
        try:
            with psycopg.connect(task["dsn"]) as c:
                service.record(CrossProject(c), who, identifier, body)
            return who.project_id
        except KernelDenied as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, [(actor, task["task"]), (second, other["task"])]))
    assert results.count("quota_observation_conflict") == 1
    for who in (actor, second):
        with psycopg.connect(task["dsn"]) as c:
            if who.project_id in results:
                assert service.read(UnitOfWork(c), who, body.observation_id).observation == body
            else:
                with pytest.raises(KernelDenied, match="not_found"):
                    service.read(UnitOfWork(c), who, body.observation_id)
