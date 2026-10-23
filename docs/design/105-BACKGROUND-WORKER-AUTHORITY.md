# Current authority throughout a background native worker

This closes the admission-to-disclosure and running-worker gap in AOS-012-S5,
starting at main `19bfd0a` (PR194). A queue claim alone previously did not carry
queue-specific withdrawal, billing, quota or account checks into the native
launch, scoped tool or result publication. Existing native policy/certificate,
lease, invocation, sandbox and independent verifier checks remain mandatory.

## One controller-owned intersection

`BackgroundPlanRunner` constructs a `WorkerAuthority` from its immutable run and
exact leased ToolScope. The callback is never accepted through an API, prompt,
CLI document or worker response. Its hash participates in the native invocation
configuration; a foreground invocation retains its existing binding format.

`BackgroundRunService.authorize_worker` verifies scope, the latest exact run,
unchanged reviewed queue/account link, no coordinator return, latest plan, the
exact still-held worker claim and current lease epoch/expiry. It then checks the
original run deadline, withdrawal, goal state, fresh Disabled billing report,
quota/reserve/observed-exhaustion rules and other foreground/held work. Only the
proven current worker is excluded from its own foreground-capacity conflict.
Sibling work still needs its prior released verified handoff. Nothing renews an
old consent, quota observation, lease or original wall budget.

The trusted guard runs before native invocation admission/claim/disclosure,
through the native and scoped-tool watchdogs, before sandbox create/start and
receipt, and before independent evidence publication and handoff/completion.
Watchdogs use a new repeatable-read read-only transaction each tick. They read
immutable binding/history plus current conditions without plan share locks or
new event writes. Ordinary start/claim still reconstruct the complete accepted
plan and protected handoffs under their existing guards; monitoring is not an
alternative admission path. Failures stop the active transport; uncertain
invocations/claims remain fenced for explicit inspection/reconciliation.

## Fresh account observations at disclosure and return

Immediately before disclosure and after transport return, reuse the existing
pinned, bounded CLI metadata probe and private account-observation CAS. Compare
the fresh (under30seconds) scoped pseudonymous principal/profile/binary with the
separately reviewed account link. Preserve the archive's existing limits and
unknown/error refusals. Recheck cancellation/deadline after the probe. No
metadata subprocess is launched on every watchdog tick. No raw account identity,
credential, billing setting or prompt enters the guard's reports.

Metadata does not establish an atomic principal lock throughout a provider
process: an external owner login change can occur between observations. During
a call, DB eligibility is monitored; principal change observed on return prevents
result publication. A completed external disclosure/tool effect cannot be
undone. This is no stronger secret-injection/egress envelope, general connection
grant integration, provider billing attestation or native runtime qualification.

## Failure and scope limits

The hook covers native editing workers. Trusted final integration retains its
existing separate claim/current-policy/verifier path; it needs its own queue
lifecycle intersection before claiming full background end-to-end revocation.
No auto-merge, automatic retry, provider fallback, schema migration, background
enablement or owner service/config change is introduced. Current billing remains
stale/off until actually renewed by the owner. Full TC06/07/10, connection/runtime
qualification, foreground/resource evidence and G3/owner trial remain open.

See [owner checks](../testing/BACKGROUND_WORKER_AUTHORITY.md) and the
[source-bound evidence](../../evidence/background-worker-authority-2026-10-23/report.json).
