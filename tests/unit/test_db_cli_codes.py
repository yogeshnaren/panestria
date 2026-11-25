"""`panestria db` maps every failure to one stable code, and refuses bad input before connecting."""

from __future__ import annotations

import json

import psycopg
import pytest
import sqlalchemy.exc
from typer.testing import CliRunner

from panestria.api.db import DatabaseUnavailable
from panestria.assets import AssetUnavailable
from panestria.cli import db
from panestria.cli.main import app
from panestria.config import ProfileRejected

UNREACHABLE = "postgresql://panestria_synthetic:placeholder-not-a-secret@127.0.0.1:1/none"


def _wrapped(kind: type[sqlalchemy.exc.DBAPIError], orig: Exception) -> sqlalchemy.exc.DBAPIError:
    return kind("SELECT 1", {}, orig)


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (db._Refused("database_schema_newer_than_package"), "database_schema_newer_than_package"),
        (ProfileRejected("invalid_database_url", "safe message"), "invalid_database_url"),
        (AssetUnavailable("packaged_asset_missing"), "packaged_asset_missing"),
        (
            _wrapped(sqlalchemy.exc.OperationalError, psycopg.errors.LockNotAvailable("lock")),
            "migration_lock_timeout",
        ),
        (
            _wrapped(sqlalchemy.exc.OperationalError, psycopg.errors.QueryCanceled("cancel")),
            "migration_statement_timeout",
        ),
        (_wrapped(sqlalchemy.exc.OperationalError, psycopg.OperationalError("down")), "database_unavailable"),
        (_wrapped(sqlalchemy.exc.ProgrammingError, psycopg.errors.SyntaxError("bad")), "migration_failed"),
        (DatabaseUnavailable("down"), "database_unavailable"),
        (psycopg.OperationalError("down"), "database_unavailable"),
        (RuntimeError("database URL scheme is not supported"), "migration_failed"),
    ],
)
def test_every_failure_maps_to_one_documented_code(error: Exception, code: str) -> None:
    assert db._code(error) == code


def _invoke(monkeypatch: pytest.MonkeyPatch, url: str, *args: str) -> tuple[int, dict[str, object]]:
    monkeypatch.setenv("PANESTRIA_DATABASE_URL", url)
    result = CliRunner().invoke(app, ["db", *args])
    stream = result.stdout if result.exit_code == 0 else result.stderr
    return result.exit_code, json.loads(stream.strip().splitlines()[-1])


@pytest.mark.parametrize("value", ["5 seconds", "-1s", "5sec", ""])
def test_a_malformed_timeout_is_refused_before_connecting(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    for option in ("--lock-timeout", "--statement-timeout"):
        assert _invoke(monkeypatch, UNREACHABLE, "upgrade", option, value) == (2, {"code": "invalid_migration_timeout"})


def test_a_bad_url_or_unreachable_database_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    for command in ("status", "upgrade"):
        assert _invoke(monkeypatch, "not-a-url", command) == (2, {"code": "invalid_database_url"})
        assert _invoke(monkeypatch, UNREACHABLE, command) == (2, {"code": "database_unavailable"})


def test_a_package_without_migrations_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing() -> None:
        raise AssetUnavailable("packaged_asset_missing")

    monkeypatch.setattr(db, "migrations", missing)
    for command in ("status", "upgrade"):
        assert _invoke(monkeypatch, UNREACHABLE, command) == (2, {"code": "packaged_asset_missing"})


def test_valid_timeouts_reach_the_migration_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    config = db._alembic(lock_timeout="30s", statement_timeout="10min")
    assert config.cmd_opts is not None
    assert config.cmd_opts.x == ["lock_timeout=30s", "statement_timeout=10min"]
    assert db._alembic().cmd_opts.x == []  # type: ignore[union-attr]
