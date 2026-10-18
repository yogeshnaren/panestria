# Durable PUBLIC search admission

Revision-3 AOS-019-S1 continuation, based on main `3bca982`. Preserve existing
research request hashes and limits: a new `SearchPlan` owns the query budget
instead of adding a serialized default to historical `ResearchLimits` records.
This design enables trusted controller integration; it does not admit a public
endpoint, issue a runtime certificate or complete AOS-019/G2.

One immutable plan is keyed by canonical task ID, with one research request,
request/contract/policy/configuration hashes and 1–16 maximum queries. The trusted
owner-facing workflow must review that budget before invoking this controller.
A model cannot reset it by creating another request, lease, adapter or plan.
Goals and tasks remain in the canonical Postgres tables. The new tables record
only the plan, consumed dispatches and append-only historical outcomes.

Before preparing or claiming, the kernel checks actor/project/goal/task scope,
current lease/epoch/state, an ACTIVE goal, the stored validated contract and
immutable request. Both question and goal must be PUBLIC, cloud egress allowed,
`public-search` explicitly declared and API cash budget zero. All current policy
axes must permit `external-send` to the separate `public-web` destination; the
contract's policy reference and trust profile must match. A changed policy or
configuration requires a new task and review, not a reset of this plan's budget.
Wall time starts at the task's **first** attempt and is limited by both contract
and research-request deadlines; reclaiming a lease cannot reset it.

Lock order is project, task/attempt, search records, global event append last.
The task lock serializes the query count. Claim and its disclosure event commit
in the same caller transaction before the broker can create a socket. The
controller acknowledges that commit and rechecks authority before returning
from `before_send`. No database transaction spans HTTP I/O. Claim records include
attempt/epoch, ordinal, query/configuration/form-body hashes, query byte count,
scope, provider, PUBLIC label and possible upstream disclosure. They contain no
plaintext query, source URL, title, snippet, cookies or credentials.

The uniqueness fence is `(task_id, query_sha256)`. A dispatched query stays
consumed after timeout, setup error, cancellation, lost acknowledgement or crash.
No automatic retry, refund, fallback or exactly-once HTTP claim follows. A
committed dispatch without an outcome means **UNKNOWN**; inspect it, do not send
again. A rolled-back claim consumes nothing and cannot authorize I/O. Successful
local responses record only hash/candidate count. Neither a local response nor
an authorized socket measures upstream engine usage, quota, spending or truth.
`authorized=YES`, `accessible=YES`, `observed=UNKNOWN` deliberately stay distinct.

The controller watches current authority during I/O and fences late results.
Socket reads already poll cancellation under an absolute deadline. Revocation
cannot retract bytes already sent; the ledger records possible disclosure even
when the broker is stopped before connecting. Historical outcomes may be written
after cancellation without restoring task authority. Search candidates remain
untrusted and unfetched; this path never records a source, citation, semantic
support verdict or completed goal.

`PublicSearchCertificateStore` adds purpose `PUBLIC_SEARCH_RUNTIME_ONLY` and
actual AOS-019-TC04 OS evidence to the existing AOS-008/AOS-010 runtime checks.
Runtime identity binds `public-search-v1`, current package bytes and exact local
client settings. Native Build-only certificates cannot authorize search. There
is **no live public-search issuer or installed provider qualification yet**.
Future operator qualification must also inspect/pin the actual service, upstream
engine choices, no-extra-spend configuration and OS boundary; a loopback URL or
synthetic HTTP test cannot prove them. Do not copy fixture certificates into an
operator certificate store or widen an existing Ask/Build project implicitly.

Migration 0030 adds three immutable tables and preserves old rows. It refuses
downgrade once any plan exists; use forward repair or a reviewed backup. Foreign
keys, closed disclosure projections, bounds and immutable triggers protect
retained audit. Workers get no database credentials. Kernel checks remain the
authority for policy, deadlines and task-wide count; raw SQL is not an alternate
dispatch API. Actual dump/restore must preserve the query fence and global event
counter before acceptance.
