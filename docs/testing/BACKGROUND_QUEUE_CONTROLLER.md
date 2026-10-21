# Run a finite reviewed background queue

`background work` polls for eligible queued work without requiring an item ID
for every job. It is explicitly enabled, finite and serial. It installs no OS
service and does not resume the owner's paused Codex scheduled task.

First follow the [queue](BACKGROUND_WORK_QUEUE.md), [account link](BACKGROUND_ACCOUNT_LINK.md)
and [runner](BACKGROUND_RUN.md) guides. Each item needs a reviewed accepted PUBLIC
plan, zero API cash, current linked actual account/runtime, eligible quota/billing
reports, capacity and foreground reserve. This command creates or refreshes none.

With the same private database environment and Build configuration:

```bash
uv run --frozen panestria background work --config /absolute/private/build.json \
  --ticks 12 --poll-seconds 5 --jobs 1 --allow-background-subscription-run
```

It stays in that terminal until its bounds, cancellation or a stop condition.
Expect metadata-only JSON lines: QUEUE_TICK, QUEUE_JOB_RETURNED for an attempted
item, then a final receipt. Idle ticks are observations, not model work or goal
progress; they neither probe the provider, claim capacity nor write events.

Bounds: 1–64 ticks, 5–60 seconds between ticks, 1–8 attempted jobs. Intervals
count waiting, not time inside a job. Each admitted job retains its immutable
wall/quota/billing limits. A tick renews no report, budget or permission. Default
one-job mode returns after final verification reaches WAITING_APPROVAL. Use the
separate Build review CLI/TUI for exact merge.

A larger job bound can wait for owner review/merge before capacity admits another
item. Held final reviews can reserve the background slot. Only never-started
eligible reviewed items are considered. A race, denial, UNKNOWN, failure or
partially paused selected job stops the controller immediately: no alternate
fallback, implicit resume, approval, merge, timer or provider switch.

Ctrl+C uses the existing active-run cancellation path. A crash/uncertain outcome
needs canonical `background runs`, Build progress and claim inspection; do not
use a new key to erase uncertainty. Counters are a local receipt, not a second
task store. No live scheduler/job is enabled by this implementation.

[Component evidence](../../evidence/background-controller-2026-10-21/report.json)
uses real synthetic PostgreSQL/Git/MCP/Docker/CLI with explicit native/account/
capacity fixtures. Full S5/S7, live qualification and cumulative G3 remain separate.
