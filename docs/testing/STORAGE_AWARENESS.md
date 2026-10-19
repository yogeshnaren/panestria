# Read-only storage visibility and terminal warnings

From a bootstrapped checkout containing this component:

```bash
uv run --offline --frozen panestria storage inspect
```

This one-time command reports filesystem capacity, owner-available bytes, reserved
blocks and pressure warnings as JSON. No database, model or provider is needed.
It does not scan directories or contact Docker by default. Used percent follows
`used / (used + owner available)`; reserved blocks are not owner free space.

Copy [the settings example](../examples/storage-settings.json) to a private local
file, set its permissions to `600`, and pass its absolute path:

```bash
uv run --offline --frozen panestria storage inspect --config /absolute/private/storage.json
```

The example explicitly selects Docker's local Unix daemon and Timeshift config;
set either `include_...` field to `false` to omit it. Docker rootless/nonstandard
sockets are initially unsupported and appear UNKNOWN. Remote Docker contexts and
DOCKER_HOST are never used. Missing/denied/timed-out measurements stay UNKNOWN,
never zero; no sudo or extra privileges are requested.

To estimate selected directories, add up to eight `components` entries:

```json
{"label": "model_cache", "path": "/absolute/selected/model-cache"}
```

Each explicit selection runs unprivileged GNU `du` with a three-second timeout,
one filesystem and no symlink traversal. Incomplete scans become UNKNOWN. Large
scans can be expensive; review selections before enabling frequent monitoring.
Within-scan hardlinks are deduplicated; overlapping selections/shared extents can
still be counted twice. A component receives an estimated filesystem share only
on the monitored device. Never add these values as exclusive physical totals.

Docker image/container/volume/build-cache sizes are daemon-wide logical/shared
estimates, not automatically Panestria-owned or proof of a 40% physical disk share.
Review `docker system df -v` locally for individual owners and dependencies.
“Reclaimable” does not mean safe to delete. Cache review must explain rebuild,
download and offline impact; preserve databases/volumes, active containers,
required images/models and historical evidence.

Timeshift output shows schedule/retention config only. It never runs Timeshift or
trusts cached `snapshot_size` as current physical allocation. An hourly due-check
is not an hourly snapshot policy; retention counts are not a byte cap. Removing
the last snapshot for an enabled period may cause a new copy at the next check.
Shared rsync hardlinks prevent summing snapshot apparent sizes as exclusive bytes.
See [Timeshift's official documentation](https://github.com/linuxmint/timeshift/blob/master/README.md)
and [Docker's usage documentation](https://docs.docker.com/reference/cli/docker/system/df/).
This implementation borrows no code from either project.

To monitor, set `notifications_enabled` to `true` in the private file and run:

```bash
uv run --offline --frozen panestria storage watch --config /absolute/private/storage.json
```

It stays in that terminal until Ctrl-C, prints initial state/changed warnings/
recovery and suppresses unchanged warnings. The minimum interval is 60 seconds.
Set `notifications_enabled` back to `false` to stop at the next poll. A config-read
failure stops it visibly. No daemon, cron job or desktop/mobile push is installed.
Reports stay local; no task history, file contents or cloud telemetry is collected.

Default warnings: 80%/90% usage, 20 GiB free reserve, selected components at 20% of
filesystem total, free-space drops of 5 GiB between samples, and observed Timeshift
schedule/retention changes. A change observation cannot identify who changed it.
Options explain owner review: keep/defer work, inspect usage, review backup scope/
target, inspect unused cache candidates with rebuild impact, or add/move storage.
**No agent deletion, pruning, volume removal or backup-setting change is executed.**
Existing applications and scheduled backups can keep writing independently.

For a planned large write, preview its reserve impact:

```bash
uv run --offline --frozen panestria storage inspect --expected-write-bytes 10737418240
```

This estimates headroom after 10 GiB; it does not reserve bytes or admit/stop a
task. Automatic admission wiring, source-bound growth attribution across restarts,
preflight of all downloads/builds/backups, unified Mission Control/TUI settings/
inbox and actual host-budget qualification remain R3 work. This terminal component
is partial AOS-018-S4/MVP-X13 delivery, not TC05–TC08 or G1/G3 qualification.
