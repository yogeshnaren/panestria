"""Database schema commands that run the migrations this package ships.

Migrations are forward-only (ADR 0016): there is no command that moves a schema
back. To return to an earlier release, restore the backup taken before the
upgrade.
"""

from __future__ import annotations

import json
import os
import re
from argparse import Namespace
from typing import Annotated

import psycopg
import sqlalchemy.exc
import typer
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.util import CommandError

from panestria.api.db import DatabaseUnavailable, open_database
from panestria.assets import AssetUnavailable, migrations
from panestria.config import ProfileRejected, Settings

db_app = typer.Typer(
    no_args_is_help=True,
    help="Database schema status and upgrade. Migrations are forward-only; restore a backup to go back.",
)

_TIMEOUT_HELP = "PostgreSQL duration such as 5s or 10min (default: {})."
# The same form migrations/env.py accepts for its -x timeouts.
_DURATION = re.compile(r"[0-9]+(us|ms|s|min|h|d)?")


class _Refused(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _database_url() -> str:
    url = Settings(database_url=os.environ.get("PANESTRIA_DATABASE_URL", "")).validate_profile().database_url
    return url.get_secret_value()


def _alembic(*, lock_timeout: str | None = None, statement_timeout: str | None = None) -> Config:
    script = migrations()
    given = (("lock_timeout", lock_timeout), ("statement_timeout", statement_timeout))
    config = Config(cmd_opts=Namespace(x=[f"{name}={value}" for name, value in given if value is not None]))
    config.set_main_option("script_location", str(script))
    # Revisions import the shared guard from the script directory itself.
    config.set_main_option("path_separator", "os")
    config.set_main_option("prepend_sys_path", str(script))
    # migrations/env.py reads PANESTRIA_DATABASE_URL; this placeholder is never used.
    config.set_main_option("sqlalchemy.url", "postgresql+psycopg://invalid:invalid@127.0.0.1:1/invalid")
    return config


def _current(url: str) -> str | None:
    with open_database(url) as connection:
        try:
            row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        except psycopg.errors.UndefinedTable:
            return None
    return None if row is None else str(row[0])


def _state(config: Config, url: str) -> tuple[str | None, str]:
    script = ScriptDirectory.from_config(config)
    head = script.get_current_head()
    if head is None:
        raise _Refused("packaged_asset_missing")
    current = _current(url)
    if current is not None:
        try:
            script.get_revision(current)
        except CommandError:
            # A newer release migrated this database; this package cannot read it.
            raise _Refused("database_schema_newer_than_package") from None
    return current, head


def _fail(code: str) -> None:
    typer.echo(json.dumps({"code": code}), err=True)
    raise typer.Exit(2)


def _code(error: Exception) -> str:
    if isinstance(error, (_Refused, ProfileRejected)):
        return error.code
    if isinstance(error, AssetUnavailable):
        return str(error)
    if isinstance(error, sqlalchemy.exc.DBAPIError):
        if isinstance(error.orig, psycopg.errors.LockNotAvailable):
            return "migration_lock_timeout"
        if isinstance(error.orig, psycopg.errors.QueryCanceled):
            return "migration_statement_timeout"
        if isinstance(error, sqlalchemy.exc.OperationalError):
            return "database_unavailable"
        return "migration_failed"
    if isinstance(error, (DatabaseUnavailable, psycopg.OperationalError)):
        return "database_unavailable"
    return "migration_failed"


@db_app.command("status")
def status_command() -> None:
    """Print the database's schema revision and the head this package ships."""
    try:
        url = _database_url()
        current, head = _state(_alembic(), url)
    except (_Refused, ProfileRejected, AssetUnavailable, DatabaseUnavailable, psycopg.Error) as error:
        _fail(_code(error))
        return
    typer.echo(json.dumps({"current": current, "head": head, "current_is_head": current == head}))


@db_app.command("upgrade")
def upgrade_command(
    lock_timeout: Annotated[str | None, typer.Option("--lock-timeout", help=_TIMEOUT_HELP.format("5s"))] = None,
    statement_timeout: Annotated[
        str | None, typer.Option("--statement-timeout", help=_TIMEOUT_HELP.format("5min"))
    ] = None,
) -> None:
    """Apply every packaged migration through head. Back up a database that holds data first."""
    if any(value is not None and not _DURATION.fullmatch(value) for value in (lock_timeout, statement_timeout)):
        _fail("invalid_migration_timeout")
        return
    try:
        url = _database_url()
        config = _alembic(lock_timeout=lock_timeout, statement_timeout=statement_timeout)
        before, head = _state(config, url)
        if before == head:
            typer.echo(json.dumps({"status": "CURRENT", "revision": head}))
            return
        command.upgrade(config, "head")
        after = _current(url)
    except (
        _Refused,
        ProfileRejected,
        AssetUnavailable,
        DatabaseUnavailable,
        psycopg.Error,
        sqlalchemy.exc.SQLAlchemyError,
        CommandError,
        RuntimeError,
    ) as error:
        _fail(_code(error))
        return
    if after != head:
        _fail("migration_incomplete")
        return
    typer.echo(json.dumps({"status": "UPGRADED", "from": before, "to": after}))
