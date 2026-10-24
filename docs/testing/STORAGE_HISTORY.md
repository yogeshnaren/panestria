# Keep bounded storage observations across restarts

This optional setting lets the existing storage watcher remember a recent baseline
after its process restarts. That makes disk-growth and changed Timeshift-schedule
warnings useful across those restarts. It does not clear space or change backups.

In your existing private mode0600 [storage settings](STORAGE_AWARENESS.md), add
an absolute, dedicated private history directory and enable notifications:

```json
{
  "notifications_enabled": true,
  "history_directory": "/absolute/private/panestria-storage-history"
}
```

Keep your other selected filesystem/threshold/component settings. The directory is
created with mode0700; existing shared directories and symlinks are refused. This
is an extra opt-in: leaving out `history_directory` keeps the original memory-only
behavior. There is no package/model download or new service to install.

Start the existing foreground watcher:

```bash
uv run --offline --frozen panestria storage watch \
  --config /absolute/private/storage.json
```

The same field works with the [activity terminal](OWNER_STORAGE_TERMINAL.md) and
separately paired [Mission Control storage mode](MISSION_STORAGE_NOTICES.md).
Warnings/recommendations include `storage_history_saved`, `storage_history_full`
or `storage_history_unavailable`, with the previous compatible sample time or
UNKNOWN. Current capacity is still measured afresh. Stopping/reopening a watcher
does not refresh an old sample's time or make it a current capacity observation.

Expect immutable `SHA256.json` samples and a lock file in the selected directory.
Each sample retains its original observation time, capture time, collector/settings/
filesystem hashes and report. These are private diagnostic metadata, including the
selected filesystem path, labels, counts and backup schedule observations. They
contain no scanned file contents or credentials. Inspect a deliberately selected
sample locally, for example `python3 -m json.tool /absolute/private/history/SHA256.json`;
do not share the directory as a public report. Browser notices expose no paths.

The fixed budget is4MiB logical record data and512 directory entries including the
lock, at most511 samples; filesystem overhead is additional. The configured probe
interval is unchanged (minimum60seconds, default300). At the default interval the
entry limit can be reached in roughly42hours of continuous sampling; oversized
reports or the byte limit can stop retention sooner. After FULL/UNAVAILABLE the
current storage observation continues and explicitly warns that history was not
saved. No automatic deletion, pruning, compression or replacement directory occurs.
An OS/filesystem read or write that stalls leaves the existing observer STALLED;
it starts no replacement collector and cannot promise a fresh capacity reading.
Preserve history, defer writes, review ownership/capacity or deliberately choose a
different private directory yourself. Existing files are never removed by this mode.

Only samples no more than24hours old, with the same collector/settings/filesystem
binding, can supply a restart baseline. Missing/incompatible/old/future data stays
UNKNOWN. This does not prove exclusive physical component allocation, benchmark
resource limits, attribute a Timeshift change to Panestria or complete R3.

Set `notifications_enabled` false to stop new automatic observations/history using
the existing settings poll. Removing the history field stops retention while
leaving ordinary notifications enabled. Preserve the original files; opt-out
does not delete them. `storage inspect` remains a fresh read without saving history.
See [the design](../design/118-BOUNDED-STORAGE-HISTORY.md) for scope and bounds.
