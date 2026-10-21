# Save measurements from canonical Build runs

For an existing canonical plan goal, use the same private Build config and
`PANESTRIA_DATABASE_URL` as the [native plan runner](NATIVE_PLAN_EXECUTION.md):

```bash
panestria build metrics --config /absolute/private/build.json GOAL_UUID
```

Expect JSON with `status: SAVED`, a snapshot filename and the SHA256 of its source
metadata. Open the latest measurements using the existing history reader:

```bash
panestria metrics show --directory /absolute/private/BUILD_ROOT/metrics
panestria metrics show --directory /absolute/private/BUILD_ROOT/metrics --json
```

`BUILD_ROOT` is the existing `root` in your private Build config. Each capture
writes a new mode0600 snapshot under its private `metrics/` directory. Protected,
content-addressed source metadata is in `metrics/sources/SHA256` (mode0400). An
unchanged observation reuses the source bytes; capture time does not imply a new
worker run. Manual capture reads canonical state and retained receipts. It does
not dispatch work, grant permissions or change a goal/check/approval.

To save a snapshot automatically after a **normal return** from the canonical
native-plan runner, explicitly add this boolean to your private Build config:

```json
"record_runtime_metrics": true
```

The default is false. This setting grants no provider access and starts no new
service. Captures are serialized with a private lock. History plus raw metric
sources has a conservative16MiB write budget and4096-file reader/count bounds;
source metadata is at most32KiB, snapshots at most256KiB. A full history refuses
additional capture; it never prunes, deletes backups or changes retention.

An automatic capture error adds `metrics.status: UNAVAILABLE` to the runner's
result. The actual canonical outcome is preserved. It causes no model retry,
redispatch or approval. A crash/preflight exception or interrupted process may
have no automatic capture; inspect canonical state and use the explicit command.
Metrics are observations, not crash recovery or qualification authority.

| Measurement | Meaning and limits |
| --- | --- |
| Invocation lifecycle p50/p95 by kind | Database intent creation to acknowledged return, only for RETURNED records with a readable protected receipt. Nearest-rank percentiles include queue/controller/tool/verification time; these are not model-only latency. Nested native/tool intervals overlap and must not be summed. Sample counts remain visible. |
| Receipt-present fraction | Protected receipt bytes available for the selected invocation records. UNKNOWN/CLAIMED records are not silently counted as returned latency. This fraction is not successful-task accuracy. |
| Final required-check pass fraction | Current independently confirmed final evidence against original required checks. Intermediate successes do not fill it. Missing/unconfirmed final evidence leaves it unmeasured. |
| Accuracy and actual cash | UNMEASURED. Deterministic checks or subscription access cannot supply either value. |

Source metadata retains owner/project/goal/contract identity, invocation/task/
attempt/kind/state, original timestamps, binding/configuration/receipt hashes and
an original native controller source hash when actually present. It copies no
prompt, code, model response, database credential or arbitrary exception text.
No model identity, Git source commit, cost or release pass is guessed. At most64
invocations are selected from one repeatable-read canonical snapshot. Old
[historical metric snapshots](PERFORMANCE_METRICS.md) remain readable unchanged.

[Component evidence](../../evidence/build-runtime-metrics-2026-10-21/report.json)
covers actual disposable PostgreSQL, CLI, protected receipts, Docker/MCP checks,
private file persistence, exact database durations, raw-source deduplication,
full-history refusal without another launch, and UNKNOWN cancellation records
with held capacity. Native generation/authentication/capacity are explicit
fixtures. There is no new live inference/provider call or G3 qualification.

This is partial AOS-029-S2 delivery. Cross-mode instrumentation, complete
quality baselines, resource/token/cost/exposure views, OTel/Phoenix and release
qualification remain separate R3 work.
