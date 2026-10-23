# Opt-in storage notices in Mission Control

This dedicated read-only desktop mode shows selected host storage observations
and owner recommendations. It cannot clear storage, change Timeshift, remove
Docker volumes or assign all host use to Panestria. Phone access and resource
qualification remain separate R3 work.

Use the [existing storage settings guide](STORAGE_AWARENESS.md) to choose a private
mode0600 file. Set `notifications_enabled: true` only when you want observations.
Select Docker/Timeshift/components explicitly; default capacity needs no directory
scan or daemon access. UNKNOWN stays unknown, and selected estimates may overlap.

Build the local production UI using an already installed supported Node/runtime
and the pinned dependencies as in the [observer guide](MISSION_CONTROL_OBSERVER.md).
The recorded bundle is approximately279KB JavaScript before compression; cached
Node dependencies/browser binaries use additional storage. Review free space
before installing dependencies; there is no model download or automatic cleanup.

Choose an existing project, private activity settings and unused loopback port.
Supply the existing database environment in that terminal. Start the explicit
foreground mode:

```bash
uv run --frozen panestria mission-control serve \
  --config /absolute/private/mission/activity.json \
  --assets "$PWD/apps/mission-control/dist" \
  --storage-config /absolute/private/storage.json
```

Do not combine storage mode with Ask, research or Build mutation flags. An occupied
port is preserved. Keep this foreground process running; Ctrl-C stops that exact
service. No scheduler, LAN listener, new account or host cleanup is installed.

Request a fresh one-use code in a second terminal:

```bash
uv run --frozen panestria mission-control pair-code \
  --config /absolute/private/mission/activity.json
```

Open its printed loopback origin and pair. Existing observer/Ask/Build sessions
cannot gain host storage access: this mode has separate pairing/cookies. Expect
**OWNER HOST STORAGE** and an **Owner host storage notices** panel with:

- Current observation status/time, used percentage, owner-available and reserved
  capacity. Stale/unavailable measurements are UNCONFIRMED, not zero.
- WARNING/CRITICAL codes and recommendations for owner review. Preserve active
  containers, databases/volumes, model/offline caches, backups and evidence while
  assessing keep/defer, ownership/dependencies, scope/target or added capacity.
- Explicitly selected component estimates with their basis and overlap warning;
  requested Timeshift schedules. Physical snapshot allocation stays UNKNOWN.
- Read-only project activity. No cleanup, backup-setting, inference or approval
  action is exposed by the storage panel.

To opt out, set `notifications_enabled` false in the same private file. The
existing settings poll checks at most once per minute; expect DISABLED and cleared
observations after that check. Actual full scans follow the chosen interval,
minimum60seconds, and concurrent refreshes coalesce. Do not enable expensive
component scans more often than needed. Logging out/revocation clears the view;
private paths and file contents are never sent to the browser.

The normal dashboard and activity terminal keep their existing behavior. This
mode adds no provider call, model initialization, canonical event, deletion or
backup change. Its connected proof uses actual disposable PG/cookies/HTTP/statvfs
and Chromium, with an explicit synthetic reserve threshold and forced due tick;
it does not claim actual host-budget/phone/TLS/release qualification.
