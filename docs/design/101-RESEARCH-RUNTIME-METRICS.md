# Save retained research measurements and separate owner judgments

Partial AOS-029-S2. Extend the existing private performance history with one
explicit `metrics capture-research` command. It inspects an existing retained
draft and latest owner review using the canonical protected readers, in one
repeatable-read PostgreSQL view. Existing inspection takes project/task locks;
the capture creates no database rows, event, grant, state transition or judgment.
It initializes no model, search service, credential or certificate store.

Allowlist opaque scope/request/synthesis IDs, original stored model identity,
token counts, selected/omitted passage counts, original event sequence/timestamps,
canonical collection receipt counts/reservations, review event sequence and verdict
counts. Copy no question, source quote/URL, draft text, owner rationale, prompt,
raw exception or private content fingerprint. Repeated unchanged captures reuse
the sanitized source hash; they are not additional inference observations.

The STARTED-to-RETURNED event timestamp interval includes controller/model startup,
inference, validation and retention. It is not model-only duration or question-to-
answer latency; wall-clock timestamps can be affected by clock changes. Invalid
ordering or negative/nonfinite intervals refuse. Original model timing/cash and
runtime build source are not retained in the draft and remain unmeasured.
One draft supplies one lifecycle sample, with no distribution claim.

Collection fractions count canonical RETURNED search and RETAINED fetch receipts
over their selected dispatch records, including UNKNOWN/error records in the
denominator. Reservations are capacity commitments, not measured bytes received
or upstream usage. No collection/dispatch denominator remains unknown. These
measure receipt outcomes, not source truth, retrieval recall or factual support.

Read and bind the latest immutable owner review to the exact current draft before
counting its verdicts. Report fully SUPPORTED and CONTRADICTED fractions separately
over judgments other than NOT_FACTUAL; PARTIALLY_SUPPORTED stays in the denominator
and never counts as fully supported. The scope explicitly says OWNER_REPORTED.
No review means UNMEASURED; an all-NOT_FACTUAL review has an undefined denominator.
Neither metric fills quality.correct_fraction, automatic support or a release gate.

Use the same private history format, nonblocking capture lock and conservative
16MiB/4096-entry write budget as explicit Ask capture, with at most16KiB sanitized
source metadata and256KiB per snapshot. Reject unsafe paths/locks, contention,
full history, foreign scope and unavailable/stale/cancelled draft inputs. Nothing
prunes or deletes storage. History cannot become task state, retry permission,
training rights, a benchmark or a qualification certificate.

The [guide](../testing/RESEARCH_RUNTIME_METRICS.md) and
[original observations](../../evidence/research-runtime-metrics-2026-10-23/report.json)
describe real disposable PG/CAS/reader/CLI checks with explicit synthetic model,
transport and dispatch-metadata fixtures. Full domain quality, tracing, exposure,
resource instrumentation, G2/G3 and the owner trial remain pending.
