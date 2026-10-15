# Canonical memory interfaces

The configured Ask API exposes `/v2/memory` alongside the compatible `/v1`
surface. Use the existing scoped CLI token or paired browser session; owner,
project, Host/Origin, CSRF and transaction reauthorization still apply. No
provider call is needed for memory operations. The old running demo does not
automatically gain routes from a newer source checkout.

POST `/v2/memory` accepts the normal bounded memory fields plus an explicit
integer `schema_version: 2`. `label` must be PUBLIC, INTERNAL, CONFIDENTIAL or
RESTRICTED. PRIVATE and UNKNOWN are rejected. The response gives the new item,
source, revision and row-version references, with schema version 2.

GET `/v2/memory/search?q=...` and `/v2/memory/{item_id}` return canonical primary
labels and source classification lineage. An old PRIVATE source appears as
RESTRICTED, with PRIVATE retained as `classification.original_label` in the
audit metadata. `/v1` source/history representations remain unchanged. Neither
view grants cloud permission or changes an old source/attempt identity.

Correction and review routes:

- POST `/v2/memory/{item_id}/correct`: `expected_version`, version-2 `document`,
  and optional `review_id`.
- POST `/v2/memory/{item_id}/privacy-review`: the same expected version/document,
  without a supplied review ID. The preview shows the effective old class and
  preserves the original legacy value separately.
- POST `/v2/memory-reviews/{review_id}/decision`: the exact `effect_digest` and
  `approve` or `deny`. A decision alone does not apply a correction.
- POST `/v2/memory/{item_id}/suppress`: the exact `expected_version`.

Lowering an effective class requires that exact one-use owner review. A v2
review cannot be consumed by a similar v1 document. Old PRIVATE is effectively
RESTRICTED when comparing downgrades. New contexts derive canonical classes;
missing/unknown provenance denies. Existing private pending packs keep their
original bytes/hash and are checked using restrictive effective semantics.

All four classes can be processed locally under the existing policy axes.
Current cloud policy and SDK defaults permit only PUBLIC. INTERNAL and
CONFIDENTIAL need future separately versioned class-specific grants; the legacy
allow_private_cloud flag cannot grant them. Restricted, unresolved legacy and
unknown inputs do not go to cloud providers or automatic fallback.

Migration 0019 changes active label constraints without rewriting rows. Once
INTERNAL/CONFIDENTIAL records exist, downgrade refuses to discard or relabel
them. Use forward repair or an explicitly reviewed compatible backup.

Run affected checks from this candidate checkout with Docker available:

```bash
uv run --frozen pytest tests/integration/test_canonical_memory_v2.py \
  tests/integration/test_classification_ledger.py \
  tests/integration/test_memory_api.py tests/integration/test_memory_restore.py
```

These use disposable databases and synthetic data. Required live provider,
host, phone and owner-trial checks remain separate. Classification progress is
not encrypted-profile enablement or full MVP acceptance.
