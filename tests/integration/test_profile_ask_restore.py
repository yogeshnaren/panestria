"""Actual pg_dump/restore retains restricted receipt and pending-input binding."""

from __future__ import annotations

import os
import subprocess
from uuid import uuid4

import psycopg
import pytest
from test_memory_restore import _fixture_container
from test_profile_ask import SENTINEL, ask_profile, prepare  # noqa: F401
from test_profile_vault import profile  # noqa: F401
from test_profile_vault_restore import dump, restore

from panestria.contracts.inference import InferenceResult, Usage
from panestria.kernel.errors import KernelDenied
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
    prepare(ask_profile)
    result = subprocess.run(
        ["uv", "run", "--frozen", "alembic", "-c", "migrations/alembic.ini", "downgrade", "0020_profile_vault"],
        env={**os.environ, "PANESTRIA_DATABASE_URL": dsn},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0 and "profile Ask audit exists" in result.stderr
    with psycopg.connect(dsn) as c:
        assert c.execute("SELECT version_num FROM alembic_version").fetchone() == ("0021_profile_ask",)
        assert service.receipt(UnitOfWork(c), actor, request.request_id)["state"] == "PREPARED"
