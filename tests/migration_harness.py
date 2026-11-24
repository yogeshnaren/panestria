"""N-1 upgrade harness: every migration PR upgrades a populated previous-head database.

Every database in this module is a disposable ``CREATE DATABASE`` on the
session test server (``r1_database``). Nothing here touches another database.

How a migration PR uses it, in ``tests/integration/test_<feature>_migration.py``::

    from migration_harness import MigrationDatabase, upgrade_from_previous_head

    def test_upgrade_from_previous_head_keeps_data(r1_database: str) -> None:
        def seed(db: MigrationDatabase) -> None:
            with db.connect() as c:  # runs at head-1, before the new migration
                c.execute("INSERT INTO panestria.<table the migration changes> ...")

        def check(db: MigrationDatabase) -> None:
            with db.connect() as c:  # runs at head
                assert c.execute("SELECT <new column> FROM panestria.<table>").fetchall() == [...]

        upgrade_from_previous_head(r1_database, seed=seed, check=check)

``upgrade_from_previous_head`` then:

1. migrates a disposable database to head-1 and creates the DBOS system schema,
   as the product runtime does (``DBOS.migrate`` into schema ``dbos``);
2. inserts ``seed_representative_rows`` (a kernel goal chain, events, an
   approval and an enqueued DBOS workflow) and then the caller's ``seed``;
3. snapshots every row of every ``panestria`` and ``dbos`` table;
4. upgrades to head, under the production lock and statement timeouts;
5. asserts that every row present before is unchanged in its original columns.
   A migration that rewrites data names those ``"schema.table"`` or
   ``"schema.table.column"`` entries in ``changes``, and its ``check`` asserts
   their new values;
6. asserts that the schema (``panestria`` and ``dbos``: columns, defaults,
   constraints, indexes, triggers, functions, views, sequences, types, row
   security, grants) equals a fresh database migrated straight to head with the
   DBOS schema;
7. runs ``check`` and drops both databases.

When representative rows no longer insert at head-1, because a migration
changed the shape they use, update ``seed_representative_rows`` in the same PR.
The rows must describe what a real database at head-1 holds.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable, Collection, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
from alembic.config import Config
from alembic.script import ScriptDirectory
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = ROOT / "migrations" / "alembic.ini"
SCHEMAS = ("panestria", "dbos")

# Catalog description of every object a migration can create, change or drop.
_SCHEMA_SQL = """
SELECT 'column ' || table_schema || '.' || table_name || ' ' || column_name || ' ' || udt_name
    || ' null=' || is_nullable || ' default=' || coalesce(column_default, '')
    || ' generated=' || is_generated || ' ' || coalesce(generation_expression, '')
FROM information_schema.columns WHERE table_schema = ANY(%(schemas)s)
UNION ALL
SELECT 'relation ' || n.nspname || '.' || c.relname || ' kind=' || c.relkind::text
    || ' rls=' || c.relrowsecurity::text || ' force_rls=' || c.relforcerowsecurity::text
    || ' acl=' || coalesce(c.relacl::text, '')
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = ANY(%(schemas)s)
UNION ALL
SELECT 'constraint ' || c.conrelid::regclass::text || ' ' || c.conname || ' ' || pg_get_constraintdef(c.oid)
FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace WHERE n.nspname = ANY(%(schemas)s)
UNION ALL
SELECT 'index ' || indexdef FROM pg_indexes WHERE schemaname = ANY(%(schemas)s)
UNION ALL
SELECT 'trigger ' || pg_get_triggerdef(t.oid)
FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = ANY(%(schemas)s) AND NOT t.tgisinternal
UNION ALL
SELECT 'function ' || pg_get_functiondef(p.oid) || ' acl=' || coalesce(p.proacl::text, '')
FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = ANY(%(schemas)s) AND p.prokind IN ('f', 'p')
UNION ALL
SELECT 'view ' || schemaname || '.' || viewname || ' ' || definition FROM pg_views WHERE schemaname = ANY(%(schemas)s)
UNION ALL
SELECT 'sequence ' || schemaname || '.' || sequencename || ' ' || data_type::text || ' ' || increment_by
FROM pg_sequences WHERE schemaname = ANY(%(schemas)s)
UNION ALL
SELECT 'type ' || n.nspname || '.' || t.typname || ' ' || t.typtype::text
    || ' ' || coalesce((SELECT string_agg(e.enumlabel, ',' ORDER BY e.enumsortorder)
                        FROM pg_enum e WHERE e.enumtypid = t.oid), '')
FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
WHERE n.nspname = ANY(%(schemas)s) AND t.typtype IN ('e', 'd', 'c')
    AND NOT EXISTS (SELECT 1 FROM pg_class c WHERE c.oid = t.typrelid AND c.relkind <> 'c')
UNION ALL
SELECT 'policy ' || schemaname || '.' || tablename || ' ' || policyname || ' ' || cmd
    || ' ' || coalesce(qual, '') || ' ' || coalesce(with_check, '')
FROM pg_policies WHERE schemaname = ANY(%(schemas)s)
UNION ALL
SELECT 'schema ' || nspname || ' acl=' || coalesce(nspacl::text, '') FROM pg_namespace WHERE nspname = ANY(%(schemas)s)
UNION ALL
SELECT 'alembic_version ' || version_num FROM public.alembic_version
ORDER BY 1
"""

_TABLES_SQL = """
SELECT n.nspname, c.relname,
    array_agg(a.attname::text ORDER BY a.attnum) FILTER (WHERE a.attnum > 0 AND NOT a.attisdropped)
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_attribute a ON a.attrelid = c.oid
WHERE n.nspname = ANY(%(schemas)s) AND c.relkind IN ('r', 'p')
GROUP BY n.nspname, c.relname
ORDER BY 1, 2
"""


def revisions() -> list[str]:
    """Every revision from the first migration to head, oldest first."""
    script = ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))
    ordered = [rev.revision for rev in script.walk_revisions("base", "heads")]
    ordered.reverse()
    if len(script.get_heads()) != 1:
        raise AssertionError("single_migration_head_required")
    return ordered


def current_head() -> str:
    return revisions()[-1]


def previous_head() -> str:
    """Head-1: the revision a real database runs before this PR's migration."""
    return revisions()[-2]


def alembic(dsn: str, *args: str, timeout: float = 180) -> subprocess.CompletedProcess[str]:
    """Run the alembic CLI against ``dsn`` exactly as an operator would."""
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), *args],
        cwd=ROOT,
        env={**os.environ, "PANESTRIA_DATABASE_URL": dsn},
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


@dataclass(frozen=True)
class MigrationDatabase:
    """One disposable database on the test server."""

    dsn: str

    def connect(self, **kwargs: Any) -> psycopg.Connection[tuple[Any, ...]]:
        return psycopg.connect(self.dsn, **kwargs)

    def alembic(self, *args: str, timeout: float = 180) -> subprocess.CompletedProcess[str]:
        return alembic(self.dsn, *args, timeout=timeout)

    def migrate(self, direction: str, target: str) -> None:
        result = self.alembic(direction, target)
        assert result.returncode == 0, f"alembic {direction} {target} failed:\n{result.stderr}"

    def revision(self) -> str | None:
        with self.connect() as c:
            found = c.execute("SELECT to_regclass('public.alembic_version') IS NOT NULL").fetchone()
            if not found or not found[0]:
                return None
            row = c.execute("SELECT version_num FROM public.alembic_version").fetchone()
        return None if row is None else str(row[0])

    def migrate_dbos(self) -> None:
        """Create the DBOS system schema the way the product runtime does."""
        from dbos import DBOS

        from panestria.execution.dbos_runtime import DBOS_SCHEMA, sqlalchemy_url

        DBOS.migrate(sqlalchemy_url(self.dsn), schema=DBOS_SCHEMA)

    def schema_fingerprint(self) -> str:
        with self.connect() as c:
            rows = c.execute(_SCHEMA_SQL, {"schemas": list(SCHEMAS)}).fetchall()
        return "".join(f"{row[0]}\n" for row in rows)

    def data_snapshot(self) -> dict[str, dict[str, Any]]:
        """Every row of every table in the product and DBOS schemas, as text, order-independent."""
        snapshot: dict[str, dict[str, Any]] = {}
        with self.connect() as c:
            for schema, table, columns in c.execute(_TABLES_SQL, {"schemas": list(SCHEMAS)}).fetchall():
                snapshot[f"{schema}.{table}"] = {"columns": list(columns), "rows": _rows(c, schema, table, columns)}
        return snapshot


