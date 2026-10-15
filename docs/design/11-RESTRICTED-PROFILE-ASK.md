# Restricted profile Ask overlay

This work depends on owner API PR #58 and the approved-field selector. Default
profile use remains disabled; actual local runtime privacy qualification is
required before enabling it. Preserve all version-1 Ask contracts/attempts.

Source inspection corrects an earlier design assumption: ContextCompiler stores
source metadata and prompt/question digests, not the prompt body. Profile values
still must bypass its search/fingerprint path. Compile the ordinary question and
general-memory context separately, reserve the explicit profile overlay's byte
budget, and combine only in memory. Inputs and outputs derived from the raw
profile are RESTRICTED, offline and non-retained. No provider fallback exists.

A version-2 Ask submission explicitly binds one ProfileSelectionRequest and
fixes its privacy class to RESTRICTED. The trusted local selector checks owner
approval, purpose, scope, key availability, current revision/expiry/suppression
and current policy. Store an immutable, scoped request-to-ciphertext-revision
binding and a metadata-only payload manifest; never store the overlay text or
its unkeyed plaintext fingerprint. The manifest binds the general pack hash,
profile ciphertext identity/digest, selection request, policy and render version.

Prepared admission retains the masked selection in memory. Claim must validate
the persisted binding, ordinary pack, current policy, reconstructed selected
fields and complete in-memory prompt before dispatch. Correction/rotation,
approval changes, suppression, expiry, stale session/policy and tampering deny.
No captured transcript/profile content becomes a tool grant or model memory.
Loss of the in-memory request follows existing Ask timeout/recovery semantics;
do not relabel an uncertain model invocation as a completed/cheap retry.

Ordinary Ask requires a response SHA-256 for COMPLETED receipts. A short answer
can reproduce a profile fact, so retaining its unkeyed hash would undermine this
boundary. Add a versioned receipt mode for profile requests that omits the
response digest and retains usage/status only. Preserve the old invariant for
every legacy/default request. A deferred database binding check allows omission
only for an actual scoped restricted-profile request. The mode is immutable;
an ordinary request cannot opt out of its receipt contract. Existing feedback
that requires a public content fingerprint cannot implicitly retain these
outputs; separately consented encrypted feedback is later work.

Reuse the existing local-provider-only Ask admission, resource governor,
deadline, cancellation and transaction-time session checks. Factor shared route
execution rather than copying its state machine. No launcher or environment
flag can silently enable personal profiles. Tests use real PostgreSQL/crypto,
mock local transport for route failures, and a separately scoped actual local
engine/OS key-store boundary test before enablement. Include stale and forged
binding/prompt/label/selection cases, no FTS/input/output fingerprints or plaintext
in database/logs, v1 compatibility, actual restore, downgrade refusal, resource
denial/cancel/deadline and retry semantics. Do not claim a live pass from mocks.
