# Canonical pending-review discovery

Add a content-free read-only snapshot of latest unaccepted plans and pending
canonical action approvals for open CREATED/ACTIVE goals. Query the retained
build_plan/build_plan_acceptance and approval_request tables; do not create an
inbox queue, copy task state or append observation events. Original policies,
contract-consent workflows and exact decision services remain unchanged.

`GET /v1/activity/reviews` uses an authenticated owner/project and a REPEATABLE READ,
READ ONLY transaction. Return closed metadata only: kind/id/goal/task IDs,
canonical PROPOSED/PENDING and goal state, expiry and whether expiry was reached
at the recorded observation time. No prompt, intent, preview body, destination,
path, digest, diff, inventory, secret or profile. Expired records remain visible;
expiry-not-reached is not a qualified or currently permissible decision.

Bound pages to1–32, default16, sorted by expiry/id/kind. Cursor kind/UUID resolves
only a retained owner/project row, including after a decision; foreign anchors
are hidden. New pending items before the anchor require a first-page refresh.
Show only the latest plan version, exclude accepted plans/resolved requests and
closed goals. Immutable historical records are never deleted or relabeled.

The React inbox polls every10seconds, hides entries on error/auth loss or after
15seconds without a confirmed snapshot, and paginates explicitly. Plan selection
only fills the explicit intake/review inspection form: it never POSTs or grants
consent. A pending/uncertain operation keeps its original ID and rejects inbox
navigation until inspected. Exact protected reading and separate decision remain
manual. Action approvals open their canonical goal; protected Build review stays
behind its existing explicit mode. No generic preview/decision/dispatch route is
added. Other approval families and full dispatch integration remain R3 work.

Connected checks use actual disposable PG/Git/HTTP/CLI/browser with an explicitly
seeded VERIFYING fixture task and declared worker inventory. A real canonical
contract-consent request and plan acceptance exercise discovery and removal.
These fixtures make no worker, verification, provider or release qualification.
