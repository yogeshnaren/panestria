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

## Connect storage policy to canonical native Build

In your **private Build config**, set the absolute path to the existing private
storage settings file and your anticipated write estimate:

```json
"storage_policy": "/absolute/private/storage.json",
"anticipated_build_write_bytes": 1073741824
```

This is opt-in: no `storage_policy` means no added probe or notification. The
selected storage file must have `notifications_enabled: true`; turning it off
removes these extra checks. A configured file that cannot be read privately
**defers** new work. It does not silently disable protection. Keep it mode0600.
The storage policy's `filesystem` must be on the same actual device as the Build
root. A capacity failure or device mismatch is a visible DEFER.

Preview without starting a worker or changing canonical state:

```bash
panestria build storage-preview --config /absolute/private/build.json
```

Expect a decision, reason, timestamped actual capacity/reserve observation,
anticipated write bytes and recommendations. `storage_policy` defaults absent;
`anticipated_build_write_bytes` defaults to1GiB when enabled, configurable from
1byte to32GiB. This is an owner planning estimate, **not an enforced write cap,
physical reservation, upper bound or guarantee against concurrent disk writers**.
Use an estimate appropriate for the selected repository and workload.

`plan inventory --config ...` checks before materializing a new snapshot;
`plan run-native --config ...` checks before each new canonical worker or final
verifier claim. An enabled run prints initial/changed storage notifications as
JSON on **stderr before new work**, leaving stdout for its normal result. The
probe uses fast filesystem capacity only; it does not repeat expensive directory,
Docker or Timeshift probes during admission. Use the explicit `storage inspect`
command for those details. It does not attribute all device usage to Panestria.

Critical pressure, unknown capacity, a mismatched device, or anticipated writes
that cross the configured free reserve defer new claims. High-use warnings below
the critical/reserve thresholds are visible but allow the existing authorized
run. A deferred run returns `status: WAIT`, `reason: storage_admission_deferred`
and the observation/recommendations. Merely viewing/retrying cannot delete data
or change the storage policy. Review keep/defer, inspect, backup-scope/target,
cache/rebuild/offline dependencies and capacity options as the owner.

Already admitted work is not killed or falsely cancelled because of this signal.
The foreground controller waits for its real outcomes; verified handoffs remain
canonical and UNKNOWN capacity stays held. If pressure later clears, explicitly
invoke the same accepted plan again. Completed nodes are reused and only new
ready work can be admitted. There is no background retry/resume daemon.
Storage notifications never approve a merge or establish release acceptance.

[Source-bound component checks](../../evidence/build-storage-admission-2026-10-21/report.json)
use actual disk observations, disposable PostgreSQL/Git, CLI, Docker/MCP and
verified handoffs. Native generation/auth/capacity are explicitly synthetic
fixtures. Required host-budget/foreground qualification, all download/artifact
admissions, growth attribution, local inbox and full Mission Control integration
remain pending R3 work; this does not complete TC05–TC08 or G3.
