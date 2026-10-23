# Public HTTPS fetch grants

Partial revision-3 MVP-X09 / AOS-008-S4–S5 delivery. The first supported broker
capability is anonymous PUBLIC HTTPS GET through the existing admitted fetch and
isolated reader. It does not enroll authenticated accounts, expose local folders,
import provider/browser sessions or introduce a secret injection path. Existing
connection declarations and review screens remain DECLARATION_ONLY / UNVERIFIED;
a declaration does not certify the runtime.

The exact `FetchConnectionBinding` (grant UUID and revision) joins the existing
owner/project/request/contract/policy/configuration/attempt/epoch binding. An old
serialized plan remains readable without a connection field, but cannot execute.
No migration backfills grants or changes old plan hashes/evidence. The current
fetch runtime descriptor changes, so previous runtime certificates do not qualify
the new configuration by inference. Existing certificate-purpose/runtime checks
must pass independently before a declaration can intersect execution authority.

`GrantBroker.authorize` runs inside the certified admission transaction and
requires the current active declaration, policy, version, connector/version,
configuration and conformance pointer. The account reference is a deterministic
owner/project/configuration-scoped **anonymous service identity**, not proof of an
external authenticated account. Both read and send must be present and PUBLIC
allowed; cash must be zero and roots absent. The backend performs only anonymous
GET, so other declared actions never become executable. Expiry and wall capacity
remain separate; wall time starts at the first retained plan using this revision.
Replacing a declaration requires fresh exact owner review; old pinned plans cannot
adopt it. Revoking/replacing/policy changes fence subsequent admissions, hops and
publication. Historical receipts remain immutable and uncertain transfers do not
become successful or free. A request already sent cannot be recalled.

Every first URL and redirect must match a declared exact HTTPS origin on443,
with the same canonical host the transport uses. Check before DNS/connect/send;
retain existing private-address, peer, TLS, redirect, reader and source checks.
An unknown redirect fails closed; no automatic origin expansion or consent retry.
A metadata-only collection preflight refuses absent/exhausted grants before
starting a new search/lease. The actual fetch checks the same pinned grant again.

Calls and bytes are cumulative across all goals/tasks sharing a grant revision.
The project lock serializes reservation with existing review/revoke. Dispatch,
connection reservation and ordered event commit in one PostgreSQL transaction;
the acknowledgment must return before any I/O. All possible redirect hops are
reserved up front and clamp the transport redirect limit. Unused, failed,
revoked and commit-ack-lost reservations are never refunded. Missing/inconsistent
reservations are UNKNOWN and refuse more work. Limits are not reset by a new goal.

Each hop reserves49153 application bytes: bounded HTTP request8192, framing32768,
and conservative buffer/read-ahead8193. Terminal body capacity plus one-byte
limit detection is separate. These conservative plaintext application limits are
**not actual usage or DNS/TLS/TCP/physical-wire accounting**. Runtime descriptor
and transport share bounds. PostgreSQL checks bind reservation task/request and
revision to the immutable dispatch/plan and defer body/hop consistency until
commit. Audit rows cannot be updated/deleted. Downgrade refuses retained bound
plans/reservations rather than discarding history.

`connections prepare-public-fetch` reads private scope/runtime settings and writes
one new0600 unverified proposal template. It fixes this supported capability and
anonymous identity, while the owner explicitly chooses exact origins and limits.
It neither submits nor decides it, overwrites a config, qualifies a certificate
nor changes the running runtime. Existing proposal/scroll review/separate confirm
and revoke commands remain the only declaration lifecycle.

Connected checks use actual disposable PostgreSQL, loopback HTTP, CLI/private CAS
and the existing isolated reader, with explicitly synthetic HTTPS/certificates.
They are not public TLS/search/runtime qualification or complete TC05–TC08/G2/G3.
General authenticated account/root/native adapter/secret-envelope and lifecycle
qualification remain open. See the [setup guide](../testing/PUBLIC_FETCH_CONNECTION.md)
and [source-bound observations](../../evidence/fetch-connection-grants-2026-10-23/report.json).
