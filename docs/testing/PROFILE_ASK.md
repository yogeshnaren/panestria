# Restricted profile Ask checks

The optional version-2 Ask route reuses the local-only Ask pipeline. Its profile
API/vault must be separately configured and explicitly enabled; default launchers
still do not enable personal profiles. Required actual runtime qualification is
separate from these component checks.

```sh
uv run --frozen pytest tests/integration/test_profile_ask.py \
  tests/integration/test_profile_ask_api.py tests/integration/test_profile_ask_restore.py \
  tests/integration/test_profile_vault_restore.py tests/integration/test_ask_api.py \
  tests/integration/test_ask_kernel.py tests/integration/test_aos_002_migration.py -q
```

POST `/v2/ask` accepts the ordinary bounded Ask fields plus integer
`schema_version: 2` and a `profile` selection object: `profile_id`, exact
`expected_row_version`, approved `fields`, explicit `purpose`,
`destination: OFFLINE_LOCAL_MODEL` and optional bounded `max_bytes`. Privacy is
fixed to RESTRICTED, offline is true and response retention is false. Numeric
boolean aliases, class downgrades and extra authority fields are rejected.

The ordinary question/reference context compiles separately. Its metadata and
digests persist as before; its body does not. Profile values bypass that search/
fingerprint path and join only the in-memory prompt. An immutable scoped binding
stores the ciphertext revision, selection metadata and payload-manifest digest,
without profile text or an unkeyed digest of the combined prompt. Claim checks
the current profile/policy, stored binding, protected bytes, complete prompt and
inference limits before local dispatch. No cloud or harness fallback exists.

Profile answers can reproduce a private field. Their receipts therefore use
`response_digest_mode: OMITTED_RESTRICTED_PROFILE` with `response_sha256: null`;
they retain usage, state and protected source references, without an unkeyed
answer digest. Version-1 requests keep their original completion/hash invariant.
The database rejects ordinary requests that opt out, late profile bindings on
ordinary requests and changes to an admitted receipt mode. Existing clear-output
fingerprint feedback cannot silently retain these profile answers.

Browser calls require the same scoped session, exact Origin and CSRF. Replies
use no-store headers. Replay returns a receipt without rerunning inference or
returning the answer again. A known resource-probe failure records UNAVAILABLE;
a database outage retains durable admission for later deadline reconciliation.
Corrections, rotation, suppression, expiry or policy changes invalidate pending
profile selections. Previously delivered content cannot be recalled.

Tests use actual crypto/PostgreSQL and actual dump/restore, plus mock local
transport for HTTP orchestration. They cover tamper/stale/scope/manifest checks,
source and inference forgery, omitted fingerprints, version-1 compatibility,
resource denial, restore/lost keys and downgrade refusal. Full exact-head CI and
actual OS/model/sandbox/egress evidence are required before runtime enablement;
these results do not complete TC06–TC08 or certify a release gate.
