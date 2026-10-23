# A saved runtime performance overview

AOS-029-S2 connects existing opt-in Ask, Build and research metric captures into
one owner-invoked CLI view and optional small private report. Existing collectors
and canonical task/usage/source data are unchanged. This reads saved measurements,
not live databases, models, accounts, network services or owner task content.

Up to8 explicitly selected private histories supply at most4096 snapshots and a
16MiB total read budget including unique source bytes per history. Each snapshot
uses existing PerformanceSnapshot/Measurement validation. Runtime observations
must reference exact `sources/SHA256` bytes in a private canonical directory;
source metadata supplies allowlisted owner/project, mode and original request or
goal UUID. Missing/corrupt/unsafe source files refuse the report. General historic
corpus/CI/mutation observations are explicitly counted as omitted; their separate
existing evidence view remains available. No guessed importer is added.

A cohort binds owner/project, source kind, metric/scope, model/digest, source
commit/dirty flag, corpus/rubric and fold. The latest saved capture supplies its
original measurement and sample denominator, including UNKNOWN. Distinct original
request/goal IDs supply an inventory count; repeated captures never inflate it.
That count is not a benchmark sample size. Build within-goal p95, research lifecycle
and Ask generation/first-content latency are kept distinct. No averages of
percentiles, blended accuracy, cost sum or inferred measurement time is produced.

Capture time is explicitly a saved-observation timestamp, not fresh inference,
current permission, current model qualification or a live dashboard. Runtime
source SHA checks establish retained-byte integrity, not the truth of observations
or a new runtime certificate. Original measurements keep their source hash and
relative evidence reference. Those references resolve in the selected original
histories; the overview contains numeric metadata and provenance, not a portable
archive of all original source bytes. Preserve the histories for inspection.

The output directory must differ from every selected input history. An exclusive
nonblocking private lock serializes append under a16MiB/4096-entry budget; each
report is at most256KiB, mode0600 in a mode0700 directory. No overwrite, cleanup,
pruning or owner service change occurs. Report storage is separate so existing
`metrics show` does not receive another schema. Unsafe missing-area strings and
symlinks refuse; terminal output uses bounded typed numeric/identity fields.

Read-only scope does not make metadata public: IDs, models and measurements remain
private owner data. There is no export endpoint or new consent/credential. Empty
runtime results remain empty; historical omissions/missing areas stay visible.
Original semantic judgments, exposure/tracing, resource measurement, phone views,
full AOS-029 and cumulative gates remain required.

See the [owner guide](../testing/PERFORMANCE_OVERVIEW.md) and
[source-bound component checks](../../evidence/performance-overview-2026-10-23/report.json).
