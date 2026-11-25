"""`panestria db` status and upgrade run in-process against disposable databases.

test_db_cli.py drives the installed console script; this file runs the same
commands in the test process, so the command module is measured too.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from migration_harness import current_head, disposable_database, previous_head
from panestria.cli.main import app


def _invoke(monkeypatch: pytest.MonkeyPatch, dsn: str, *args: str) -> tuple[int, dict[str, object]]:
    monkeypatch.setenv("PANESTRIA_DATABASE_URL", dsn)
    result = CliRunner().invoke(app, ["db", *args])
    stream = result.stdout if result.exit_code == 0 else result.stderr
    return result.exit_code, json.loads(stream.strip().splitlines()[-1])


def test_status_and_upgrade_from_the_previous_release(r1_database: str, monkeypatch: pytest.MonkeyPatch) -> None:
    head, previous = current_head(), previous_head()
    with disposable_database(r1_database, previous, label="db_inprocess") as db:
        assert _invoke(monkeypatch, db.dsn, "status") == (
            0,
            {"current": previous, "head": head, "current_is_head": False},
        )
        assert _invoke(monkeypatch, db.dsn, "upgrade", "--lock-timeout", "10s", "--statement-timeout", "5min") == (
            0,
            {"status": "UPGRADED", "from": previous, "to": head},
        )
        assert db.revision() == head
        assert _invoke(monkeypatch, db.dsn, "upgrade") == (0, {"status": "CURRENT", "revision": head})


def test_an_empty_database_reports_no_revision_and_a_newer_one_is_refused(
    r1_database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    with disposable_database(r1_database, None, label="db_inprocess_empty") as db:
        assert _invoke(monkeypatch, db.dsn, "status") == (
            0,
            {"current": None, "head": current_head(), "current_is_head": False},
        )
    with disposable_database(r1_database, "head", label="db_inprocess_newer") as db:
        with db.connect() as c:
            c.execute("UPDATE public.alembic_version SET version_num = '9999_from_a_newer_release'")
        for command in ("status", "upgrade"):
            assert _invoke(monkeypatch, db.dsn, command) == (2, {"code": "database_schema_newer_than_package"})
        assert db.revision() == "9999_from_a_newer_release"
