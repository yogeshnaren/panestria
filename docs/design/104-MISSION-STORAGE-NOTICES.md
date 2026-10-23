# Explicit owner host storage notices in Mission Control

Partial MVP-X13/AOS-018-S4 and AOS-028 integration. Reuse the existing selected
private storage settings, unprivileged bounded observer and allowlisted metadata
contract. This adds a separate local browser mode, not a new probe, data store,
background scheduler, cleanup capability or automatic project-usage attribution.

`mission-control serve --storage-config PRIVATE_SETTINGS --assets PRODUCTION_BUILD`
constructs the existing coalesced observer and permits only the read-only host
storage mode alongside ordinary project metadata. Combining it with Ask/research/
Build intake/review/run modes refuses before serving. The default browser remains
unable to read storage observations, even if a trusted caller mounted an observer.
Existing terminal/default behavior and denial code stay compatible.

A dedicated mission-storage cookie and HMAC key purpose bind the selected config
locator and exact origin. Fresh terminal pairing is required; old observer/Ask/
Build tokens cannot gain host-data access by changing URLs. `/v1/activity/storage`
requires normal current auth/origin/project checks before and after its cached
read and additionally checks explicit mode and namespace. No bearer, locator,
raw filesystem/device path or file contents are returned. The observer loads only
private operator-selected settings and emits the existing bounded metadata model.
No new owner credential or installed service is created by implementation/tests.

The UI mounts only after authenticated capabilities confirm the explicit host
mode. It validates owner/project/scope and no-cleanup/no-acceptance authority,
bounded lists and safe numeric capacity before display. It reports actual
owner-available/reserved space separately, selected estimates and overlaps,
UNKNOWN attribution, warnings/recommendations and requested Timeshift schedules.
It cannot infer exclusive Docker/backup usage or snapshot physical bytes. React
escapes labels/recommendations. There is no cleanup or backup-setting action.

Demand-driven polling respects the observer's next-check and minimum full-probe
interval; repeated views do not queue probes. A disabled/unavailable/stalled or
stale observation does not retain a current capacity/warning claim. Auth loss
unmounts host data and aborts pending reads; a late response cannot restore it.
No localStorage/sessionStorage, content telemetry or canonical task event is added.
Changing notifications_enabled is observed at the existing bounded settings poll;
opt-out stops subsequent probes and clears observations. It is not instant recall
of bytes already displayed. The private foreground service exits on owner Ctrl-C.

The [source-bound component checks](../../evidence/mission-storage-notices-2026-10-23/report.json)
use actual disposable PG/cookies/HTTP/statvfs, terminal regressions, typed production
assets and Chromium. A synthetic reserve threshold guarantees a warning; the
browser opt-out check explicitly forces the next settings tick rather than waiting
60seconds. Actual file opt-out and database session revocation still occur. This
is not physical pressure/stall/resource-budget qualification, phone TLS/device
consent, full TC05–TC08 or G1/G3/owner acceptance. No owner data/settings are changed.
