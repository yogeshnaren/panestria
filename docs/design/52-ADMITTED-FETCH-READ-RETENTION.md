# Admitted public fetch, isolated read and retention

This task connects existing HTTPS transport, isolated readers and source storage
through canonical current authority and durable source/body reservations. Its
output is a retained source ID for later claim/brief inspection. It is not an
enabled public-web runtime, semantic verifier or full Delegate submission route.

Search and fetch use one `require_public_research` implementation: explicit
caller transaction; project then task/attempt locking; current lease/epoch,
ACTIVE goal, validated stored contract, PUBLIC question/goal, zero SDK cash,
explicit cloud allowance and capability, current reviewed policy/hash/trust and
all three policy axes. The first task attempt starts the wall clock; replacement
leases cannot reset it. Search retains its serialized fields and denial codes;
fetch requires `public-fetch` and a separately purpose-bound certificate store.

`FetchPlan` binds task/request/contract/policy/configuration hashes. Limits come
from the immutable hashed research request. Migration0031 stores immutable plan,
dispatch, hop and outcome records in the canonical database. Source receipts bind
the same task/request, captured snapshot and metadata hash with composite FKs.
No new task-state store, event ordering counter or implicit provider is created.

Before transport, `AdmittedFetch.collect` acknowledges a durable per-task source
ordinal and body-byte reservation. The broker reads at most cap+1 bytes to detect
truncation, so that extra byte is reserved too. The cap is reduced when necessary
to fit the remaining total. Fewer than two remaining bytes refuses another
source. Count and reservation checks serialize under the task lock. Failed,
cancelled, uncertain and smaller-than-cap responses never refund reservations;
repeated URL hashes, replacement attempts and request IDs cannot reset them.
These conservative capacity counts are not actual traffic/quota/spend readings.

For every hop, including redirects, the fixed controller callback rechecks
current authority, inserts hash/byte-count disclosure and commits before DNS or
socket creation. The trusted transport still checks URL syntax, all DNS answers,
numeric pinned peers, TLS/SNI, redirects, encoding, framing, byte/deadline limits
and cancellation. It carries no cookies, auth headers, inherited proxy or retry.
The existing 32KiB framing bound is per hop, separate from body reservations;
this does not measure or cap all TLS/DNS protocol traffic as body bytes.

The controller supplies its own callback and shared bounded fetch/DNS pools;
workers cannot inject an authorization callback or transport factory. An authority
watcher fences ongoing I/O/reader work. Deadline is from the canonical first
attempt, never rounded up to a fresh second. The actual readonly/no-network
HTML/plain/PDF reader receives only fetched bytes. Complete fetch+reader results
go through existing `SourceStore.commit_fetch`; incomplete extraction never
becomes a usable source. It creates no fact/support judgment or goal completion.

Source commit and the historical fetch outcome use separate acknowledged
transactions. A crash between them can leave valid retained evidence and UNKNOWN
dispatch outcome. Reservation and URL remain consumed; inspect history rather
than silently refetching. Missing outcomes mean UNKNOWN. Cancellation may leave
valid historical bytes/receipts, but current authority is checked again after
receipt handling before any result is returned. Already-sent bytes cannot be
retracted, and the ledger conservatively records possible outbound disclosure.

`PublicFetchCertificateStore` refuses generic/search/Build stores and purposes.
It requires source/configuration-bound PUBLIC_FETCH_READER_RUNTIME_ONLY evidence
for existing008/010 OS cases plus019-TC02/TC03 and020-TC01. Runtime binding includes
Python/OpenSSL/kernel, pinned reader image and UID/GID. No live issuer or
certificate is created here. Real OS/broker qualification, including the actual
operator Docker/runtime setup, remains mandatory before live use. Test stores
are explicitly TEST_FIXTURE_NOT_LIVE and must never be copied into operator use.

Rollback is forward repair or reviewed backup when audit rows exist; populated
downgrade is refused. Source records and original reports stay immutable. Current
schema fingerprint, documented snapshot and API schema head advance together.
Original archives/specs and historical evidence are unchanged. New-request
owner submission, configured search, semantic qualification and G2 remain pending;
SDK TC04 stays deferred, not passed. No release or owner acceptance is inferred.

Closed diagnostics distinguish body-size/truncation, fetch deadline, HTTP error,
reader truncation/unsupported output and unavailable operations. Raw exception
text/URLs are not added to events. The DB restore test preserves the same CAS
root; it is a Postgres restore check, not a complete machine/CAS backup claim.
