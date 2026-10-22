# Save reported Ask measurements without another inference

AOS-029-S2 now connects the canonical receipt read path to the existing private
PerformanceSnapshot history. This is an explicit owner command, not an automatic
exporter or another task store. Use the existing private loopback owner client
metadata/token, verify canonical owner/project activity scope first, then read one
exact Ask receipt. No profile view/key/model/cache/config enablement is needed.

Allowlist opaque request/context IDs, terminal state, reported public model
identity and numeric usage/timing only. Never hash/copy the complete receipt,
source titles, trace strings, prompt, answer or selected private profile/example.
Protected receipts require the existing omitted-response-digest mode and null
hash. A supplied public model manifest must agree with model/complete usage; its
absence stays unknown. Original runtime source and measurement timestamp are not
in the receipt and must never be inferred from today's checkout/capture time.

Generation/first-content/decode/token/cash values preserve missingness. Incomplete
requests have no successful latency/token/cash sample. Each completed request
contributes one reported sample, not a latency distribution, quality score,
provider attestation or qualification. Ordinary and profile Ask cohorts stay
separate. Semantic accuracy remains UNMEASURED.

Save only that sanitized source into private content-addressed files, then a
private snapshot referencing its hash. Reuse the shared history writer lock,
fail immediately if another capture owns it, and reserve bounded headroom before
adding a source. Existing byte/count limits refuse growth; no history pruning or
owner storage deletion. Capture errors leave the canonical Ask unchanged and
never trigger inference, retry, fallback or a new request. Use separate history
directories for independent capture workflows as in the existing metrics guide.

Component checks use real PG/scoped HTTP/CLI/private files and declared synthetic
keys/model/capacity. They prove both Ask cohorts, missing/malformed values,
identity mismatch, wrong-scope refusal, full-history refusal, no extra model calls
and no private content retained. They are not a new actual model benchmark,
release pass, OTel/Phoenix, exposure view or completed cross-mode observability.
