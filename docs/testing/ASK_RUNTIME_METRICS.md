# Save measurements from an existing Ask request

After an Ask completes, retain its request UUID from the terminal/receipt. This
command reads that existing canonical receipt; it does not ask the model another
question. It works with ordinary local Ask or an explicitly enabled qualified
profile service. It enables neither service and needs no database credential,
profile key or model cache.

Use the existing [private owner client](PROFILE_STYLE_TERMINAL.md) file. For an
ordinary Ask server, the same metadata-only format works without enabling any
profile routes. Copy the actual existing owner/project/port/token-file metadata
into a private mode0600 file outside Git:

```json
{
  "schema_version": 1,
  "owner_id": "<existing owner UUID>",
  "project_id": "<existing project UUID>",
  "bind_host": "127.0.0.1",
  "bind_port": 8766,
  "token_file": "/absolute/private/existing-owner.token"
}
```

The token remains in its existing private file. This is the small client metadata
file, not the larger local server configuration containing model/cache paths.
Only IPv4 loopback is supported here. The service must expose its canonical
activity and Ask receipt routes; an observer-only server has no Ask receipts.
Wrong scope/auth/missing receipt/storage errors return UNAVAILABLE without a
fallback or mutation.

```bash
uv run --frozen panestria metrics capture-ask \
  --config /absolute/private/owner-client.json --request-id REQUEST_UUID \
  --directory /absolute/private/ask-metrics
uv run --frozen panestria metrics show --directory /absolute/private/ask-metrics
uv run --frozen panestria metrics show --directory /absolute/private/ask-metrics --json
```

SAVED reports the snapshot basename and sanitized source hash. The snapshot lives
in the chosen directory, with source metadata under `sources/HASH`. With no
`--directory`, the existing default is `~/.local/state/panestria/metrics`.
Directory/file permissions are0700/0600. The bounded16MiB history refuses growth
instead of removing anything; an active capture lock returns UNAVAILABLE rather
than waiting/retrying. `ask_metrics_history_budget_reached` means stop adding captures and review your
chosen history directory; you can choose a separate private directory or make an
explicit owner retention/storage decision. Panestria deletes nothing.
`metrics_capture_busy` means another writer owns this history; a later explicit
capture is your decision. Scope/auth codes require checking the selected existing
client configuration. Other errors use a generic bounded code, never a raw
exception payload. Preserve the original request and inspect any errors.

The latest snapshot shows reported generation duration, first-content latency,
decode throughput, input/output tokens and actual cash **only when present** in
the canonical receipt. Missing is UNKNOWN; incomplete/cancelled requests do not
contribute a successful sample. Accuracy remains UNKNOWN. Local-provider elapsed
and first-content timings exclude service/model startup and are not full
end-to-end request latency. Capture time is when this metadata was saved, not
when inference ran. One request has sample count1 and supplies no p95 claim.

Ordinary/profile cohorts are separate. Optional pinned model identity comes from
the original canonical context/usage, not today's model-selection file. Runtime
build source, original measurement timestamp, quality, resource peaks, quota and
release qualification remain unmeasured. Repeated capture creates a new snapshot
of the same source; do not count it as another inference observation.

Prompts, answers, source titles, raw trace strings, profile/example values and
private input/output fingerprints are excluded. No external telemetry, model
call, profile disclosure, training export, database write or storage cleanup is
performed. See [design98](../design/98-ASK-RUNTIME-METRICS.md) and the
[general metrics guide](PERFORMANCE_METRICS.md).

[Original component observations](../../evidence/ask-runtime-metrics-2026-10-22/report.json)
retain the initial duplicate-module collection error, corrected21-case suite,
both-cohort10-case checks and affected refusal-code case separately. No new live
model benchmark was run for this read-only metadata feature.
