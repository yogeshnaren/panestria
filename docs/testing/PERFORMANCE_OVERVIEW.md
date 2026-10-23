# See saved Ask, Build and research measurements together

First capture measurements through the existing [Ask receipt](ASK_RUNTIME_METRICS.md),
[Build runtime](RUNTIME_BUILD_METRICS.md) and [research draft](RESEARCH_RUNTIME_METRICS.md)
commands. Captures are opt-in; this command does not start measurement or inference.
If you used their shared default directory, run:

```bash
panestria metrics overview
panestria metrics overview --json
```

If you chose separate private histories, select them explicitly and optionally
save one combined report in a **different** private directory:

```bash
panestria metrics overview \
  --directory /absolute/private/ask-metrics \
  --directory /absolute/private/build-metrics \
  --directory /absolute/private/research-metrics \
  --output /absolute/private/performance-overviews
```

Expect a row per latest saved measurement/cohort, including mode, owner/project,
metric, original sample denominator, model, distinct original record count and
capture time. `SAVED` prints the exact new private report path. `--json` prints
the report to stdout; the saved-path acknowledgment goes to stderr. Keep reports
and original histories private. No API, database, model or credential is needed
to read these already-retained files.

Interpret the rows carefully:

- Ask generation/first-content timings, Build invocation lifecycle percentiles and
  research synthesis lifecycle are different measurements and remain separate.
- `original n` is the latest observation's original denominator. `distinct records`
  is an inventory of original request/goal IDs represented in that cohort. Saving
  one request repeatedly does not create more requests or measured samples.
- Projects, ordinary/profile Ask, models/digests, scopes, source and evaluation
  identities stay separate. The overview displays the latest capture in each
  cohort; it calculates no cross-run p95, overall accuracy or weighted average.
- Latest UNKNOWN stays UNKNOWN even if an older capture contained a number. Owner
  research judgments and required-check fractions are not semantic accuracy.
- Capture time means when metadata was saved, not fresh inference or the original
  measurement time. Nothing renews a policy, permission, certificate or billing
  observation. Original `sources/HASH` references belong to the selected histories;
  preserve them alongside the report for source inspection.
- Historical corpus/CI/mutation observations are counted as omitted. Use the
  existing [historical metrics view](PERFORMANCE_METRICS.md) for those cohorts.

Missing/corrupt sources, unsafe paths/private permissions, excessive history or
output storage return UNAVAILABLE. Select at most8 existing private histories
and a smaller coherent set if there are more than128 resulting cohorts. Inputs
have a4096-snapshot/16MiB bounded read budget. Each saved report is at most256KiB;
the separate output history refuses growth at16MiB/4096 entries. A busy writer
refuses rather than retries. Panestria deletes nothing; choose retention/storage
options yourself. Never put overview JSON into a collector's input history.

[Component evidence](../../evidence/performance-overview-2026-10-23/report.json)
uses actual private filesystem/CLI I/O with synthetic retained measurements:
three modes, repeated captures, scope/model separation, latest UNKNOWN, append-only
save, source corruption, symlink/terminal-data refusal and storage pressure. It
runs no new model/provider or benchmark and qualifies no accuracy/latency gate.
Full automatic usage/tracing/exposure/resource/phone integration and original
AOS-029/G3/owner acceptance remain open.
