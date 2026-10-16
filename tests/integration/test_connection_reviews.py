"""Actual PG declaration/owner-review boundaries; no live connector or permission is minted."""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import uuid4

import psycopg
import pytest

from connection_support import manifest, proposal
from panestria.kernel.connections import ConnectionReviewService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.policy import PolicyService
from panestria.kernel.repositories.policy import active_policy_ref
from panestria.kernel.uow import UnitOfWork
from panestria.policy.profiles import CertificateStore


@pytest.fixture
def configured(r1_task, tmp_path):
    actor = Actor(r1_task["owner"], r1_task["project"])
    with psycopg.connect(r1_task["dsn"]) as c:
        PolicyService(CertificateStore(tmp_path, {})).initialize(UnitOfWork(c), actor, r1_task["task"])
    with psycopg.connect(r1_task["dsn"]) as c:
        policy = active_policy_ref(UnitOfWork(c), actor.owner_id, actor.project_id)
    return r1_task, actor, policy, ConnectionReviewService()


def request(configured, **changes):
    task, actor, policy, _ = configured
    return proposal(policy, manifest(actor.owner_id, actor.project_id), **changes)


def prepare(configured, change):
    task, actor, _, service = configured
    with psycopg.connect(task["dsn"]) as c:
        return service.propose(UnitOfWork(c), actor, task["task"], change)


def decide(configured, review, decision="approve"):
    task, actor, _, service = configured
    with psycopg.connect(task["dsn"]) as c:
        return service.decide(UnitOfWork(c), actor, review.proposal_id, review.effect_digest, decision)


def current(configured, identifier):
    task, actor, _, service = configured
    with psycopg.connect(task["dsn"]) as c:
        return service.current(UnitOfWork(c), actor, identifier)


def test_exact_owner_preview_approval_and_replays_are_declarations_only(configured):
    task, actor, _, service = configured
    change = request(configured)
    review = prepare(configured, change)
    with psycopg.connect(task["dsn"]) as c:
        assert service.preview(UnitOfWork(c), actor, review.proposal_id).state == "PENDING"
        with pytest.raises(KernelDenied, match="connection_not_declared"), c.transaction():
            service.current(UnitOfWork(c), actor, review.grant_id)
        with pytest.raises(KernelDenied, match="digest_mismatch"), c.transaction():
            service.decide(UnitOfWork(c), actor, review.proposal_id, "00" * 32, "approve")
        for who in (Actor(str(uuid4()), actor.project_id), Actor(actor.owner_id, str(uuid4()))):
            with pytest.raises(KernelDenied, match="not_found"), c.transaction():
                service.preview(UnitOfWork(c), who, review.proposal_id)
    receipt = decide(configured, review)
    declared = current(configured, review.grant_id)
    assert receipt.granted_version == 1 and receipt.authority == "DECLARATION_ONLY"
    assert declared.state == "DECLARED_ACTIVE" and declared.conformance_status == "UNVERIFIED"
    assert declared.manifest.conformance_sha256 is not None and declared.authority == "DECLARATION_ONLY"
    assert prepare(configured, change).replayed and decide(configured, review).replayed
    with pytest.raises(KernelDenied, match="decision_conflict"):
        decide(configured, review, "deny")
    with psycopg.connect(task["dsn"]) as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.connection_grant_decision WHERE review_id=%s", (review.proposal_id,)
        ).fetchone() == (1,)
        events = c.execute(
            "SELECT kind,payload FROM panestria.task_event WHERE task_id=%s AND kind LIKE 'connection.%%' ORDER BY seq",
            (task["task"],),
        ).fetchall()
        assert [row[0] for row in events] == ["connection.review_requested", "connection.review_decided"]
        assert "example.com" not in json.dumps(events) and "account_ref" not in json.dumps(events)


