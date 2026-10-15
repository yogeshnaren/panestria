# Explicit local owner profile API checks

These routes are separately mounted with `mount_profile_api` and a trusted
ProfileVault. They remain absent from the default launcher; the vault is disabled
by default. No real profile or owner keyring is needed for the tests:

```sh
uv run --frozen pytest tests/integration/test_profile_api.py \
  tests/integration/test_profile_context.py tests/integration/test_profile_vault.py \
  tests/integration/test_profile_vault_restore.py \
  tests/integration/test_browser_v2_session.py -q
```

Use the existing scoped CLI bearer or paired browser session. Browser POSTs
require the exact Origin and CSRF header. Pair again if using the old `/v1`-only
cookie; the compatibility fix installs one application-path cookie and removes
the old path. Every operation rechecks session authority inside its transaction.

All input objects require integer `schema_version: 1`. Contracts:

- POST `/v2/profiles`: opaque `profile_id`, existing scoped `key_id`,
  `intent: SAVE_RESTRICTED_PROFILE` and bounded `document`.
- POST `/v2/profiles/{id}/correct`: exact `expected_version`, existing scoped
  `key_id`, the same explicit intent and complete new document. An explicitly
  provisioned new key handle rotates the new revision while old keys remain.
- POST `/v2/profiles/{id}/view`: exact `expected_version` and
  `purpose: OWNER_REVIEW`. Only this explicit owner action returns clear values.
- POST `/v2/profiles/{id}/suppress`: exact `expected_version`; no key required.

The document has typed owner-statement fields, optional explicit local-context
field approval and expiry. Every raw profile is RESTRICTED. Owner/project/consent
actor derive from authentication; the server generates each consent-action ID.
Requests cannot supply approval flags, key bytes, store configuration, project
overrides or provider credentials. HTTP cannot provision/unlock/delete keys or
trigger inference. Clear views and errors have no-store/no-referrer headers.

Tests cover lifecycle/ciphertext persistence, consent identity, paired-browser
CSRF, Host/Origin/auth, transaction-time session revocation, scope, exact schema
versions, input/HTTP byte limits, fixed-error redaction, stale views before key
access, duplicate creation and missing-key denial. Component pass does not
qualify actual profile setup/runtime dispatch or complete the MVP privacy cases.
Phone/read-only device routes must not inherit this owner credential scope.
