"""Alembic environment. The database URL comes from the process environment."""

from __future__ import annotations

import os
import re
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None

# A migration waiting for a lock queues every later query on that table behind
# it. Fail fast instead and retry when the server is idle. The statement limit
# bounds any single statement. Override for one run with
# `alembic -x lock_timeout=30s -x statement_timeout=30min upgrade head`.
TIMEOUTS = {"lock_timeout": "5s", "statement_timeout": "5min"}
_DURATION = re.compile(r"[0-9]+(us|ms|s|min|h|d)?")


def _database_url() -> str:
    url = os.environ["PANESTRIA_DATABASE_URL"]
    if url.startswith("postgresql+psycopg://"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    raise RuntimeError("database URL scheme is not supported")


def _timeouts() -> dict[str, str]:
    given = context.get_x_argument(as_dictionary=True)
    for name in given:
        if name not in TIMEOUTS:
            raise RuntimeError(f"unknown migration argument: {name}")
    values = {**TIMEOUTS, **given}
    for name, value in values.items():
        if not _DURATION.fullmatch(value):
            raise RuntimeError(f"{name} must be a PostgreSQL duration such as 5s or 10min, not {value!r}")
    return values


def run_migrations_offline() -> None:
    timeouts = _timeouts()
    context.configure(url=_database_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        for name, value in timeouts.items():
            context.execute(f"SET {name} = '{value}'")
        context.run_migrations()


def run_migrations_online() -> None:
    timeouts = _timeouts()
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        # Session-level settings, committed before alembic opens its own transaction.
        for name, value in timeouts.items():
            connection.execute(text("SELECT set_config(:name, :value, false)"), {"name": name, "value": value})
        connection.commit()
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