def _rows(
    connection: psycopg.Connection[tuple[Any, ...]], schema: str, table: str, columns: list[str]
) -> list[tuple[str | None, ...]]:
    query = sql.SQL("SELECT {} FROM {}.{}").format(
        sql.SQL(", ").join(sql.SQL("{}::text").format(sql.Identifier(column)) for column in columns),
        sql.Identifier(schema),
        sql.Identifier(table),
    )
    return sorted(connection.execute(query).fetchall(), key=lambda row: [(v is None, v or "") for v in row])


@contextmanager
def disposable_database(
    server_dsn: str, revision: str | None = "head", *, dbos: bool = False, label: str = "migration"
) -> Iterator[MigrationDatabase]:
    """Create a database on the test server, migrate it to ``revision`` and always drop it.

    ``revision=None`` leaves it empty (no alembic_version). ``dbos=True`` also
    creates the DBOS system schema after migrating.
    """
    name = f"panestria_{label}_{uuid4().hex[:16]}"
    if len(name) > 63:
        raise ValueError("database label too long")
    database = MigrationDatabase(server_dsn.rsplit("/", 1)[0] + "/" + name)
    with psycopg.connect(server_dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            if revision is not None:
                database.migrate("upgrade", revision)
            if dbos:
                database.migrate_dbos()
            yield database
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


# Fixed synthetic identities: one owner, one project and goal chains below them.
OWNER = "00000000-0000-4000-8000-00000000a001"
PROJECT = "00000000-0000-4000-8000-00000000a002"


def seed_representative_rows(
    db: MigrationDatabase,
    *,
    goals: int = 2,
    events_per_goal: int = 3,
    approval: bool = True,
    workflow: bool = True,
) -> dict[str, Any]:
    """Insert rows a real database holds: goal chains, events, an approval and a DBOS workflow.

    Plain SQL against the current schema, not product services: services follow
    head, while this runs at head-1. ``approval`` and ``workflow`` let older
    revisions or DBOS-less databases leave those parts out. Returns the
    identifiers it created.
    """
    created: dict[str, Any] = {"owner": OWNER, "project": PROJECT, "goals": [], "tasks": [], "events": 0}
    with db.connect() as c:
        c.execute("INSERT INTO panestria.principal(id, display_name) VALUES (%s, 'migration harness owner')", (OWNER,))
        c.execute("INSERT INTO panestria.project(id, owner_id) VALUES (%s, %s)", (PROJECT, OWNER))
        for index in range(goals):
            goal, contract, task, check = (str(uuid4()) for _ in range(4))
            c.execute(
                "INSERT INTO panestria.goal(id, owner_id, project_id, intent, status)"
                " VALUES (%s, %s, %s, %s, 'ACTIVE')",
                (goal, OWNER, PROJECT, f"harness goal {index}"),
            )
            body = {"autonomy_profile_ref": "test-policy-v1", "budget": {"max_api_usd": "1.000000"}}
            c.execute(
                "INSERT INTO panestria.goal_contract(id, goal_id, version, body, sha256)"
                " VALUES (%s, %s, 1, %s::jsonb, %s)",
                (contract, goal, json.dumps(body), f"{index:02x}" * 32),
            )
            c.execute(
                "INSERT INTO panestria.task(id, goal_id, contract_id, name, state)"
                " VALUES (%s, %s, %s, 'harness', 'READY')",
                (task, goal, contract),
            )
            c.execute(
                "INSERT INTO panestria.acceptance_check"
                " (id, contract_id, check_key, description, verifier_type, verifier_spec)"
                " VALUES (%s, %s, 'harness', 'harness', 'artifact-exists', %s::jsonb)",
                (check, contract, json.dumps({"type": "artifact-exists"})),
            )
            for event in range(events_per_goal):
                c.execute(
                    "INSERT INTO panestria.task_event(id, goal_id, task_id, kind, actor, payload)"
                    " VALUES (%s, %s, %s, 'goal.created', 'synthetic', %s::jsonb)",
                    (str(uuid4()), goal, task, json.dumps({"n": event})),
                )
            created["goals"].append(goal)
            created["tasks"].append(task)
            created["events"] += events_per_goal
        if approval:
            created["approval"] = _insert_approval(c, created["goals"][0], created["tasks"][0])
    if workflow:
        created["workflow"] = _enqueue_workflow(db, created["tasks"][0])
    return created


def _insert_approval(connection: psycopg.Connection[tuple[Any, ...]], goal: str, task: str) -> str:
    approval = str(uuid4())
    connection.execute(
        "INSERT INTO panestria.approval_request(id, goal_id, task_id, owner_id, project_id, minimum_actor_id,"
        " action_kind, effect_digest, policy_version, state, expires_at, preview)"
        " VALUES (%s, %s, %s, %s, %s, %s, 'merge', %s, 'synthetic-1', 'PENDING',"
        " now() + interval '1 hour', %s::jsonb)",
        (approval, goal, task, OWNER, PROJECT, OWNER, "ab" * 32, json.dumps({"action_kind": "merge"})),
    )
    return approval


def _enqueue_workflow(db: MigrationDatabase, task: str) -> str:
    """Leave one ENQUEUED DBOS workflow, as an admitted but not yet run task does."""
    from panestria.execution.dbos_runtime import QUEUE_NAME, WORKFLOW_NAME, open_client

    workflow = f"harness-{uuid4()}"
    engine, client = open_client(db.dsn)
    try:
        client.enqueue(
            {"queue_name": QUEUE_NAME, "workflow_name": WORKFLOW_NAME, "workflow_id": workflow}, task, "ab" * 32, 1
        )
    finally:
        client.destroy()
        engine.dispose()
    return workflow


def assert_rows_preserved(
    before: dict[str, dict[str, Any]], after_db: MigrationDatabase, *, changes: Collection[str] = ()
) -> None:
    """Every row in ``before`` reads back identically in its original columns, except named ``changes``."""
    with after_db.connect() as c:
        for name, table in before.items():
            if name in changes or not table["rows"]:
                continue
            schema, relation = name.split(".", 1)
            columns = [column for column in table["columns"] if f"{name}.{column}" not in changes]
            kept = [table["columns"].index(column) for column in columns]
            expected = sorted(
                (tuple(row[i] for i in kept) for row in table["rows"]), key=lambda r: [(v is None, v or "") for v in r]
            )
            assert _rows(c, schema, relation, columns) == expected, f"{name}: rows changed during upgrade"


def upgrade_from_previous_head(
    server_dsn: str,
    *,
    seed: Callable[[MigrationDatabase], None] | None = None,
    check: Callable[[MigrationDatabase], None] | None = None,
    changes: Collection[str] = (),
    start: str | None = None,
) -> dict[str, Any]:
    """Run the N-1 upgrade proof described in this module's docstring.

    ``start`` overrides head-1 only for proving the harness itself on an older
    step. Returns the representative row identifiers and both snapshots.
    """
    previous = start or previous_head()
    head = current_head()
    with disposable_database(server_dsn, previous, dbos=True, label="n_minus_one") as db:
        assert db.revision() == previous
        created = seed_representative_rows(db)
        if seed is not None:
            seed(db)
        before = db.data_snapshot()
        assert before["panestria.goal"]["rows"] and before["dbos.workflow_status"]["rows"], (
            "representative rows missing"
        )
        db.migrate("upgrade", "head")
        assert db.revision() == head
        assert_rows_preserved(before, db, changes=changes)
        with disposable_database(server_dsn, "head", dbos=True, label="fresh_head") as fresh:
            assert db.schema_fingerprint() == fresh.schema_fingerprint(), "upgraded schema differs from a fresh install"
        if check is not None:
            check(db)
        return {"created": created, "before": before, "after": db.data_snapshot()}
