# Explicit local profile-key setup

The local CLI can provision or check scoped OS encryption keys independently of
the HTTP API. It does not enable profiles, unlock/create a keyring collection,
change provider credentials, delete keys or trigger inference. The existing
persistent default Secret Service collection must already be unlocked by its
owner. The actual owner collection has not been modified by implementation tests.

For an explicitly chosen owner/project, use their UUIDs from trusted local
configuration. `key-create` generates opaque profile/key UUIDs when omitted:

```sh
uv run --frozen panestria profile key-create --owner-id "$OWNER_ID" --project-id "$PROJECT_ID"
uv run --frozen panestria profile key-check --owner-id "$OWNER_ID" --project-id "$PROJECT_ID" \
  --profile-id "$PROFILE_ID" --key-id "$KEY_ID"
```

Successful output contains only schema version, PRESENT status and the four
opaque identifiers. Retain those identifiers. To retry an explicitly known
handle idempotently, supply all four to `key-create`; omitting IDs creates a new
intent. To prepare rotation, keep the same profile ID and choose a fresh key ID.
Existing backups still need their old keys. No key bytes or key fingerprint are
printed, accepted in arguments, or written to a fallback file/environment.

Unavailable/locked/missing stores fail with a fixed code and exit 2. A valid
handle is included on failure so an unknown creation can be reconciled with
`key-check`. Do not silently generate another identity, retry an ambiguous
creation, delete an orphan or discard keys needed by retained snapshots.
The commands operate in the current OS user's secret store; UUIDs are routing
metadata and do not grant a different host user or worker secret-store authority.

```sh
uv run --frozen pytest tests/integration/test_profile_key_cli.py -q
uv run --frozen pytest tests/integration/test_profile_keys_live.py -m live -q
```

Six fake-store CLI checks prove operation separation, handle preservation and
redaction. The actual isolated D-Bus/GNOME Keyring test invokes both CLI commands
and verifies the same key through the real adapter, including lock denial and
daemon restart. These synthetic tests do not touch the desktop owner's keyring
and do not qualify complete profile setup, model dispatch or a release gate.