def test_denial_never_creates_a_current_revision(configured):
    review = prepare(configured, request(configured))
    receipt = decide(configured, review, "deny")
    assert receipt.decision == "DENIED" and receipt.granted_version is None
    assert decide(configured, review, "deny").replayed
    with pytest.raises(KernelDenied, match="connection_not_declared"):
        current(configured, review.grant_id)


def test_replace_and_revoke_preserve_old_revisions_and_historical_receipts(configured):
    task, actor, policy, _ = configured
    first = prepare(configured, request(configured))
    decide(configured, first)
    narrower = manifest(actor.owner_id, actor.project_id, actions=("read",), origins=("https://other.example.com",))
    second = prepare(configured, proposal(policy, narrower, grant_id=first.grant_id, expected_version=1))
    assert current(configured, first.grant_id).version == 1
    decide(configured, second)
    assert current(configured, first.grant_id).manifest.sha256() == narrower.sha256()
    revoke = prepare(
        configured, proposal(policy, None, grant_id=first.grant_id, expected_version=2, operation="REVOKE")
    )
    assert revoke.manifest.sha256() == narrower.sha256()
    decide(configured, revoke)
    declared = current(configured, first.grant_id)
    assert declared.state == "DECLARED_REVOKED" and declared.version == 3
    assert decide(configured, first).replayed and current(configured, first.grant_id).version == 3
    with pytest.raises(KernelDenied, match="connection_already_revoked"):
        prepare(configured, proposal(policy, None, grant_id=first.grant_id, expected_version=3, operation="REVOKE"))
    with psycopg.connect(task["dsn"]) as c:
        assert c.execute(
            "SELECT operation FROM panestria.connection_grant_revision WHERE grant_id=%s ORDER BY version",
            (first.grant_id,),
        ).fetchall() == [("REPLACE",), ("REPLACE",), ("REVOKE",)]


def test_changed_replay_scope_policy_and_version_cannot_self_approve(configured):
    task, actor, policy, service = configured
    change = request(configured)
    review = prepare(configured, change)
    changed = change.model_copy(update={"manifest": manifest(actor.owner_id, actor.project_id, actions=("read",))})
    with pytest.raises(KernelDenied, match="connection_proposal_conflict"):
        prepare(configured, changed)
    wrong = change.model_copy(
        update={"proposal_id": str(uuid4()), "manifest": manifest(str(uuid4()), actor.project_id)}
    )
    with pytest.raises(KernelDenied, match="not_found"):
        prepare(configured, wrong)
    with pytest.raises(KernelDenied, match="policy_mismatch"):
        prepare(
            configured,
            change.model_copy(update={"proposal_id": str(uuid4()), "policy_ref": "project-policy:1:" + "00" * 32}),
        )
    with psycopg.connect(task["dsn"]) as c:
        for who in (Actor(str(uuid4()), actor.project_id), Actor(actor.owner_id, str(uuid4()))):
            with pytest.raises(KernelDenied, match="not_found"), c.transaction():
                service.decide(UnitOfWork(c), who, review.proposal_id, review.effect_digest, "approve")
    decide(configured, review)
    with pytest.raises(KernelDenied, match="connection_version_conflict"):
        prepare(configured, proposal(policy, review.manifest, grant_id=review.grant_id, expected_version=0))


def test_actual_short_review_expiry_blocks_new_decisions(configured):
    task, actor, _, _ = configured
    service = ConnectionReviewService(review_seconds=1)
    with psycopg.connect(task["dsn"]) as c:
        review = service.propose(UnitOfWork(c), actor, task["task"], request(configured))
    time.sleep(1.05)
    with psycopg.connect(task["dsn"]) as c:
        assert service.preview(UnitOfWork(c), actor, review.proposal_id).state == "EXPIRED"
        with pytest.raises(KernelDenied, match="connection_review_expired"), c.transaction():
            service.decide(UnitOfWork(c), actor, review.proposal_id, review.effect_digest, "approve")


