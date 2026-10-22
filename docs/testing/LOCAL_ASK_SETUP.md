# Explicit local Ask project setup

This command prepares a scope for the supported Ask launcher. It does not start
a listener/model, change the R0 demo, or complete R1/G1. Use a dedicated database
with current migrations and an existing connection supplied through
`PANESTRIA_DATABASE_URL`; never commit that value. Preserve the owner's review
and demo databases when testing.

## Recommended first run

Use an already configured, dedicated PostgreSQL database and an existing
dedicated model cache containing only `blobs` and `manifests`. Export its
`PANESTRIA_DATABASE_URL` privately, then run:

```sh
uv run --frozen alembic -c migrations/alembic.ini upgrade head
uv run --frozen panestria local init --offline-ask \
  --directory "$HOME/panestria-local-ask" \
  --model-cache /absolute/existing/public-model-cache --port 8768
```

The new directory must have an existing parent; use its absolute canonical path.
The command creates it with mode700, stores private mode600 `local.json` and
`local.token`, generates stable owner/project IDs and commits the existing
offline-only setup transaction. No UUID editing or pasted Python is needed.
It does not provision a database, apply migrations, verify model bytes, start a
server/model, download anything or grant cloud/Build/research permissions. The
existing server launcher validates model bytes and resource admission at startup.

Expect `status: CONFIGURED`, `server_started: false`, a policy reference and two
commands in `next_steps`. Run `panestria local serve --config ...` in terminal A
with the same private database environment, then `panestria tui --config ...` in
terminal B. See [the keyboard guide](LOCAL_ASK_TUI.md) for what the screen does.
For the optional production Mission Control page, use the same local settings
with explicit `--mission-assets` as described in the
[offline Ask browser guide](MISSION_OFFLINE_ASK.md). The default page and TUI
remain available; the separate metadata observer cannot submit questions.

An identical `init` retry keeps the same file bytes and identities; completed
setup returns `replayed: true`. A database error retains the settings for retry
after fixing that connection. A concurrent initializer is refused, and changing
the cache/port cannot overwrite the existing settings. Existing unsafe, mixed
or incomplete files are preserved and refused; do not delete them to force a
retry. If a crash left valid `local.json` but no token **before the server was
ever started**, inspect that config, use the existing `local token-create`
command for its exact missing `local.token`, then retry with the same arguments.
An existing deployment with a lost token needs an explicit credential recovery
decision; this command does not rotate it automatically.

`database_schema_not_current` means the selected database is not migrated to the
application's current schema. `database_unavailable` requires connection/startup
repair. Paths and credentials are not echoed in failure diagnostics. Never put
the private directory or database environment file in Git.

## Existing manually configured scope

The lower-level command remains available when retaining explicit known IDs:

```sh
uv run --frozen alembic -c migrations/alembic.ini upgrade head
uv run --frozen panestria local setup --offline-ask \
  --owner-id YOUR_OWNER_UUID --project-id YOUR_PROJECT_UUID
```

Expect `status: CONFIGURED`, a `project-policy:1:…` reference and `replayed: false`.
An identical retry returns `replayed: true` without a new revision/audit row.
There is no generated goal/task. Existing names, paths and ownership are
preserved. Missing intent or invalid UUID/configuration fails before writes.
Another owner's project returns `not_found`; a different existing policy returns
`local_setup_policy_conflict` and stays unchanged.

The resulting SYNTHETIC_DEV policy is **uncertified** and permits only local
read. Cloud destinations, spending, tools, edits, merges and deletion are denied.
This does not replace certified Build setup or grant personal data/model/harness
access. Profiles remain disabled by default, with separate explicit setup.

The immutable `local_project_setup` receipt shares the global event sequence and
commits atomically with policy. Preserve it in backups. Populated downgrade is
refused; use reviewed forward repair or backup restoration. Eight local checks
passed using real disposable PostgreSQL, concurrent setup, injected rollback,
scope/policy denials, actual pg_dump/pg_restore and schema reapply; no provider
calls or owner database changes:

```sh
uv run --frozen pytest tests/integration/test_local_setup.py \
  tests/integration/test_aos_002_migration.py -q
```
