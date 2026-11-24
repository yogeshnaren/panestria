"""Migration safety on disposable PostgreSQL: forward-only downgrades, timeouts, N-1 upgrade.

ADR 0016 decision 5: migrations are forward-only and rollback means restoring
a backup. Every database here is a disposable CREATE DATABASE on the session
test server; synthetic data only.
"""

from __future__ import annotations

import importlib.util
import time
from typing import Any

import alembic
import psycopg
import pytest

from migration_harness import (
    ROOT,
    MigrationDatabase,
    assert_rows_preserved,
    current_head,
    disposable_database,
    previous_head,
    revisions,
    seed_representative_rows,
    upgrade_from_previous_head,
)

VERSIONS = ROOT / "migrations" / "versions"
# Revisions written before the shared guard existed; 0018 onward carry their own guards.
GUARDED = revisions()[:17]
assert GUARDED[-1] == "0017_worker_invocation"


def test_populated_downgrade_base_refuses_and_changes_nothing(r1_database: str) -> None:
    # The production-review shape: 30 goals and about 200 events on a real copy.
    with disposable_database(r1_database, "head", dbos=True, label="populated_base") as db:
        seed_representative_rows(db, goals=30, events_per_goal=7, approval=False)
        schema, data = db.schema_fingerprint(), db.data_snapshot()

        refused = db.alembic("downgrade", "base")

        assert refused.returncode != 0
        assert "downgrade of 0002_kernel refused" in refused.stderr
        assert "panestria.goal (30 rows)" in refused.stderr
        assert "panestria.task_event (210 rows)" in refused.stderr
        assert "forward-only (ADR 0016)" in refused.stderr
        # One transaction: the later downgrades that already ran are rolled back too.
        assert db.revision() == current_head()
        assert db.schema_fingerprint() == schema
        assert db.data_snapshot() == data


def test_populated_downgrade_refuses_at_the_newest_populated_revision(r1_database: str) -> None:
    with disposable_database(r1_database, "head", label="populated_approval") as db:
        seed_representative_rows(db, workflow=False)

        refused = db.alembic("downgrade", "base")

        assert refused.returncode != 0
        assert "downgrade of 0003_approval_preview refused" in refused.stderr
        assert "panestria.approval_request.preview (1 rows with non-default values)" in refused.stderr
        assert db.revision() == current_head()


def test_empty_downgrade_base_still_removes_the_schema(r1_database: str) -> None:
    with disposable_database(r1_database, "head", label="empty_base") as db:
        db.migrate("downgrade", "base")
        with db.connect() as c:
            assert c.execute("SELECT to_regnamespace('panestria')").fetchone() == (None,)
        db.migrate("upgrade", "head")
        assert db.revision() == current_head()


def test_dropped_columns_holding_defaults_do_not_block_downgrade(r1_database: str) -> None:
    # Re-upgrading restores the default, so nothing is lost; generated digests are recomputed.
    with disposable_database(r1_database, "0013_event_audit", label="default_columns") as db:
        seed_representative_rows(db, workflow=False)
        before = db.data_snapshot()

        db.migrate("downgrade", "0004_check_candidate")

        changes = {
            "panestria.task.max_attempts",
            "panestria.task.retry_at",
            "panestria.task_event.schema_version",
            "panestria.task_event.privacy_label",
            "panestria.task_event.sha256",
            "panestria.project.policy_version",
        }
        remaining = db.data_snapshot()
        assert_rows_preserved({k: v for k, v in before.items() if k in remaining}, db, changes=changes)


@pytest.mark.parametrize(
    ("revision", "target", "change", "refusal"),
    [
        (
            "0005_leases",
            "0004_check_candidate",
            "UPDATE panestria.task SET max_attempts = 5",
            "panestria.task.max_attempts (2 rows with non-default values)",
        ),
        (
            "0008_policy",
            "0007_budgets",
            "UPDATE panestria.project SET policy_version = 1",
            "panestria.project.policy_version (1 rows with non-default values)",
        ),
    ],
)
def test_dropped_column_holding_owner_data_refuses(
    r1_database: str, revision: str, target: str, change: str, refusal: str
) -> None:
    with disposable_database(r1_database, revision, label="owner_column") as db:
        seed_representative_rows(db, workflow=False)
        with db.connect() as c:
            c.execute(change)

        refused = db.alembic("downgrade", target)

        assert refused.returncode != 0 and refusal in refused.stderr
        assert db.revision() == revision


