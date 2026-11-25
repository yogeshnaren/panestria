# Migration safety and the N-1 upgrade harness

Production-readiness plan item 1.19. Release 1 migrations are forward-only
([ADR 0016](../../adr/0016-self-hosted-release-1-scope.md), decision 5): to roll
back, restore a backup taken before the upgrade. This page covers what protects
a migration run and what every later migration PR must prove.

## What protects a migration run

- **Timeouts.** `migrations/env.py` sets `lock_timeout = 5s` and
  `statement_timeout = 5min` on the migration session. A migration blocked by
  live traffic fails within seconds and rolls back, instead of queueing every
  later query on the table behind its lock. To retry, stop the server or wait
  until it is idle. One run can raise either value:
  `alembic -c migrations/alembic.ini -x lock_timeout=30s -x statement_timeout=30min upgrade head`.
  Unknown `-x` arguments and values that are not PostgreSQL durations are refused.
- **Populated downgrades refuse.** Each downgrade calls
  `refuse_populated_drop` from `migrations/downgrade_guard.py` before its first
  statement. The guard locks every table it names. It refuses when a dropped
  table has rows, or a dropped column holds a value other than its default.
  The whole alembic run is one transaction, so a refusal also undoes the
  downgrades that ran before it. Offline `--sql` downgrades refuse because they
  cannot check data. No override exists. A test that must downgrade a populated
  disposable copy empties it first, as `test_aos_002_migration.py` does.
  Migrations 0018–0042 predate the shared guard and carry equivalent inline
  guards: each checks a root table, and every child table it drops has a
  NOT NULL foreign key chain to that root.
- **No product downgrade.** The `panestria` CLI has no downgrade or rollback
  command or option. No product module calls an alembic downgrade.
  `tests/contract/test_forward_only_migrations.py` enforces both.

## Installed package: `panestria db`

An installed wheel carries the migrations under `panestria/_migrations` and
runs them with `panestria db`. It reads `PANESTRIA_DATABASE_URL`, as the other
commands do, and prints JSON. A source checkout uses the `migrations/`
directory it already has.

- `panestria db status` prints `current` (null for an empty database), the
  `head` this package ships and `current_is_head`.
- `panestria db upgrade` applies every packaged migration through head and
  prints `UPGRADED` with `from` and `to`, or `CURRENT` when nothing was needed.
  `--lock-timeout` and `--statement-timeout` raise the defaults for one run.
- Refusals print `{"code": …}` on stderr and exit 2:

| Code | Meaning |
|---|---|
| `invalid_database_url` | `PANESTRIA_DATABASE_URL` is missing or not a PostgreSQL URL. |
| `invalid_migration_timeout` | A timeout is not a PostgreSQL duration such as `5s` or `10min`. Nothing connected. |
| `database_unavailable` | The database could not be reached. |
| `database_schema_newer_than_package` | A newer release migrated this database. Install that release, or restore the backup taken before it. |
| `migration_lock_timeout` | Live traffic held a lock past the lock timeout. Nothing changed; retry while the server is idle. |
| `migration_statement_timeout` | One statement ran past the statement timeout. Nothing changed. |
| `migration_failed`, `migration_incomplete` | The run failed or stopped short of head. The run is one transaction, so nothing changed. |
| `packaged_asset_missing` | The installed package has no migrations. Reinstall it. |

## What a migration PR adds

1. **A guarded downgrade.** Call
   `refuse_populated_drop(revision, tables=(...), columns={table: (...)})` first,
   naming every table and every non-generated column the downgrade drops.
2. **An N-1 upgrade test** with `upgrade_from_previous_head` from
   `tests/migration_harness.py`:

   ```python
   from migration_harness import MigrationDatabase, upgrade_from_previous_head


   def test_upgrade_from_previous_head_keeps_data(r1_database: str) -> None:
       def seed(db: MigrationDatabase) -> None:
           with db.connect() as c:  # at head-1, before this PR's migration
               c.execute("INSERT INTO panestria.<table this migration changes> ...")

       def check(db: MigrationDatabase) -> None:
           with db.connect() as c:  # at head
               assert c.execute("SELECT <new column> FROM panestria.<table>").fetchall() == [...]

       upgrade_from_previous_head(r1_database, seed=seed, check=check)
   ```

   The harness:
   - migrates a disposable database to head-1 and creates the DBOS system
     schema, as the runtime does;
   - inserts representative rows: goal chains, events, an approval and an
     enqueued DBOS workflow. Then it runs your `seed`;
   - upgrades to head under the production timeouts;
   - asserts that every earlier row in `panestria` and `dbos` is unchanged in
     its original columns;
   - asserts that the full schema of both schemas equals a fresh head install
     with DBOS;
   - runs your `check`.

   A migration that rewrites data lists the affected `"schema.table"` or
   `"schema.table.column"` entries in `changes=`, and its `check` asserts the
   new values. Lower-level helpers (`disposable_database`, `seed_representative_rows`,
   `assert_rows_preserved`, `MigrationDatabase.schema_fingerprint` and
   `data_snapshot`) are available for targeted tests.
3. **Representative rows that still insert.** If the migration changes a shape
   that `seed_representative_rows` uses, update it in the same PR so it
   describes a real database at head-1.

## Running

The tests need Docker and the pinned PostgreSQL image. Each test creates and
drops its own database on the session container started by `r1_database`. They
never touch the owner's review database.

```sh
uv run --frozen pytest tests/integration/test_migration_safety.py tests/contract/test_forward_only_migrations.py -q
```

`test_migration_safety.py` runs in the platform CI lane, and the contract test
runs in the fast lane.
