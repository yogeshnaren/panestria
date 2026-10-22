# Saved performance measurements

Panestria now has a private, append-only **derived metrics history**, separate
from task state and release decisions. It reads retained evidence and saves
bounded numeric metadata with original source commits, artifact SHA256, model
identity/digest, corpus, rubric, fold, units and sample denominators. Capture
time is when the summary was saved; it does not claim a fresh benchmark ran.
This needs no API, PostgreSQL, model process or provider credential.

From the repository root:

```bash
uv sync --frozen --group dev
uv run --frozen panestria metrics capture
uv run --frozen panestria metrics show
uv run --frozen panestria metrics show --json
```

The default history is `~/.local/state/panestria/metrics/`. Each invocation prints
its exact saved path. To choose a different private directory:

```bash
uv run --frozen panestria metrics capture --directory /your/private/metrics
uv run --frozen panestria metrics show --directory /your/private/metrics
```

`capture` reads supported `local-entailment-*/` and `native-entailment-*/`
evidence folders, checks observation hashes and keeps calibration/qualification
separate. It also retains the original failed GPU prerequisite observation from
2026-10-18, explicitly labeled as failed historical evidence. It does not turn
that latency or zero GPU residency into a passing GPU benchmark.

Optional evidence inputs:

```bash
uv run --frozen panestria metrics capture \
  --mutation-report /path/to/mutation-campaign/report.json \
  --ci-report /path/to/ci-audit/report.json
```

Repeat `--mutation-report` for up to eight campaigns. The existing CI audit
format records baseline/main workflow duration with their original commits.
The mutation pilot format records raw detected/surviving faults; an incomplete
run or missing passing baseline has no detection score. New unsupported formats
require an explicit importer, rather than guessing a number from arbitrary logs.

## What the current evidence can show

| Area | Saved now | Interpretation |
| --- | --- | --- |
| Quality | Correct fraction, accuracy among answered cases, supported-label precision, coverage, false-supported count | Small historical SNLI entailment observations; calibration and held-out qualification separate. Not general Ask/Build/research accuracy. |
| Latency | Per-case p50/p95 for the recorded local entailment run; original failed warm Ask/GPU observation | Nearest-rank percentiles, with sample count. Native per-case latency was not recorded and stays UNKNOWN. |
| Resources | Original model VRAM observation under the failed prerequisite | Historical; current CPU/RAM/storage growth and peaks remain unmeasured here. |
| Cost | Actual cost when explicitly recorded, otherwise UNKNOWN | Subscription access or no reported overage is not a measured cash cost or remaining quota. |
| Test effectiveness | Bounded mutation detection fraction, survivors and source | Measures selected tests against selected injected faults, not model accuracy or a release pass. |
| CI | Recorded workflow wall time by source | Test workloads differ; keep their original run/evidence rather than claim equal-work speedups. |

For example, the held-out historical Qwen result was 21/36 correct with supported
precision 12/24. The Claude result was 33/36 correct with precision 12/13. These
used **different rubrics and execution paths**: the report keeps the cohorts
separate and does not rank them as a controlled experiment. No automatic support
qualification is granted. Small sample counts, caption-domain data and historical
runtime conditions limit what can be concluded.

The plain terminal view shows each measurement/model/fold/source separately.
JSON contains the full cohort and artifact hashes. A new capture preserves the
old files; `show` reads the latest capture. There is no blended overall accuracy
score, zero-for-unknown fallback, automatic provider probe, or network exporter.
Only allowlisted numeric metadata is saved; prompts, answers, credentials, raw
exceptions, SQL and source text are not copied into this history.

Files are mode 0600 in a mode 0700 directory, at most 256 KiB per capture. A small
16 MiB history budget refuses additional captures instead of pruning history.
Concurrent invocations should use separate directories. Review/retention is an
owner decision; this command never deletes backups, Docker data, model caches
or prior metrics. Reads are bounded; corrupt/private-permission failures remain
visible as UNAVAILABLE rather than an empty successful report.

## Measurements from new Build runs

[Runtime Build capture](RUNTIME_BUILD_METRICS.md) connects this same history
format to actual canonical invocation timestamps, protected receipt availability
and independently confirmed final checks. Use `build metrics --config ... GOAL`
for an explicit snapshot, or opt in to normal-return native-plan capture in the
private Build config. Accuracy and actual cash remain UNMEASURED. These are
lifecycle intervals with sample counts, not model-only latency or a release pass.

## Remaining R3 instrumentation

This is an evidence-history foundation, **not continuous runtime observability
or completion of AOS-029**. The report explicitly lists unmeasured areas:
current-candidate end-to-end latency, Ask answer/retrieval quality, research-domain
quality, Build success/false-done rates, crash recovery, current resource growth,
quota and actual cost. Existing in-memory sanitized spans are not silently
reclassified as durable performance history.

As each remaining R3 path becomes usable, persist its actual observations using
this same provenance discipline before calling it qualified:

- Ask: TTFT, total duration, decode throughput, cancellation; retrieval recall
  and citation correctness against a versioned labeled set.
- Delegate: search/fetch/extraction/synthesis duration, source fidelity,
  supported precision, coverage/abstention and adversarial false-support rates.
- Build: queue/worker/verifier/final-tree duration, independently verified
  completion, conflict/recovery rates and false-done failures.
- Personal platform: quota freshness/reserves, actual versus estimated cost,
  CPU/RAM/VRAM and storage growth, foreground responsiveness.

Keep provider/hardware/model/runtime/contract/corpus/policy settings as cohort
keys, with numerator/denominator and missing-data reasons. Compare compatible
cohorts; preserve failed observations and original evidence. Full release gates
and the real owner trial remain separate. Broader scheduled MVP work is paused;
these explicit metrics and mutation tasks do not restart it.

## Measurements from existing Ask receipts

[Explicit Ask capture](ASK_RUNTIME_METRICS.md) now reads an existing scoped
ordinary/profile receipt and retains reported generation/first-content/decode/
token/cash values in this same private history without another inference. Missing
accuracy/cash/source/time remain unknown, and one case is not a distribution.
No private content or output/input hash is copied. Automatic instrumentation,
latency distributions, quality, OTel/exposure and original gates remain open.
