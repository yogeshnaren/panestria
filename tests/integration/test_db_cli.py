"""`panestria db` runs the packaged migrations forward and refuses what it cannot do safely."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from migration_harness import MigrationDatabase, current_head, disposable_database, previous_head

PANESTRIA = Path(sys.executable).parent / "panestria"


def _db(dsn: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(PANESTRIA), "db", *args],
        env={**os.environ, "PANESTRIA_DATABASE_URL": dsn},
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def _ok(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _refused(result: subprocess.CompletedProcess[str]) -> str:
    assert result.returncode == 2, (result.stdout, result.stderr)
    return str(json.loads(result.stderr.strip().splitlines()[-1])["code"])


def test_an_empty_database_is_upgraded_to_the_packaged_head_once(r1_database: str) -> None:
    with disposable_database(r1_database, None, label="db_cli_empty") as db:
        head = current_head()
        assert _ok(_db(db.dsn, "status")) == {"current": None, "head": head, "current_is_head": False}
        assert _ok(_db(db.dsn, "upgrade")) == {"status": "UPGRADED", "from": None, "to": head}
        assert db.revision() == head
        assert _ok(_db(db.dsn, "status")) == {"current": head, "head": head, "current_is_head": True}
        assert _ok(_db(db.dsn, "upgrade")) == {"status": "CURRENT", "revision": head}


def test_the_previous_release_is_upgraded_in_place(r1_database: str) -> None:
    with disposable_database(r1_database, previous_head(), label="db_cli_previous") as db:
        assert _ok(_db(db.dsn, "upgrade")) == {"status": "UPGRADED", "from": previous_head(), "to": current_head()}
        assert db.revision() == current_head()


def test_a_blocked_upgrade_stops_on_the_lock_timeout_and_changes_nothing(r1_database: str) -> None:
    with disposable_database(r1_database, previous_head(), label="db_cli_lock") as db:
        holder = _hold_write_locks(db)
        try:
            assert _refused(_db(db.dsn, "upgrade", "--lock-timeout", "1s")) == "migration_lock_timeout"
        finally:
            holder.rollback()
            holder.close()
        assert db.revision() == previous_head()


def test_a_database_from_a_newer_release_is_left_alone(r1_database: str) -> None:
    with disposable_database(r1_database, "head", label="db_cli_newer") as db:
        with db.connect() as c:
            c.execute("UPDATE public.alembic_version SET version_num = '9999_from_a_newer_release'")
        for command in ("status", "upgrade"):
            assert _refused(_db(db.dsn, command)) == "database_schema_newer_than_package"
        assert db.revision() == "9999_from_a_newer_release"


def test_bad_input_is_refused_before_any_connection() -> None:
    unreachable = "postgresql://panestria_synthetic:placeholder-not-a-secret@127.0.0.1:1/none"
    assert _refused(_db(unreachable, "upgrade", "--lock-timeout", "5 seconds")) == "invalid_migration_timeout"
    assert _refused(_db("not-a-url", "upgrade")) == "invalid_database_url"
    assert _refused(_db(unreachable, "status")) == "database_unavailable"


def _hold_write_locks(db: MigrationDatabase):  # type: ignore[no-untyped-def]
    """Hold what an open write transaction holds: ROW EXCLUSIVE on every table and the version row."""
    holder = db.connect()
    tables = holder.execute(
        "SELECT string_agg(format('%I.%I', schemaname, tablename), ',') FROM pg_tables WHERE schemaname='panestria'"
    ).fetchone()
    assert tables is not None
    holder.execute(f"LOCK TABLE {tables[0]} IN ROW EXCLUSIVE MODE")
    holder.execute("SELECT version_num FROM public.alembic_version FOR UPDATE")
    return holder
