"""Actual snapshots restore ciphertext; old wrapping keys stay outside backups."""

from __future__ import annotations

import hashlib
import os
import subprocess
from contextlib import contextmanager
from urllib.parse import urlsplit
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from test_memory_restore import _fixture_container
from test_profile_vault import create, document, profile  # noqa: F401

from panestria.kernel.errors import KernelDenied
from panestria.kernel.uow import UnitOfWork


def dump(container, *, schema_only=False):
    result = subprocess.run(
        [
            "docker",
            "exec",
            container,
            "pg_dump",
            "--username=panestria_synthetic",
            "--dbname=panestria_synthetic",
            "--format=custom",
            "--compress=0",
            "--no-owner",
            "--no-acl",
            *(["--schema-only"] if schema_only else []),
        ],
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 0 and 0 < len(result.stdout) < 16 * 1024 * 1024
    return result.stdout


@contextmanager
def restore(dsn, container, snapshot):
    name = "panestria_profile_restore_" + uuid4().hex
    params = conninfo_to_dict(dsn)
    params["dbname"] = name
    with psycopg.connect(dsn, autocommit=True) as administrative:
        administrative.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            result = subprocess.run(
                [
                    "docker",
                    "exec",
                    "-i",
                    container,
                    "pg_restore",
                    "--username=panestria_synthetic",
                    "--dbname=" + name,
                    "--no-owner",
                    "--no-acl",
                    "--exit-on-error",
                ],
                input=snapshot,
                capture_output=True,
                timeout=60,
            )
            assert result.returncode == 0, "isolated_profile_restore_failed"
            yield make_conninfo(**params)
        finally:
            administrative.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def test_actual_backup_restore_and_rotation_key_retention(profile, record_property):  # noqa: F811
    dsn, actor, handle, keys, vault = profile
    first = create(profile)
    container = _fixture_container()
    old_snapshot = dump(container)
    rotated = handle.model_copy(update={"key_id": str(uuid4())})
    keys.provision(rotated)
    suppressed = handle.model_copy(update={"profile_id": str(uuid4()), "key_id": str(uuid4())})
    keys.provision(suppressed)
    with psycopg.connect(dsn) as c:
        second = vault.revise(UnitOfWork(c), actor, rotated, 0, document(), consent_ref=str(uuid4()))
        hidden = vault.create(UnitOfWork(c), actor, suppressed, document(), consent_ref=str(uuid4()))
        vault.suppress(UnitOfWork(c), actor, hidden.profile_id, 0)
    new_snapshot = dump(container)
    for snapshot in (old_snapshot, new_snapshot):
        assert all(value.get_secret_value() not in snapshot for value in keys.values.values())
    with restore(dsn, container, old_snapshot) as old_dsn, restore(dsn, container, new_snapshot) as new_dsn:
        with psycopg.connect(old_dsn) as old, psycopg.connect(new_dsn) as new:
            assert vault.read(UnitOfWork(old), actor, handle.profile_id)[0] == first
            assert vault.read(UnitOfWork(new), actor, handle.profile_id)[0] == second
            with pytest.raises(KernelDenied, match="^profile_suppressed$"):
                vault.read(UnitOfWork(new), actor, hidden.profile_id)
            keys.values.pop(handle.model_dump_json())
            with pytest.raises(KernelDenied, match="^key_handle_missing$"):
                vault.read(UnitOfWork(old), actor, handle.profile_id)
            assert vault.read(UnitOfWork(new), actor, handle.profile_id)[0] == second
            assert new.execute(
                "SELECT key_id::text FROM panestria.profile_revision WHERE profile_id=%s ORDER BY version",
                (handle.profile_id,),
            ).fetchall() == [
                (handle.key_id,),
                (rotated.key_id,),
            ]
    record_property("old_backup_sha256", hashlib.sha256(old_snapshot).hexdigest())
    record_property("new_backup_sha256", hashlib.sha256(new_snapshot).hexdigest())
    record_property("execution_mode", "ACTUAL_PG_DUMP_RESTORE_WITH_TEST_ONLY_EXTERNAL_KEYS")


def test_populated_vault_downgrade_preserves_audit(profile):  # noqa: F811
    dsn, actor, handle, keys, vault = profile
    container = _fixture_container()
    # Isolate the vault's guard from newer guards/data created by other tests.
    # Restore actual current schema only; no test/owner source database is reset.
    with restore(dsn, container, dump(container, schema_only=True)) as isolated_dsn:
        isolated_url = urlsplit(dsn)._replace(path="/" + conninfo_to_dict(isolated_dsn)["dbname"]).geturl()
        with psycopg.connect(isolated_dsn) as c:
            c.execute(
                "INSERT INTO panestria.principal(id,display_name) VALUES(%s,'synthetic guard owner')", (actor.owner_id,)
            )
            c.execute("INSERT INTO panestria.project(id,owner_id) VALUES(%s,%s)", (actor.project_id, actor.owner_id))
            before = c.execute("SELECT version_num FROM alembic_version").fetchone()
        # Schema-only dump deliberately has no Alembic data row.
        result = subprocess.run(
            ["uv", "run", "--frozen", "alembic", "-c", "migrations/alembic.ini", "stamp", "head"],
            env={**os.environ, "PANESTRIA_DATABASE_URL": isolated_url},
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0 and before is None
        ref = create((isolated_dsn, *profile[1:]))
        with psycopg.connect(isolated_dsn) as c:
            version = c.execute("SELECT version_num FROM alembic_version").fetchone()
        result = subprocess.run(
            ["uv", "run", "--frozen", "alembic", "-c", "migrations/alembic.ini", "downgrade", "0019_canonical_labels"],
            env={**os.environ, "PANESTRIA_DATABASE_URL": isolated_url},
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode != 0 and "profile audit exists" in result.stderr
        with psycopg.connect(isolated_dsn) as c:
            assert c.execute("SELECT version_num FROM alembic_version").fetchone() == version
            assert vault.read(UnitOfWork(c), actor, handle.profile_id)[0] == ref
            assert c.execute(
                "SELECT count(*) FROM panestria.profile_event WHERE profile_id=%s", (handle.profile_id,)
            ).fetchone() == (1,)