def test_caller_rollback_and_autocommit_guard_preserve_atomicity(configured):
    task, actor, _, service = configured
    change = request(configured)
    with psycopg.connect(task["dsn"], autocommit=True) as c:
        with pytest.raises(KernelDenied, match="connection_caller_transaction_required"):
            service.propose(UnitOfWork(c), actor, task["task"], change)
        with pytest.raises(RuntimeError), c.transaction():
            service.propose(UnitOfWork(c), actor, task["task"], change)
            raise RuntimeError("synthetic rollback")
        assert c.execute(
            "SELECT count(*) FROM panestria.connection_grant_review WHERE id=%s", (change.proposal_id,)
        ).fetchone() == (0,)
    review = prepare(configured, change)
    with psycopg.connect(task["dsn"], autocommit=True) as c:
        with pytest.raises(KernelDenied, match="connection_caller_transaction_required"):
            service.decide(UnitOfWork(c), actor, review.proposal_id, review.effect_digest, "approve")
        with pytest.raises(RuntimeError), c.transaction():
            service.decide(UnitOfWork(c), actor, review.proposal_id, review.effect_digest, "approve")
            raise RuntimeError("synthetic rollback")
    with pytest.raises(KernelDenied, match="connection_not_declared"):
        current(configured, review.grant_id)


def test_concurrent_proposals_and_decisions_have_one_atomic_winner(configured):
    change = request(configured)
    with ThreadPoolExecutor(max_workers=2) as pool:
        initial = list(pool.map(lambda _: prepare(configured, change), range(2)))
    assert sorted(r.replayed for r in initial) == [False, True] and len({r.grant_id for r in initial}) == 1
    with ThreadPoolExecutor(max_workers=2) as pool:
        decisions = list(pool.map(lambda _: decide(configured, initial[0]), range(2)))
    assert sorted(r.replayed for r in decisions) == [False, True]
    task, actor, policy, _ = configured
    reviews = [
        prepare(
            configured,
            proposal(
                policy, manifest(actor.owner_id, actor.project_id), grant_id=initial[0].grant_id, expected_version=1
            ),
        )
        for _ in range(2)
    ]

    def race(review):
        try:
            return decide(configured, review).granted_version
        except KernelDenied as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        winners = list(pool.map(race, reviews))
    assert winners.count(2) == 1 and winners.count("connection_version_conflict") == 1
    assert current(configured, initial[0].grant_id).version == 2


def test_same_proposal_id_racing_across_projects_never_leaks_or_leaves_an_orphan(configured, tmp_path):
    task, actor, policy, service = configured
    other = {name: str(uuid4()) for name in ("project", "goal", "contract", "task")}
    other_actor = Actor(actor.owner_id, other["project"])
    with psycopg.connect(task["dsn"]) as c:
        c.execute("INSERT INTO panestria.project(id,owner_id) VALUES (%s,%s)", (other["project"], actor.owner_id))
        c.execute(
            "INSERT INTO panestria.goal(id,owner_id,project_id,intent,status) VALUES (%s,%s,%s,'synthetic','ACTIVE')",
            (other["goal"], actor.owner_id, other["project"]),
        )
        c.execute(
            "INSERT INTO panestria.goal_contract(id,goal_id,version,body,sha256) VALUES (%s,%s,1,'{}',%s)",
            (other["contract"], other["goal"], "ab" * 32),
        )
        c.execute(
            "INSERT INTO panestria.task(id,goal_id,contract_id,name,state) VALUES (%s,%s,%s,'synthetic','READY')",
            (other["task"], other["goal"], other["contract"]),
        )
        c.commit()
        PolicyService(CertificateStore(tmp_path, {})).initialize(UnitOfWork(c), other_actor, other["task"])
        c.commit()
        other_policy = active_policy_ref(UnitOfWork(c), other_actor.owner_id, other_actor.project_id)
    identifier = str(uuid4())
    barrier = Barrier(2)

    class CrossProjectRace(UnitOfWork):
        def execute(self, query, params=()):
            if "INSERT INTO panestria.connection_grant_review" in query:
                barrier.wait(timeout=10)
            return super().execute(query, params)

    def submit(item):
        who, task_id, ref = item
        try:
            with psycopg.connect(task["dsn"]) as c:
                result = service.propose(
                    CrossProjectRace(c),
                    who,
                    task_id,
                    proposal(ref, manifest(who.owner_id, who.project_id), proposal_id=identifier),
                )
                return result.grant_id
        except KernelDenied as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, [(actor, task["task"], policy), (other_actor, other["task"], other_policy)]))
    assert results.count("connection_proposal_conflict") == 1
    with psycopg.connect(task["dsn"]) as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.connection_grant WHERE owner_id=%s", (actor.owner_id,)
        ).fetchone() == (1,)
        assert c.execute(
            "SELECT count(*) FROM panestria.connection_grant_review WHERE id=%s", (identifier,)
        ).fetchone() == (1,)


