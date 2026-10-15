# Explicit local Ask project setup

This command prepares a scope for the supported Ask launcher. It does not start
a listener/model, change the R0 demo, or complete R1/G1. Use a dedicated database
with current migrations and an existing connection supplied through
`PANESTRIA_DATABASE_URL`; never commit that value. Preserve the owner's review
and demo databases when testing.

Choose two stable UUIDs and retain them as your owner and Ask project identities:

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
