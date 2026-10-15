# Bounded profile ciphertext vault

This task depends on the key adapter in PR #54. It implements the database and
trusted local service part of AOS-011-S5/S6, initially disabled. API/context
dispatch and whole-case qualification remain separate. Existing memory sources,
FTS, contexts, applied migrations and historical evidence stay unchanged.

Use the pinned upstream AESGCM implementation, a 256-bit scoped OS key and fresh
96-bit random nonce. Authenticate schema, algorithm, RESTRICTED class, owner,
project, profile, immutable revision identity/version, key handle, consent actor
and reference. Store only ciphertext, nonce, ciphertext digest and routing/audit
metadata in new tables. Do not store a low-entropy plaintext hash, field values,
FTS/embedding representation, plaintext file or database key copy.

One profile header points at immutable ciphertext revisions with optimistic
row-version checks. Composite foreign keys preserve scope and a deferred
current-revision foreign key prevents dangling committed pointers. Lifecycle
events append atomically through a database trigger; they contain identifiers
and state only. Corrections/rotation append rather than modifying old encrypted
rows. Suppression denies new reads; revisions and old backups remain until an
explicit future purge/retention operation accounts for their dependencies.

The service validates the actor's project, exact scoped handle and expected
version before key access. Key provisioning never occurs inside its caller-owned
transaction. Unknown/locked/missing keys, corrupt envelopes, ciphertext/metadata
swaps, malformed documents, nonce reuse, missing pointers and stale versions
deny. Writes never delete keys after failure. Populated-vault schema downgrade
refuses audit/data loss; use compatible restoration or reviewed forward repair.

Profile documents are bounded typed owner statements. Only explicitly approved
fields can later be selected for an authorized local purpose. All raw content
remains RESTRICTED; local Claude Code still performs cloud inference and cannot
receive it as an offline destination. Model inference, API/export and arbitrary
worker use are not enabled here. Import lint excludes key/vault modules from
worker and sandbox packages. That boundary supplements actual runtime sandbox
mount/bus controls; it cannot sandbox arbitrary same-user host code.

Tests use actual AES-GCM and disposable PostgreSQL with a test-only in-memory
key implementation. Include scope, tamper/AAD/nonce, CAS, transaction rollback,
immutable history, correction/suppression/expiry, actual pg_dump/pg_restore and
lost-key denial. Separate isolated OS key qualification does not replace vault
tests. No live provider data or real personal profile is needed. Python masks
secret representations but cannot guarantee erasure from process memory or
protection against host administrators. The feature remains off until its
whole runtime boundary is qualified.