def test_database_immutability_and_deferred_pointer_are_enforced(configured):
    task, _, _, _ = configured
    review = prepare(configured, request(configured))
    decide(configured, review)
    with psycopg.connect(task["dsn"]) as c:
        for table in ("connection_grant_review", "connection_grant_decision", "connection_grant_revision"):
            key = "id" if table == "connection_grant_review" else "review_id"
            for verb in ("UPDATE", "DELETE"):
                from psycopg import sql

                query = (
                    sql.SQL("UPDATE panestria.{} SET manifest_sha256=manifest_sha256 WHERE {}=%s")
                    if table != "connection_grant_decision"
                    else sql.SQL("UPDATE panestria.{} SET decision=decision WHERE {}=%s")
                )
                if verb == "DELETE":
                    query = sql.SQL("DELETE FROM panestria.{} WHERE {}=%s")
                with pytest.raises(psycopg.Error, match="immutable"), c.transaction():
                    c.execute(query.format(sql.Identifier(table), sql.Identifier(key)), (review.proposal_id,))
        with pytest.raises(psycopg.Error, match="pointer/revision mismatch"), c.transaction():
            c.execute("UPDATE panestria.connection_grant SET current_version=2 WHERE id=%s", (review.grant_id,))
            c.execute("SET CONSTRAINTS ALL IMMEDIATE")
        with pytest.raises(psycopg.Error, match="pointer transition"), c.transaction():
            c.execute("UPDATE panestria.connection_grant SET current_version=0 WHERE id=%s", (review.grant_id,))


@pytest.mark.parametrize("granted_version", [None, 1])
def test_database_requires_each_approved_decision_to_have_its_own_revision(configured, granted_version):
    task, actor, policy, _ = configured
    first = prepare(configured, request(configured))
    other = prepare(configured, proposal(policy, first.manifest, grant_id=first.grant_id, expected_version=0))
    decide(configured, first)
    with pytest.raises(psycopg.Error), psycopg.connect(task["dsn"]) as c:
        c.execute(
            "INSERT INTO panestria.connection_grant_decision(review_id,grant_id,owner_id,project_id,expected_version,"
            "effect_digest,decision,granted_version,decided_by) VALUES (%s,%s,%s,%s,0,%s,'APPROVED',%s,%s)",
            (
                other.proposal_id,
                other.grant_id,
                actor.owner_id,
                actor.project_id,
                other.effect_digest,
                granted_version,
                actor.owner_id,
            ),
        )


