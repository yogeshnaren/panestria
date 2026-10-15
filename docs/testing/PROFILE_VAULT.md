# Ciphertext profile storage checks

The trusted local `ProfileVault` service is disabled by default and has no
public API or model/worker dispatch path in this task. It uses the separately
qualified scoped OS key adapter, but requires explicit trusted setup before
loading any key. Do not put a real personal profile into a test fixture.

From this candidate checkout, with Docker available:

```sh
uv sync --frozen --group dev
uv run --frozen pytest tests/integration/test_profile_vault.py \
  tests/integration/test_profile_vault_restore.py \
  tests/integration/test_aos_002_migration.py -q
```

Tests use real AES-GCM and isolated PostgreSQL with a test-only in-memory key
store. They check scoped ciphertext-only writes, masked results, size/version
bounds, exact consent metadata, disabled defaults, corrupt ciphertext/AAD,
cross-profile/owner/project swaps even with a reused test key, stale/concurrent
corrections, missing keys, expiry, suppression, nonce uniqueness, immutable
history, transaction rollback and deferred pointer/scope constraints. Lifecycle
events share the existing global kernel counter. Schema round-trip/drift tests
use the newly generated active snapshot; historical evidence remains unchanged.

The restore test runs actual `pg_dump`/`pg_restore` for snapshots before and
after rotation. Keys remain external. Both snapshots work with their respective
retained keys; removing the old test key denies the old snapshot while the new
snapshot remains usable. Suppression survives restoration. No backup bytes,
key material or clear profile values are written to evidence. A populated-vault
downgrade fails without deleting history or changing the Alembic version.

[Component evidence](../../evidence/profile-vault-2026-10-15/report.json) records
the tested source and fixture hashes. It does not claim a complete TC06/TC07,
production key backup, profile-context integration, runtime worker isolation,
live provider conformance or release acceptance. The [OS backend test](PROFILE_KEYS.md)
remains separately scoped. Import boundaries supplement the existing sandbox;
they do not sandbox arbitrary same-user Python or prevent host-admin access.

Rollback uses compatible restore or reviewed forward repair once profile data
exists. Do not drop applied history or delete a wrapping key needed by retained
snapshots. Suppression blocks new reads; it cannot erase prior deliveries or
copies in old backups. Full-database rollback protection is not provided by
AEAD alone. The next task adds cacheless approved-field context selection and
scope-bound local setup/API admission, followed by actual runtime qualification.
