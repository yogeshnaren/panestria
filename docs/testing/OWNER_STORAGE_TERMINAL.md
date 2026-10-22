# Storage warnings beside project activity

This read-only terminal shows host capacity and owner review recommendations
alongside existing project activity. It starts no model or worker and performs
no deletion, pruning or backup-setting changes. Storage belongs to the host;
these observations do not establish which project or program caused usage.

Use current main with `uv sync --frozen --group dev`. The database must already
be migrated and contain your existing owner/project. Load its private
`PANESTRIA_DATABASE_URL` environment without printing it. Use the unchanged IDs
from your existing private Ask or Build configuration. Choose an unused
loopback port; 8783 below is an example, not a reserved service.

Prepare a new private activity directory once:

```bash
uv run --offline --frozen panestria activity init \
  --directory "$HOME/.panestria-storage-terminal" \
  --owner-id OWNER_UUID --project-id PROJECT_UUID --port 8783
```

Expect CONFIGURED and `server_started: false`. Create the following
`$HOME/.panestria-storage-terminal/storage.json` with permissions `600`.
If it already exists, inspect/edit it deliberately instead of overwriting it.

```json
{
  "schema_version": 1,
  "notifications_enabled": true,
  "filesystem": "/",
  "interval_seconds": 300,
  "include_docker": false,
  "include_timeshift": false,
  "components": []
}
```

```bash
chmod 600 "$HOME/.panestria-storage-terminal/storage.json"
```

Default warning/critical thresholds are 80%/90%, free reserve 20 GiB. Used
percent is used divided by used plus owner-available space; filesystem reserved
blocks are not owner free space. A separate filesystem may need its own absolute
selection. Add only deliberate component paths; see the [probe guide](STORAGE_AWARENESS.md)
for costs, Docker overlap, Timeshift schedules and protected dependencies.

Terminal 1, with the existing private database environment loaded:

```bash
uv run --offline --frozen panestria activity serve \
  --config "$HOME/.panestria-storage-terminal/activity.json" \
  --storage-config "$HOME/.panestria-storage-terminal/storage.json"
```

Leave this foreground process running. An occupied port is refused without
stopping its owner. In terminal 2:

```bash
uv run --offline --frozen panestria activity tui \
  --config "$HOME/.panestria-storage-terminal/activity.json"
```

Expect PROJECT TASKS, then a storage banner showing the highest-severity notice
or explicit collection/disabled/unavailable status. Press `o` for HOST STORAGE;
use PgUp/PgDn to read the complete warnings/options, `r`/F5 to read the cache,
`b`/Esc to return and `q` to quit. Refresh does not bypass sampling limits.
An OBSERVED sample carries its timestamp; stale values are labeled unconfirmed.
No warnings in one sample is not a host-health or release certificate.

`include_docker: true` explicitly permits the existing local-daemon metadata
probe. `include_timeshift: true` reads bounded schedule configuration only, never
runs Timeshift or alters its schedule. A denied source is UNKNOWN; physical
snapshot bytes remain UNKNOWN. Component allocations and Docker categories may
overlap. Review cache rebuild/download/offline impact and preserve databases,
models, active volumes and evidence before any owner-managed cleanup decision.

To stop collection, change `notifications_enabled` to `false` in the private
file. It is detected at the next demand policy check (at most once per sixty
seconds); an already running read may finish, but its result is discarded after
the off-setting is observed. Ctrl+C stops this foreground server and prevents
new/late publication. It does not terminate a stuck kernel filesystem read.
STALLED prevents replacement collectors while that read is held. No requests
means no new collection. Settings errors are UNAVAILABLE, not zero usage.

Without `--storage-config`, activity operates as before with no probes. This
integration is not enabled for Mission Control/phone. It retains no measurement
history across restart and does not replace Build's separate write preflight.

[Component evidence](../../evidence/storage-status-terminal-2026-10-22/report.json)
includes an actual disposable PG/HTTP/CLI/PTY journey and read-only filesystem
capacity. A synthetic free-reserve threshold triggers a warning without filling
the disk. Clock/probe controls test stalls and revocation; they do not qualify
actual host pressure, Docker/Timeshift attribution or G1/G3.
