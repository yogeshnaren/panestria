# Private read-only phone ingress

Status: PROPOSED implementation design for AOS-028-S4 / MVP-X12. No ingress,
device enrollment, certificate, database migration or phone qualification has
been enabled by this document. Original TC05–TC08/G3 requirements stay intact.

## Outcome and boundary

An explicitly started private TLS listener serves the existing content-free
Mission Control observer to an explicitly paired device. It cannot submit work,
approve a plan/merge, run/cancel workers, change grants, read raw artifacts or
export a restricted profile. Existing desktop modes remain loopback-only. The
phone is an observer of the workstation, not another executor.

Reuse existing ProjectActivity/ReviewInbox/ActivityTimeline/BuildObservation,
SessionService, BrowserSecurity, read-only DB snapshots, production assets and
bounded uvicorn settings. Do not widen every BrowserAccess origin or route.
Use a distinct phone access profile and server-side closed route/method allowlist;
future desktop routes must not become reachable automatically.

## Deliberate configuration and transport

Add a separate disabled-by-default private owner configuration and `phone` CLI
group. Require an existing private owner token, existing certificate/key, exact
owner/project, one literal private IPv4 bind address, explicit port and a bounded
set of exact allowed client IPv4 addresses. Initially support RFC1918/CGNAT and
loopback test/preview addresses only; no wildcard/public IP, DNS discovery,
network installation, port forwarding, public ingress or automatic certificates.
Read private owner files without symlink traversal; hold file descriptors while
loading TLS and reserve the socket exclusively. Use TLS1.2 or newer, fixed
request/concurrency limits, no access/body logs, no proxy-header trust and no HTTP
fallback. The actual phone must trust the selected certificate; tests must verify
their fixture CA, never disable certificate validation.

The app checks actual connection TLS/client identity and exact Host/Origin;
forwarding headers cannot substitute for either. A private IP allowlist supplements
application authentication and does not replace it. Configuration cannot prove a
firewall/private-network deployment: actual owner-selected network/phone validation
remains separate live evidence. Starting the service never configures that network.

## Canonical pairing and devices

Keep existing hash-only PostgreSQL pairing challenges/browser sessions. Add a
phone scope to challenges and a canonical immutable phone-device role binding to
the existing session ID, owner/project and configuration digest. This is a scoped
authentication role, not a shadow task/attempt/approval store. Preserve old rows
and the default desktop behavior. Issue/invalidate challenges only within their
scope so phone pairing cannot consume a desktop challenge.

Derive a distinct session HMAC purpose from the existing private token and exact
phone configuration/certificate identity. A configuration change or token rotation
requires new pairing; old session records remain historical. Phone pairing uses
128 bits of one-use code entropy, the existing short bounded TTL plus a global
attempt limit, and no code/token URLs or persistent browser token storage. Limit
phone sessions to one hour. Cookies are HttpOnly/Secure/SameSite=Strict and use a
separate namespace; desktop/phone cookies and codes cannot be interchanged.

Authenticate both the unexpired/unrevoked canonical session and its immutable
current read-only role before data access, and again before publishing a snapshot.
The local owner CLI can list phone device IDs/status and revoke a selected scoped
device with explicit confirmation. Device logout revokes itself with same-origin
CSRF. Revocation changes canonical session state, not merely a UI flag; historical
role/pairing facts remain. Unknown/revoked/foreign devices deny access. No raw token,
code, certificate key or private question becomes an event payload or response.

## Allowed surface

Serve only static production observer assets, session pairing/self-logout, observer
capabilities and existing content-free project/review/event/optional PUBLIC Build
progress reads. Pair-code issuance and device administration are local CLI actions,
not remote bearer endpoints. Reject other routes/methods on the server even with a
valid device cookie and CSRF. Keep session-control writes separate from task/data
mutation. No model/provider/native auth/secret store is initialized by this mode.

All responses use no-store and existing browser security headers. No service
worker or restricted-data cache. Reuse the pairing form with its distinct code
length; display observer authority honestly. Full responsive attention/reconnect/
stale/offline behavior is S5, and actual target-phone evidence is S6.

## Required checks and rollout

Use disposable PG and ephemeral TLS sockets with synthetic actors/data and a
temporary fixture CA. Cover TLS verification and plaintext refusal; pairing/code
replay/expiry/namespace isolation; authenticated metadata; exact Host/Origin/peer
checks; wrong-project/device/revoked/expired denial; local device revocation;
server-side mutation/raw-artifact/profile denial despite valid auth; unchanged
desktop sessions; and no canonical task writes or model initialization. Exercise
the production CLI/server path, not only ASGI fixtures. Distinguish injected peer/
clock fixtures from actual socket/TLS observations. Update the observed schema
fingerprints from an actual migration round trip; audit-bearing downgrade must
not erase devices silently.

Start disabled, retain original failed observations, and run existing affected
session/observer/OpenAPI checks plus exact-head CI. Never label synthetic TLS as
real private-phone/network qualification. Enable no owner service or enrollment
until its explicit selected configuration and actual acceptance step.
