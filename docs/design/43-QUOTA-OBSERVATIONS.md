# Scoped quota observations and owner input

This AOS-012-S4 task starts from main d20361e after PR92. It adds a useful local
owner-input/read path and a durable observation ledger. It does not dispatch
background work, infer a cash price, prove a billing route or change provider
permissions. AOS-012-S5–S7 and the full R3 gates remain required.

## Data and interpretation

Keep provider, opaque account UUID, optional exact model, and window reference
separate. A session window and a weekly window are independent constraints.
Store a strict decimal string plus unit (percent/tokens/requests), or null for
unknown. A percentage cannot become a token/request count. Normalize only the
numeric spelling. Sources remain PROVIDER_REPORTED, OWNER_REPORTED, ESTIMATED
and UNKNOWN. Provider/estimate source hashes are provenance references, never
self-authenticating evidence or permission. No collector is enabled here; the
HTTP boundary permits only owner reports/unknown, not provider impersonation.

Every observation has an immutable ID, UTC observed time, optional reset time,
bounded freshness duration (at most24 hours) and ingestion time. Storage is capped
at10,000 immutable observations per project; reaching it denies new input until a
reviewed retention/archive design exists, while exact replays remain available. Reject timestamps in the future
using the PostgreSQL clock; naive times are invalid. Reset must follow observed
time, but an already expired historical report is allowed. Replays compare the
canonical body and task; they never refresh timestamps. Freshness is recomputed
using the server clock. Expired/reset observations expose null effective balance
while preserving the historical reported value. Unknown never becomes zero or
unlimited. A newer UNKNOWN report in a source lane supersedes that lane's older
known report. Keep each source lane visible rather than inventing precedence or
averaging conflicting reports. Late arrival is ordered by observation time,
then ingestion time/ID, not by client insertion order alone.

## Database and trust boundary

Migration0029 is additive over actual head0028. Immutable scoped rows reference
existing project/goal/task FKs. Duplicate IDs cannot cross scope. Canonical JSON
and projected columns must agree; every read validates the body hash. Use the
caller transaction, project/task locks, row insert before global event lock and
one same-PG event. Rollback removes both; duplicate concurrent submissions yield
one row/event. Autocommit without an explicit transaction is denied. A populated
downgrade refuses to erase audit history; dump/restore retains interpretation
and the global event cursor. No account credential, freeform note, prompt or raw
provider response is accepted. Opaque account refs are not an account enrollment.

The existing loopback bearer/browser session/Host/Origin/CSRF boundary protects
input and reads, including reauthorization inside the transaction. Responses
are no-store, errors omit submitted content, body size is capped and owner/project
identity comes only from the authenticated configuration. Reads reveal only the
configured owner's project. Health-only apps leave these routes unmounted.
No network/provider/model/SDK call, new dependency or owner database is needed.

## Failure and qualification plan

Test closed/schema/type/time/decimal/unknown cases, actual scoped PostgreSQL
atomicity/idempotency/races/immutable/FK constraints, stale/reset/source-lane and
out-of-order behavior, API authentication/revocation/CSRF/authority spoof/body
limits, actual empty migration/reapply and populated restore/refusal. Refresh
schema snapshots from a unique disposable real PostgreSQL instance. Preserve
failed observations and bind final evidence to the clean tested source. Do not
mark all of TC05, S4 or any release gate passed from contract fixtures alone.

## Observed qualification

Clean cdf3e35 passes172 focused checks in214.59s, including67 new cases; one
existing live test is excluded. Actual head29 schema1126lines was refreshed on
unique owned cached PostgreSQL port32773. Static checks and11 import contracts
pass. The source-bound evidence preserves the original HTTP status and test
expectation failures. See [the report](../../evidence/quota-observations-2026-10-16/REPORT.md)
and [API review instructions](../testing/QUOTA_OBSERVATIONS.md). Supported live
quota telemetry, full S4/TC05 and the queue/capture/release obligations remain open.