def test_changed_policy_requires_new_review_and_marks_old_declaration_stale(configured, tmp_path):
    from panestria.contracts.policy import AutonomyAxis

    task, actor, policy_ref, service = configured
    first = prepare(configured, request(configured))
    decide(configured, first)
    pending = prepare(configured, proposal(policy_ref, first.manifest, grant_id=first.grant_id, expected_version=1))
    policies = PolicyService(CertificateStore(tmp_path, {}))
    with psycopg.connect(task["dsn"]) as c:
        old = policies.get(UnitOfWork(c), actor)
        actions = dict(old.autonomy.actions)
        actions["read"] = "observe"
        new = old.model_copy(update={"version": 2, "autonomy": AutonomyAxis(version=2, actions=actions)})
        revision = policies.propose(UnitOfWork(c), actor, task["task"], new)
        c.commit()
        policies.decide(UnitOfWork(c), actor, revision.review_id, revision.effect_digest, "approve")
        c.commit()
        policies.apply(UnitOfWork(c), actor, revision.review_id, revision.effect_digest)
        c.commit()
    with pytest.raises(KernelDenied, match="policy_mismatch"):
        decide(configured, pending)
    assert current(configured, first.grant_id).policy_status == "STALE"
    assert decide(configured, first).replayed  # Historical receipt, never a renewed permit.


@pytest.mark.parametrize("delta", [-1, 31 * 86400])
def test_new_manifest_expiry_is_future_and_bounded_by_server_clock(configured, delta):
    task, actor, policy, _ = configured
    body = manifest(actor.owner_id, actor.project_id, expires_at=datetime.now(UTC) + timedelta(seconds=delta))
    with pytest.raises(KernelDenied, match="connection_expiry_invalid"):
        prepare(configured, proposal(policy, body))


def test_actual_declaration_expiry_does_not_erase_approval_history(configured):
    task, actor, policy, _ = configured
    body = manifest(actor.owner_id, actor.project_id, expires_at=datetime.now(UTC) + timedelta(seconds=3))
    review = prepare(configured, proposal(policy, body))
    decide(configured, review)
    assert current(configured, review.grant_id).state == "DECLARED_ACTIVE"
    time.sleep(3.05)
    assert current(configured, review.grant_id).state == "EXPIRED"
    assert decide(configured, review).replayed


def test_restored_metadata_corruption_is_denied_without_rewriting_history(configured):
    task, actor, _, service = configured
    review = prepare(configured, request(configured))
    decide(configured, review)
    with psycopg.connect(task["dsn"]) as c:
        with pytest.raises(RuntimeError, match="synthetic rollback"), c.transaction():
            # Trusted test-only corruption, always rolled back including trigger state.
            c.execute("ALTER TABLE panestria.connection_grant_review DISABLE TRIGGER immutable_connection_grant_review")
            c.execute(
                "UPDATE panestria.connection_grant_review "
                "SET manifest_body=manifest_body || '{\"approved\":true}'::jsonb WHERE id=%s",
                (review.proposal_id,),
            )
            with pytest.raises(KernelDenied, match="connection_review_corrupt"):
                service.current(UnitOfWork(c), actor, review.grant_id)
            raise RuntimeError("synthetic rollback")
    assert current(configured, review.grant_id).state == "DECLARED_ACTIVE"


def test_global_event_lock_follows_every_grant_entity_write(configured):
    task, actor, _, service = configured

    class EventLast(UnitOfWork):
        locked = False
        writes = 0

        def execute(self, query, params=()):
            if "pg_advisory_xact_lock" in query:
                self.locked = True
            if query.lstrip().startswith(("INSERT", "UPDATE", "DELETE")) and "panestria.task_event" not in query:
                assert not self.locked, "entity write after global event lock"
                self.writes += 1
            return super().execute(query, params)

    with psycopg.connect(task["dsn"]) as c:
        uow = EventLast(c)
        review = service.propose(uow, actor, task["task"], request(configured))
        assert uow.locked and uow.writes == 2
    with psycopg.connect(task["dsn"]) as c:
        uow = EventLast(c)
        service.decide(uow, actor, review.proposal_id, review.effect_digest, "approve")
        assert uow.locked and uow.writes == 3


