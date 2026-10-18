# Explicit owner collection from a staged question

This connects `research stage` to actual admitted search, fetch, isolated reading,
retained excerpts and private inspection. It is a collection mode, **not a
synthesized or fact-checked answer**. Synthesis, qualified semantic support and
the complete Delegate/G2 gate remain pending. No source, skill or original gate
is rewritten by this task.

## Inputs and authority

`ResearchSettings` selects one owner/project, private CAS root, separate protected
certificate store/hash and exact LocalSearchSettings. Private files and canonical
owner-only directories are checked before execution. The configuration grants
nothing: the current project must separately have the reviewed joint
PUBLIC_RESEARCH_RUNTIME_ONLY certificate, PUBLIC web permission, compatible trust
and autonomy, and a matching pinned contract. A native Build certificate or a
standalone component certificate cannot enable this path.

The owner explicitly supplies 1–16 PUBLIC queries, each satisfying SearchQuery's
512-byte/no-engine-selector/control-character rules. Duplicate queries are denied
before activation. The entire staged question (up to65,536 bytes) is **not** sent
automatically. The explicit `--public-web` flag cannot override a private class,
cloud denial, mismatched policy/runtime, missing capabilities or nonzero API cash.
Execution admits only read/public-search/public-fetch capabilities; no actor,
shell, provider fallback or model call exists in this mode.

## Canonical state and interruption

CollectionLifecycle validates stored request/contract hashes, artifact metadata,
scope, limits and the current reviewed policy. The controller also rechecks the
acknowledged private question bytes. It requires a fresh CREATED goal/task with
no prior attempt. The phases are CREATED→VALIDATING (goal ACTIVE), then READY,
then a first bounded `public-research-collection` lease, then immutable component
plans. **Each phase commits its own state and event in the same PostgreSQL
transaction**, acknowledged before network work. The global event counter remains
the last write/lock; no filesystem/database atomicity or exactly-once HTTP claim
is introduced. A crash between phases is visible and refuses automatic restart.

Collection operations acquire project→goal(NO KEY UPDATE)→task→attempt/audit→event.
The goal lock precedes the task because activation changes goal status and owner
cancellation already acquires goal→task. Normal admitted search/fetch/quote units
retain their existing project→task order and do not update the goal; their event
FK key-share locks are compatible with cancellation's goal lock.

The existing brokers commit query/hop disclosures before I/O and consume source/
body reservations even after failed or uncertain transfers. There is no refund,
provider fallback, repeated query/URL or automatic retry. One unavailable search
stops subsequent queries. Remaining queries stop as soon as source/body capacity
is exhausted. Duplicate URLs are skipped. All policy/lease/deadline/cancellation
fences remain in the admitted controllers.

A known bounded stop closes only the collection adapter (attempt SUCCEEDED),
fences its epoch and leaves the **task VERIFYING, goal ACTIVE** awaiting synthesis
and support. No acceptance/check_run or goal PASS is created. A committed query
reservation with a lost acknowledgement can be surfaced by the transport as
unavailable; therefore known termination independently refuses missing/UNKNOWN
canonical receipts. It goes to RECONCILING/LOST, with no automatic redispatch.

Errors/interruptions fence the same unreplaced epoch into RECONCILING/LOST when
possible. An expired unreplaced lease may only be retrospectively marked lost,
never known-successful. Cancellation, a replacement epoch or a finished attempt
cannot be overwritten. A failure before the attempt ID is acknowledged can leave
VALIDATING/READY/RUNNING plus its original lease/history; inspect and reconcile
or cancel rather than restarting the command blindly. This is not yet a durable
automatic restart/supervisor workflow.

## Output and honest limits

For each retained source, the trusted controller records at most8,192 UTF-8 bytes
at an exact code-point boundary and passage offsets. ClaimStore checks the quote
against retained normalized bytes. The draft label says “retained source excerpt;
not an assessed answer”, with kind INTERPRETATION and NOT_ASSESSED support. Search
snippets and embedded instructions never become an answer or actor instruction.

The private inspector adds request-scoped search/fetch observations from existing
immutable ledgers, including missing receipts as UNKNOWN, bounded failure reasons,
reserved capacity, attempt status, expiry and canonical stop reason. Reservations
are **not measured traffic, spend or quota**. These observations do not confer
live-runtime, semantic or completion authority. HTML remains inert/escaped with
no external resource loads or active source links; JSON unwraps secrets only in
the private owner export. Historical artifacts/hashes remain unchanged.

The connected test uses actual disposable Postgres, loopback HTTP, CAS, fixed
Docker reader and owner CLI. HTTPS bytes/certificates are explicitly synthetic
TEST_FIXTURE_NOT_LIVE data. Actual SearXNG setup/upstreams and public-web runtime
qualification remain owner-deferred. No live certificate is issued, no model or
provider call is made, and G1/G2/G3 are not promoted. Operator web policy-review
commands and stable live qualification remain separate work.
