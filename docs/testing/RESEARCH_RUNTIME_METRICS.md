# Save measurements from a retained research draft

After the existing [local synthesis](LOCAL_RESEARCH_SYNTHESIS.md) retains a draft,
use its request UUID and unchanged private synthesis config. Load the existing
private `PANESTRIA_DATABASE_URL` environment without printing its value. This
command reads the retained draft, its bound source passages and any latest
[owner claim review](OWNER_CLAIM_REVIEW.md). It starts no model/search service,
requests no API/login, and writes no database state or approval.

```bash
uv run --offline --frozen panestria metrics capture-research \
  --config /absolute/private/synthesis.json --request-id REQUEST_UUID \
  --directory /absolute/private/research-metrics
uv run --offline --frozen panestria metrics show \
  --directory /absolute/private/research-metrics
uv run --offline --frozen panestria metrics show \
  --directory /absolute/private/research-metrics --json
```

Expect SAVED, a snapshot basename and sanitized source SHA256. Snapshots and
`sources/HASH` are mode0600 inside mode0700 directories. The default directory
without `--directory` is `~/.local/state/panestria/metrics`; choose a separate
private directory if you want a distinct research history. `show` displays the
latest capture only. Capture time is when metadata was saved, not when inference
ran. Repeated captures of unchanged records reuse source bytes and create a new
snapshot; do not count them as independent model runs.

| Saved measurement | What it means |
| --- | --- |
| Synthesis lifecycle seconds | Original STARTED-to-RETURNED canonical event timestamp interval; includes controller/model startup, inference, checking and retention. Wall-clock based, not model-only, full request latency or p95. |
| Input/output tokens | Counts retained in that original completed draft, with its stored model/digest. Today's model selection is not substituted. |
| Search returned / fetch retained receipt fractions | Canonical receipt outcomes over dispatches. UNKNOWN/errors remain in the denominator; no collection/empty denominator stays UNKNOWN. This does not establish source truth or retrieval quality. |
| Reserved body bytes | Capacity reserved by fetch dispatches; not actual received bytes, storage growth or measured upstream usage. |
| Owner supported / contradicted fractions | Latest exact owner review, explicitly OWNER_REPORTED, over claims other than NOT_FACTUAL. Partially supported claims are not fully supported. No review is UNKNOWN; all-NOT_FACTUAL has an undefined denominator. |
| Semantic accuracy / actual cash | UNKNOWN. Owner judgments, citations, subscription access and no new inference do not supply these measurements. |

The source metadata contains opaque IDs, original timestamps and numeric counts;
it copies no question, URL, source passage, answer, owner rationale, prompt,
credential or private text fingerprint. The existing reader refuses foreign
scope, cancelled/stale inputs, missing or corrupt protected artifacts rather
than relabeling old data. It uses short canonical database locks while inspecting
the current draft; a busy/unavailable database may return UNAVAILABLE.

`metrics_capture_busy` means another capture owns this history. There is no wait
or retry. `research_metrics_history_budget_reached` means the conservative16MiB
or4096-entry write budget is full. Further capture refuses before another source
is added. Preserve the history, choose a separate private directory, or make your
own retention/storage decision. Panestria deletes nothing. Other unavailable
receipt/config/scope errors use a bounded generic code, never raw database errors
or private content. Capturing never retries model/search work or completes a goal.

These are descriptive observations, not automatic support qualification,
retrieval recall, latency distributions, a source-version/runtime certificate,
training permission or G2/G3 acceptance. See the
[design](../design/101-RESEARCH-RUNTIME-METRICS.md) and
[original component observations](../../evidence/research-runtime-metrics-2026-10-23/report.json).
Actual PG/CAS/isolated-reader/CLI checks use explicit synthetic model/transport
and dispatch-metadata fixtures. No live inference/search benchmark was run for
this capture feature.
