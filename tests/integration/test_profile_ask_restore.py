"""Actual pg_dump/restore retains restricted receipt and pending-input binding."""

from __future__ import annotations

import os
import subprocess
from urllib.parse import urlsplit
from uuid import uuid4

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict
from test_memory_restore import _fixture_container
from test_profile_ask import SENTINEL, ask_profile, prepare  # noqa: F401
from test_profile_vault import profile  # noqa: F401
from test_profile_vault_restore import dump, restore

from panestria.contracts.inference import InferenceResult, Usage
from panestria.kernel.errors import KernelDenied
from panestria.kernel.local_setup import offline_policy
from panestria.kernel.repositories.policy import insert_revision
from panestria.kernel.uow import UnitOfWork


def test_actual_profile_ask_restore_and_lost_key_denial(ask_profile):  # noqa: F811
    dsn, actor, handle, keys, vault, service, request = ask_profile
    pending = prepare(ask_profile)
    completed = request.model_copy(update={"request_id": str(uuid4())})
    with psycopg.connect(dsn) as c:
        ready = service.prepare(UnitOfWork(c), actor, completed)
    with psycopg.connect(dsn) as c:
        inference = service.claim(UnitOfWork(c), actor, ready)
    with psycopg.connect(dsn) as c:
        service.finish(
            UnitOfWork(c),
            actor,
            completed.request_id,
            InferenceResult(inference.model_ref, SENTINEL, Usage(50, 12, 0), 0.2, 0.1),
        )
        before = service.receipt(UnitOfWork(c), actor, completed.request_id)
    container = _fixture_container()
    snapshot = dump(container)
    assert SENTINEL.encode() not in snapshot
    assert all(key.get_secret_value() not in snapshot for key in keys.values.values())
    with restore(dsn, container, snapshot) as restored_dsn:
        with psycopg.connect(restored_dsn) as c:
            assert service.receipt(UnitOfWork(c), actor, completed.request_id) == before
            assert service.claim(UnitOfWork(c), actor, pending).prompt == pending.inference.prompt
            c.rollback()
            keys.values.clear()
            with pytest.raises(KernelDenied, match="key_handle_missing"):
                service.claim(UnitOfWork(c), actor, pending)
            assert service.receipt(UnitOfWork(c), actor, completed.request_id) == before


def test_populated_profile_ask_downgrade_refuses_loss(ask_profile):  # noqa: F811
    dsn, actor, handle, keys, vault, service, request = ask_profile
    with psycopg.connect(dsn) as c:
        document = vault.read(UnitOfWork(c), actor, handle.profile_id)[1]
    # Earlier populated guards must be exercised independently of newer audit
    # rows created by other tests. Copy actual current schema into a new DB;
    # never alter/delete audit from the shared source database.
    with restore(dsn, _fixture_container(), dump(_fixture_container(), schema_only=True)) as isolated_dsn:
        isolated_url = urlsplit(dsn)._replace(path="/" + conninfo_to_dict(isolated_dsn)["dbname"]).geturl()
        stamped = subprocess.run(
            ["uv", "run", "--frozen", "alembic", "-c", "migrations/alembic.ini", "stamp", "head"],
            env={**os.environ, "PANESTRIA_DATABASE_URL": isolated_url},
            capture_output=True,
            timeout=30,
        )
        assert stamped.returncode == 0
        with psycopg.connect(isolated_dsn) as c:
            c.execute(
                "INSERT INTO panestria.principal(id,display_name) VALUES(%s,'synthetic guard owner')", (actor.owner_id,)
            )
            c.execute("INSERT INTO panestria.project(id,owner_id) VALUES(%s,%s)", (actor.project_id, actor.owner_id))
            insert_revision(UnitOfWork(c), offline_policy(actor))
            vault.create(UnitOfWork(c), actor, handle, document, consent_ref=str(uuid4()))
            service.prepare(UnitOfWork(c), actor, request)
            before = c.execute("SELECT version_num FROM alembic_version").fetchone()
        result = subprocess.run(
            ["uv", "run", "--frozen", "alembic", "-c", "migrations/alembic.ini", "downgrade", "0020_profile_vault"],
            env={**os.environ, "PANESTRIA_DATABASE_URL": isolated_url},
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode != 0 and "profile Ask audit exists" in result.stderr
        with psycopg.connect(isolated_dsn) as c:
            assert c.execute("SELECT version_num FROM alembic_version").fetchone() == before
            assert service.receipt(UnitOfWork(c), actor, request.request_id)["state"] == "PREPARED"
