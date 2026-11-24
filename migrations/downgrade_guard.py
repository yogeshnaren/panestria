"""Shared downgrade guard: a downgrade never destroys populated owner data.

Release 1 migrations are forward-only (ADR 0016 decision 5); rollback means
restoring a backup. Downgrades remain for empty disposable databases. Each
downgrade calls ``refuse_populated_drop`` before its first statement and names
everything it drops. No override exists. A test that needs to downgrade a
populated disposable copy empties it first.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

import sqlalchemy as sa
from alembic import context, op

SCHEMA = "panestria"
_IDENTIFIER = re.compile(r"[a-z_][a-z0-9_]*")


class PopulatedDowngradeRefused(RuntimeError):
    """The downgrade would drop tables or columns that hold data."""


def refuse_populated_drop(
    revision: str,
    *,
    tables: Sequence[str] = (),
    columns: Mapping[str, Sequence[str]] | None = None,
) -> None:
    """Refuse this downgrade if anything it is about to drop holds data.

    ``tables`` are dropped whole, so any row refuses. ``columns`` maps a table
    that survives to the columns the downgrade drops. A row refuses when one of
    those columns holds a value other than the column default (NULL when it has
    none), because re-upgrading restores only the default. Generated columns
    are recomputed on re-upgrade and are not checked.

    Every named table is locked first, so no write lands between the check and
    the drop. The migration lock timeout bounds that wait.
    """
    dropped_columns = {table: tuple(names) for table, names in (columns or {}).items()}
    relations = list(dict.fromkeys([*tables, *dropped_columns]))
    if not relations:
        raise ValueError("refuse_populated_drop needs at least one table")
    for name in [*relations, *(c for names in dropped_columns.values() for c in names)]:
        if not _IDENTIFIER.fullmatch(name):
            raise ValueError(f"not a plain identifier: {name!r}")
    if context.is_offline_mode():
        raise PopulatedDowngradeRefused(
            f"downgrade of {revision} refused: offline (--sql) mode cannot check {SCHEMA} data."
            " Migrations are forward-only (ADR 0016); restore a backup instead."
        )
    bind = op.get_bind()
    op.execute("LOCK TABLE " + ",".join(f"{SCHEMA}.{name}" for name in relations) + " IN ACCESS EXCLUSIVE MODE")
    populated: list[str] = []
    for table in tables:
        rows = bind.exec_driver_sql(f"SELECT count(*) FROM {SCHEMA}.{table}").scalar_one()
        if rows:
            populated.append(f"{SCHEMA}.{table} ({rows} {'row' if rows == 1 else 'rows'})")
    for table, names in dropped_columns.items():
        for column in names:
            found = bind.execute(
                sa.text(
                    "SELECT column_default, is_generated FROM information_schema.columns"
                    " WHERE table_schema = :schema AND table_name = :table AND column_name = :column"
                ),
                {"schema": SCHEMA, "table": table, "column": column},
            ).one_or_none()
            if found is None:
                raise RuntimeError(f"downgrade of {revision}: column {SCHEMA}.{table}.{column} does not exist")
            default, generated = found
            if generated == "ALWAYS":
                continue
            # The default expression comes from the catalog, not from input.
            rows = bind.exec_driver_sql(
                f"SELECT count(*) FROM {SCHEMA}.{table} WHERE {column} IS DISTINCT FROM ({default or 'NULL'})"
            ).scalar_one()
            if rows:
                differ = "row differs" if rows == 1 else "rows differ"
                populated.append(f"{SCHEMA}.{table}.{column} ({rows} {differ} from the default)")
    if populated:
        raise PopulatedDowngradeRefused(
            f"downgrade of {revision} refused: {', '.join(populated)} would be dropped."
            " Migrations are forward-only (ADR 0016); restore a backup taken before the upgrade instead."
        )