def test_every_early_downgrade_declares_everything_it_drops(r1_database: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Observed catalog differences, not hand-written lists, define what each downgrade must guard."""
    monkeypatch.syspath_prepend(str(ROOT / "migrations"))
    import downgrade_guard

    observed: dict[str, dict[str, set[str]]] = {}
    with disposable_database(r1_database, None, label="guard_catalog") as db:
        previous = _catalog(db)
        for revision in GUARDED:
            db.migrate("upgrade", revision)
            current = _catalog(db)
            observed[revision] = {
                "tables": set(current) - set(previous),
                "columns": {
                    f"{table}.{column}"
                    for table in previous
                    for column, generated in current[table].items()
                    if column not in previous[table] and not generated
                },
            }
            previous = current

    for revision in GUARDED:
        calls, statements = _record_downgrade(revision, monkeypatch, downgrade_guard)
        drops = observed[revision]
        if not drops["tables"] and not drops["columns"]:
            assert calls == [], f"{revision} drops nothing"
            continue
        assert len(calls) == 1, f"{revision} must call refuse_populated_drop exactly once"
        call = calls[0]
        assert call["revision"] == revision
        assert call["before"] == 0, f"{revision} must check before its first statement"
        assert call["tables"] == drops["tables"], revision
        assert call["columns"] == drops["columns"], revision
        assert statements, revision


def test_offline_downgrade_cannot_check_data_and_refuses(r1_database: str) -> None:
    refused = MigrationDatabase(r1_database).alembic("downgrade", "0003_approval_preview:0002_kernel", "--sql")
    assert refused.returncode != 0
    assert "offline (--sql) mode cannot check panestria data" in refused.stderr


def _live_write_traffic(db: MigrationDatabase) -> psycopg.Connection[tuple[Any, ...]]:
    """Hold what an open write transaction holds: ROW EXCLUSIVE on every table and a version row lock."""
    holder = db.connect()
    tables = holder.execute(
        "SELECT string_agg(format('%I.%I', schemaname, tablename), ',') FROM pg_tables WHERE schemaname='panestria'"
    ).fetchone()
    assert tables is not None
    holder.execute(f"LOCK TABLE {tables[0]} IN ROW EXCLUSIVE MODE")
    holder.execute("SELECT version_num FROM public.alembic_version FOR UPDATE")
    return holder


def test_blocked_upgrade_fails_fast_on_the_lock_timeout(r1_database: str) -> None:
    with disposable_database(r1_database, previous_head(), label="lock_timeout") as db:
        holder = _live_write_traffic(db)
        try:
            started = time.monotonic()
            blocked = db.alembic("upgrade", "head", timeout=90)
            elapsed = time.monotonic() - started
        finally:
            holder.rollback()
            holder.close()

        assert blocked.returncode != 0
        assert "canceling statement due to lock timeout" in blocked.stderr
        assert elapsed < 45, "the default lock timeout must stop a blocked migration within seconds"
        assert db.revision() == previous_head()
        db.migrate("upgrade", "head")


def test_statement_timeout_bounds_a_statement_and_both_timeouts_can_be_overridden(r1_database: str) -> None:
    with disposable_database(r1_database, previous_head(), label="statement_timeout") as db:
        holder = _live_write_traffic(db)
        try:
            blocked = db.alembic("-x", "lock_timeout=0", "-x", "statement_timeout=1s", "upgrade", "head", timeout=90)
        finally:
            holder.rollback()
            holder.close()

        assert blocked.returncode != 0
        assert "canceling statement due to statement timeout" in blocked.stderr
        assert db.revision() == previous_head()


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["-x", "lock_timeout=5s; RESET ALL"], "lock_timeout must be a PostgreSQL duration"),
        (["-x", "statement_timeout=forever"], "statement_timeout must be a PostgreSQL duration"),
        (["-x", "lock_timeot=5s"], "unknown migration argument: lock_timeot"),
    ],
)
def test_timeout_arguments_are_validated_before_connecting(
    r1_database: str, arguments: list[str], message: str
) -> None:
    refused = MigrationDatabase(r1_database).alembic(*arguments, "upgrade", "head")
    assert refused.returncode != 0 and message in refused.stderr


def test_offline_upgrade_script_sets_both_timeouts_first(r1_database: str) -> None:
    script = MigrationDatabase(r1_database).alembic(
        "upgrade", "0041_memory_restricted_fts:0042_task_event_kind_indexes", "--sql"
    )
    assert script.returncode == 0, script.stderr
    lock = script.stdout.index("SET lock_timeout = '5s';")
    statement = script.stdout.index("SET statement_timeout = '5min';")
    assert max(lock, statement) < script.stdout.index("CREATE INDEX")


def test_upgrade_from_previous_head_preserves_data_and_matches_a_fresh_install(r1_database: str) -> None:
    result = upgrade_from_previous_head(r1_database)
    created = result["created"]
    assert len(result["after"]["panestria.goal"]["rows"]) == len(created["goals"])
    workflows = result["after"]["dbos.workflow_status"]
    status = workflows["columns"].index("status")
    assert [row[status] for row in workflows["rows"]] == ["ENQUEUED"]


def test_harness_detects_changed_rows_and_schema_drift(r1_database: str) -> None:
    with disposable_database(r1_database, "head", dbos=True, label="harness_drift") as db:
        seed_representative_rows(db, workflow=False)
        before = db.data_snapshot()
        schema = db.schema_fingerprint()
        with db.connect() as c:
            c.execute("UPDATE panestria.goal SET intent = 'rewritten' WHERE intent = 'harness goal 0'")
            c.execute("ALTER TABLE panestria.goal ADD COLUMN drift_probe text")
        with pytest.raises(AssertionError, match="panestria.goal: rows changed"):
            assert_rows_preserved(before, db)
        assert_rows_preserved(before, db, changes={"panestria.goal.intent"})
        assert db.schema_fingerprint() != schema


def _catalog(db: MigrationDatabase) -> dict[str, dict[str, bool]]:
    """{table: {column: is_generated}} for ordinary tables in the product schema."""
    catalog: dict[str, dict[str, bool]] = {}
    with db.connect() as c:
        rows = c.execute(
            "SELECT c.relname, a.attname, a.attgenerated <> '' FROM pg_class c"
            " JOIN pg_namespace n ON n.oid = c.relnamespace JOIN pg_attribute a ON a.attrelid = c.oid"
            " WHERE n.nspname = 'panestria' AND c.relkind IN ('r', 'p') AND a.attnum > 0 AND NOT a.attisdropped"
        ).fetchall()
    for table, column, generated in rows:
        catalog.setdefault(table, {})[column] = generated
    return catalog


def _record_downgrade(
    revision: str, monkeypatch: pytest.MonkeyPatch, guard_module: Any
) -> tuple[list[dict[str, Any]], list[str]]:
    """Run one migration's downgrade() against recorders instead of a database."""
    statements: list[str] = []
    calls: list[dict[str, Any]] = []

    class RecordingOp:
        def execute(self, statement: object) -> None:
            statements.append(str(statement))

        def __getattr__(self, name: str) -> Any:
            raise AssertionError(f"{revision} downgrade uses op.{name}; teach the recorder")

    def guard(name: str, *, tables: tuple[str, ...] = (), columns: dict[str, tuple[str, ...]] | None = None) -> None:
        calls.append(
            {
                "revision": name,
                "before": len(statements),
                "tables": set(tables),
                "columns": {f"{table}.{column}" for table, names in (columns or {}).items() for column in names},
            }
        )

    monkeypatch.setattr(alembic, "op", RecordingOp())
    monkeypatch.setattr(guard_module, "refuse_populated_drop", guard)
    path = next(VERSIONS.glob(f"{revision}.py"))
    spec = importlib.util.spec_from_file_location(f"recorded_{revision}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.downgrade()
    return calls, statements