def test_audit_actual_dump_restore_and_downgrade_refusal(configured, record_property):
    import hashlib
    import os
    import subprocess
    from pathlib import Path

    from psycopg import sql
    from test_memory_restore import _fixture_container

    task, actor, policy, service = configured
    review = prepare(configured, request(configured))
    decide(configured, review)
    root = Path(__file__).resolve().parents[2]
    with psycopg.connect(task["dsn"]) as c:
        quota_history = c.execute("SELECT EXISTS(SELECT 1 FROM panestria.quota_observation)").fetchone()[0]
        launch_history = c.execute("SELECT EXISTS(SELECT 1 FROM panestria.worker_invocation_launch)").fetchone()[0]
    refused = subprocess.run(
        [str(root / ".venv/bin/alembic"), "-c", "migrations/alembic.ini", "downgrade", "0026_claim_evidence"],
        cwd=root,
        env={**os.environ, "PANESTRIA_DATABASE_URL": task["dsn"]},
        capture_output=True,
        timeout=30,
    )
    expected_guard = (
        b"quota observation audit exists"
        if quota_history
        else b"sandbox launch audit exists"
        if launch_history
        else b"connection grant audit exists"
    )
    assert refused.returncode != 0 and expected_guard in refused.stderr
    with psycopg.connect(task["dsn"]) as c:
        from panestria.api.local_server import SCHEMA_HEAD

        assert c.execute("SELECT version_num FROM alembic_version").fetchone() == (SCHEMA_HEAD,)
    container = _fixture_container()
    backup = subprocess.run(
        [
            "docker",
            "exec",
            container,
            "pg_dump",
            "-U",
            "panestria_synthetic",
            "-d",
            task["dsn"].rsplit("/", 1)[1],
            "-Fc",
        ],
        capture_output=True,
        check=True,
        timeout=30,
    )
    assert 0 < len(backup.stdout) < 16 * 1024 * 1024
    record_property("backup_sha256", hashlib.sha256(backup.stdout).hexdigest())
    name = "panestria_grant_restore_" + uuid4().hex
    restored = task["dsn"].rsplit("/", 1)[0] + "/" + name
    with psycopg.connect(task["dsn"], autocommit=True) as admin:
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
                input=backup.stdout,
                capture_output=True,
                check=True,
                timeout=30,
            )
            with psycopg.connect(restored) as c:
                declared = service.current(UnitOfWork(c), actor, review.grant_id)
                assert declared.manifest.sha256() == review.manifest.sha256() and declared.version == 1
                maximum = c.execute("SELECT max(seq) FROM panestria.task_event").fetchone()[0]
                revoke = service.propose(
                    UnitOfWork(c),
                    actor,
                    task["task"],
                    proposal(policy, None, grant_id=review.grant_id, expected_version=1, operation="REVOKE"),
                )
                c.commit()
                service.decide(UnitOfWork(c), actor, revoke.proposal_id, revoke.effect_digest, "approve")
                c.commit()
                assert service.current(UnitOfWork(c), actor, review.grant_id).state == "DECLARED_REVOKED"
                assert c.execute("SELECT max(seq) FROM panestria.task_event").fetchone()[0] > maximum
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def test_empty_migration_downgrade_and_reupgrade_preserve_existing_schema(r1_database):
    import os
    import subprocess
    from pathlib import Path

    from psycopg import sql

    root = Path(__file__).resolve().parents[2]
    name = "panestria_empty_grants_" + uuid4().hex
    dsn = r1_database.rsplit("/", 1)[0] + "/" + name
    with psycopg.connect(r1_database, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            for direction, target in (("upgrade", "head"), ("downgrade", "0026_claim_evidence"), ("upgrade", "head")):
                subprocess.run(
                    [str(root / ".venv/bin/alembic"), "-c", "migrations/alembic.ini", direction, target],
                    cwd=root,
                    env={**os.environ, "PANESTRIA_DATABASE_URL": dsn},
                    capture_output=True,
                    check=True,
                    timeout=30,
                )
            with psycopg.connect(dsn) as c:
                assert c.execute("SELECT version_num FROM alembic_version").fetchone() == ("0029_quota_observations",)
                assert c.execute("SELECT count(*) FROM panestria.connection_grant").fetchone() == (0,)
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
