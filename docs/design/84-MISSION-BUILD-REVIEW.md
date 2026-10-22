# Explicit local PUBLIC Build review and consent

AOS-028-S2 needs an owner to inspect the exact diff, independent report bytes and
frozen action preview before deciding. The metadata observer intentionally cannot
expose these contents or record decisions. This slice adds an explicit
`--build-review-root` mode; default observer and standalone activity retain their
existing authority. It does not install a dispatcher or launch any provider.

## Authority and transaction

A dedicated private ActivitySettings file selects the existing owner/project and
unused loopback port. The extra trusted CLI option selects an existing private
Build root. Only its reports and derived protected owner/project destination.git
are accessed. Native credentials, certificates and private Build settings are not
loaded. It is mutually exclusive with --build-evidence-store.

Review mode has a different session HMAC purpose and cookie namespace. Switching
modes requires fresh pairing; an observer/default-app session grants no review
access. Existing exact Host/Origin, cookie authentication, memory-only CSRF,
body/header/time/rate limits and no-store headers apply. The browser cannot choose
a filesystem root. No secret or view state is saved in localStorage.

Before protected I/O, canonical owner/project, current policy and a readable
PUBLIC goal contract are required. The selected final merge request must match
that contract, current accepted plan/final node where present, exact task/epoch,
independent complete PASS checks, protected reports, base/candidate/tree and
canonical effect_digest. The destination ref is observed for expected-base
agreement; final Git CAS remains the existing protected executor's authority.

GET runs in a consistent transaction and rolls it back. It exposes a bounded
untruncated diff (64KiB), bound report bytes (64KiB total), complete canonical
preview and version/state. Oversized, missing, corrupted, non-UTF8 or changed
content fails closed, without partial success. The total JSON response is capped
below the client limit. Reports are independent verifier records/reasons/output
hashes, not a promise of complete raw command stdout.

An additional review_sha256 binds the immutable displayed content, preview,
report identities and protected diff. Current version is a separate canonical
approval fence; observation time/state are not included in that immutable hash.
This permits idempotent receipt replay without inventing a new preview.

POST re-authenticates inside its transaction, takes the project/task/request
locks, regenerates the review from protected bytes, checks review hash/request/
effect digest, then uses the existing ApprovalService.decide with exact version
and idempotency key. Expired, no-longer-pending/current, stale version, modified
preview or evidence cannot create consent. Current auth is rechecked after
protected I/O before the decision commit. Errors roll back and expose fixed
codes only. No generic mutation router is mounted on the observer.

## User outcome and failure behavior

The typed React panel shows canonical preview, protected diff and actual report
text using React text nodes/pre elements only. It renders no artifact HTML,
markdown or source links. It periodically rechecks while open, clears failed
content, resets entered confirmation when the request/hash/version/state changes,
and disables decisions when observations exceed15seconds. The owner must type
the exact digest and acknowledge reviewing the contents. Both approve and deny
use the canonical decision service.

A confirmed receipt means APPROVED or DENIED consent was recorded. It does not
mean merged, task completed, release accepted or G3 passed. There is no worker,
effect preparation, dispatch or goal kick in this service. Existing owner Build
CLI performs the separately verified effect, using the same request. Lost HTTP
acknowledgment is UNCONFIRMED; the panel clears the preview and submits no retry.
Inspect canonical state before deciding what to do next.

## Validation and rollback

Connected checks cover default/no-grant and cross-purpose sessions, scoped
PUBLIC content, foreign/private denial, stale digest/version/review hash,
cross-origin/missing-CSRF denial, changed protected report rejection, canonical
idempotent denial without dispatch, and actual Chromium/HTTP/PG/Git review with
offline decision failure, exact approval recording and subsequent existing-CLI
protected merge. Native/auth/OS/capacity identities are explicitly nonlive
fixtures. No inference/provider calls, phone qualification or release pass.

Disable this mode by restarting without --build-review-root; retain all canonical
consent/receipt/evidence history. Original observer sessions/purpose remain
separate. No migration, new ledger, automatic compensation or deletion is used.
Full workflow intake, full approval inbox/effect dispatch UI, phone and original
cumulative gates remain pending. The owner's port8770 historical review setup
continues on its already tested checkout and is not changed by this task.
