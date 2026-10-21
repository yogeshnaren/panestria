# Background account identity, revision 1

An opaque quota account UUID is a local scope, not authenticated identity. Keep
that distinction when connecting a queued PUBLIC plan to a private native login.

`NativeAccountObservation` is a new closed frozen contract, not an extension or
reinterpretation of historical compatibility manifests. The trusted collector
reuses the pinned, held-FD metadata transport and derives only scoped identity
and profile hashes. A personal first-party Pro/Max auth-status observation is
separate from inference, quota, billing and OS qualification. Unavailable fields
fail closed; no credential parsing/private endpoint substitutes for them.

`BackgroundAccountLink` binds the observation's protected canonical bytes to the
exact owner/project/item/background binding, opaque account UUID and binary pin.
The original immutable queue policy/context are unchanged. Reports are private
CAS, acknowledged before an exact owner review appends one existing ledger event.
Fleet then project locking serializes review/withdrawal. Replay preserves the
original observation time; changed identity/profile/binary cannot overwrite it.
Bounded refresh is permitted only for the same principal and unstarted plan.

No new task-state table, lease, process, spend reservation, billing report or
training right is created. Historical metadata alone cannot authorize a launch.
A dispatcher must independently revalidate the same authenticated principal,
current policy/consent, live isolation qualification, billing boundary, quota,
foreground capacity, cancellation and original plan limits. Metadata-only actual
observations are labeled separately from fixture component checks and inference.

See the [owner commands](../testing/BACKGROUND_ACCOUNT_LINK.md) and retained
[component evidence](../../evidence/background-account-2026-10-21/report.json).
