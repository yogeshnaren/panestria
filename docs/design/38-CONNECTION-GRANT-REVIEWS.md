# Owner-reviewed connection declarations

Start from verified main66cf31c, after PR87. This is the durable declaration and
review part of MVP-X09/AOS-008-S4. It prepares the grant broker prerequisite for
research admission; it does not certify a connector or enable any network/tool.

An immutable manifest names owner/project, connector/version/configuration pin,
opaque account and enrolled-root references, exact HTTPS origins, independent
read/write/send/delete/spend actions, canonical data classes, bounded calls/bytes/
cash/wall time, expiry and optional conformance reference. No credentials, raw
filesystem paths, arbitrary commands, browser profiles or worker environment.
Origins are syntax-scoped, never proof of public DNS/TLS safety. Root references
still need actual protected enrollment and descriptor-based broker validation.

The authenticated controller supplies Actor and an existing scoped task. Proposal
and owner decision bind an exact digest, current project-policy reference,
expected grant version and a15-minute review deadline. Replacement grants expire
within30days. Revoke uses the actual current immutable manifest, not a client
substitute. Approval atomically appends a revision and decision; denial preserves
the proposal without changing the current revision. Exact retries are replayed;
changed retry/decision, stale versions, wrong owner/project, expired review or
changed policy deny. Caller transactions own all writes and events on the same
PostgreSQL database; project/grant/task locks precede the global event lock.

Keep immutable proposals/decisions/revisions, one monotonic current pointer and
deferred database consistency checks. No second task state machine or independent
commit. Journal only identifiers and fingerprints. A current declaration is not
an execution permit: display DECLARED_ACTIVE/DECLARED_REVOKED/EXPIRED, with
conformance UNVERIFIED even when an unvalidated reference was supplied.

The next broker integration must validate actual configured capability evidence,
root/origin/account/action/data/policy scope, current lease and budget reservation
at admission and before future effects. Queued approval bindings/revocation,
already-started effect reconciliation, narrow secret injection, effective OS
probes and setup UI remain required for AOS-008-S4/S5 and TC05–TC08. Missing
conformance or broker enforcement must remain unavailable. This task adds no
live certificate, API onboarding route, runtime grant or release pass. Actual
tests use disposable PostgreSQL and synthetic declarations only.
