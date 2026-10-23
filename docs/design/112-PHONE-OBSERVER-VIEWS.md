# Private phone observer views

This AOS-028-S5 component reuses Mission Control's canonical metadata projections,
pending plan/action inbox, task timeline and PUBLIC Build evidence reader. The
private ingress supplies a fixed root descriptor and an authenticated capability;
the client requires agreement. Neither is an authorization grant: the closed
phone boundary and canonical device role still enforce every request.

An optional `build_evidence_store` selects an existing owner-private directory.
The phone opens it read-only and rechecks protected bytes/current scoped PUBLIC
policy. It creates no store and exposes no raw artifact/diff/profile route.
Selecting a store changes the phone profile digest and requires a new pairing;
omitting it preserves the preceding profile identity. An unconfigured reader
stays explicitly unconfirmed rather than inventing checks or a release pass.

Freshness uses browser monotonic elapsed time; server observation timestamps
remain human-readable last-seen labels. Old activity/timeline metadata is labeled
unconfirmed after failed reads; failed or aged evidence/inbox rows are hidden.
Phone background/page-return and device offline/online events clear the view and
require canonical revalidation. Network/visibility hints cannot advance status.
Revocation clears authenticated views and last-seen labels on the next denied
read. There is no background push, service worker, persistent browser data store,
offline task execution or remote decision UI. Existing desktop/storage clocks and
mutation modes retain their separate behavior.

Validation must connect production assets, actual CLI/TLS/PG/cookies, protected
Build publication and a 390px touch viewport. Terminate/restart the disposable
listener, interrupt the emulated device, and revoke its canonical session. Native
provider/auth/capacity and visibility are explicit fixtures. Browser emulation
with a temporary self-signed certificate is not actual phone/private-network
qualification; TC08 and complete S4-S6/G3 remain open. No owner ingress, database,
certificate trust, services or network configuration is changed by these checks.
