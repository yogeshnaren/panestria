# Opt-in owner storage observations in the activity terminal

Revision-3 MVP-X13, partial AOS-018-S4/AOS-029-S2. This connects existing
read-only storage probes to the owner activity terminal. No task state, grant,
cleanup action, browser host-data scope or acceptance verdict is introduced.

`activity serve --storage-config ABSOLUTE_PRIVATE_JSON` installs one observer
for the configured owner/project. The flag alone permits settings inspection;
full probes require `notifications_enabled: true`. Without the flag, activity
bytes retain their old shape and no observer/probe is created. Disabled settings
produce DISABLED, not an old healthy sample. No OS scheduler is installed.

The authenticated GET `/v1/activity/storage` reads cached memory and starts at
most one coalesced daemon collector. Private file access and synchronous probes
run off the HTTP/event loop. Demand checks settings at most once per sixty
seconds; full probes honor the configured interval (minimum sixty seconds).
Repeated requests cannot bypass that interval. With no client requests, there
are no new collections. This is advisory monitoring, not admission/reservation.

The collector rereads settings after probing. Changed/off/unreadable settings
discard the result. Shutdown prevents new collections and late publication.
Existing component subprocess timeouts remain three seconds per selected
directory and five seconds for Docker. An OS filesystem read can still stall:
at thirty-five seconds clients see STALLED and no second collector starts while
the first remains in flight. Late samples are discarded. A daemon thread is
**not** a hard interruptible I/O boundary; closing does not stop an already
running read or prove its physical return. One read may finish after opt-out.

Typed, no-store responses expose owner-wide capacity, selected component labels,
source/time, observed/estimated/unknown distinctions, Timeshift schedule booleans
and review recommendations. They exclude filesystem/config paths, device IDs,
file contents and raw exceptions. Docker logical/shared figures can overlap;
physical Timeshift bytes and project ownership remain unknown. Unknown is never
zero. The terminal shows the highest-severity warning, last-sample age, explicit
uncertainty and a scrollable `o` detail view. It offers no mutation controls.

This task is terminal-only. Combining dashboard assets with the storage flag
is refused, and a browser-wired app refuses the storage endpoint. Browser/phone
host metadata needs a separately reviewed scope and consent integration. Other
resource measures, persistent growth history, desktop/mobile inbox, write-path
coverage, approved host budgets and whole-case/gate qualification remain open.

See the [owner guide](../testing/OWNER_STORAGE_TERMINAL.md) and
[source-bound report](../../evidence/storage-status-terminal-2026-10-22/report.json).
