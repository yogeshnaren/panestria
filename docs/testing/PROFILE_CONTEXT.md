# Ephemeral approved profile context

The context foundation selects explicitly approved owner statements from the
encrypted vault for an offline local-model purpose. It does not enable Ask/API
dispatch or export profile text to a provider, worker, FTS or persistent context
pack. Profiles remain disabled by default.

```sh
uv run --frozen pytest tests/integration/test_profile_context.py -q
```

The tests use real ciphertext/database reads with synthetic in-memory test keys.
They prove selected-field minimization, explicit purpose restrictions, denial of
Claude Code/cloud/unqualified destinations, current policy enforcement, byte
bounds, missing-key denial, source/policy scope and stale/forged selection
rejection. Corrections, rotation, field-approval revocation, expiry, suppression
and policy changes invalidate previous selections; fresh contexts reflect the
new approved revision. Selection creates no database/cache entry containing
profile plaintext or its low-entropy fingerprint.

Response style may select preferred name and communication preferences only.
Other approved statements require the explicit owner-assistance purpose. Fields
are data; they cannot change tool permissions, honesty, privacy or source truth.
Protected values remain masked until an eventual trusted local inference
boundary unwraps them. Suppression cannot recall an already delivered value.

[Component evidence](../../evidence/profile-context-2026-10-15/report.json) is
source-bound. Actual OS key-store qualification and ciphertext backup tests are
separate. Full profile setup/API admission, local runtime dispatch/privacy and
TC06–TC08 acceptance remain pending. Do not feed this overlay into the existing
plaintext-persisting ContextCompiler. See [the design](../design/09-EPHEMERAL-PROFILE-CONTEXT.md)
and [storage checks](PROFILE_VAULT.md).
