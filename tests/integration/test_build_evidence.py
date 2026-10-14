"""Publication is atomic; orphan files or lost replies cannot create extra PASS records."""

from __future__ import annotations

import psycopg
import pytest
from build_support import BuildFixture, _bundle
from build_support import build as build

from panestria.kernel.errors import KernelDenied
from panestria.kernel.uow import UnitOfWork


def test_publication_rollback_and_duplicate_receipt(build: BuildFixture) -> None:
    bundle = _bundle(build)
    with psycopg.connect(build.task["dsn"]) as c:
        uow = UnitOfWork(c)
        digest = build.service.publish(uow, build.actor, bundle)
        c.rollback()
        assert (build.service.store.root / digest).exists()
        assert c.execute(
            "SELECT count(*) FROM panestria.build_evidence WHERE task_id=%s", (build.task["task"],)
        ).fetchone() == (0,)
        assert c.execute("SELECT state FROM panestria.task WHERE id=%s", (build.task["task"],)).fetchone() == (
            "RUNNING",
        )
        digest = build.service.publish(uow, build.actor, bundle)
        c.commit()
        assert build.service.publish(uow, build.actor, bundle) == digest
        assert c.execute(
            "SELECT count(*) FROM panestria.build_evidence WHERE task_id=%s", (build.task["task"],)
        ).fetchone() == (1,)
        assert c.execute(
            "SELECT count(*) FROM panestria.task_event WHERE task_id=%s AND kind='build.verified'",
            (build.task["task"],),
        ).fetchone() == (1,)


def test_missing_report_never_publishes_a_pass(build: BuildFixture) -> None:
    bundle = _bundle(build)
    (build.service.store.root / bundle.checks[0].report_sha256).unlink()
    with psycopg.connect(build.task["dsn"]) as c:
        with pytest.raises(KernelDenied, match="missing_build_evidence"), c.transaction():
            build.service.publish(UnitOfWork(c), build.actor, bundle)
        assert c.execute(
            "SELECT count(*) FROM panestria.artifact WHERE task_id=%s", (build.task["task"],)
        ).fetchone() == (0,)


def test_stale_verifier_cannot_publish_after_attempt_release(build: BuildFixture) -> None:
    from panestria.kernel.leases import LeaseService

    bundle = _bundle(build)
    with psycopg.connect(build.task["dsn"]) as c:
        uow = UnitOfWork(c)
        LeaseService().release(uow, build.actor, build.attempt, 1)
        c.commit()
        with pytest.raises(KernelDenied, match="stale_lease"), c.transaction():
            build.service.publish(uow, build.actor, bundle)
        assert c.execute(
            "SELECT count(*) FROM panestria.build_evidence WHERE task_id=%s", (build.task["task"],)
        ).fetchone() == (0,)
