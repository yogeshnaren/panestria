# AOS-029 — OTel/Phoenix tracing, cost/usage confidence and exposure dashboard: implementation plan

**Release:** R3. **Format:** full; shared design supplies cross-component detail. **Implementation:** IN_PROGRESS (derived runtime components; full tracing/exposure pending). **Tests:** NOT_RUN. **Depends on:** AOS-012, AOS-014, AOS-028. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](../design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](../design/02-DATABASE-AND-MIGRATIONS.md), [security](../design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](../design/04-API-AND-USER-FLOWS.md), [decisions](../design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](../testing/TEST_EXECUTION.md) and [source spec](../specification/specs/AOS-029.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

Owner storage clarification (2026-10-18): connect MVP-X13 opt-in storage warnings
to local settings/inbox and capacity views, with source/time/confidence, reserves,
component/growth estimates and owner options/impact. Never sum overlapping Docker
estimates as physical totals, infer project ownership, or execute cleanup/deletion/
backup changes. The standalone [terminal monitor](../testing/STORAGE_AWARENESS.md)
does not yet satisfy the unified dashboard/inbox obligation; AOS-029 remains open.

The [owner activity storage terminal](../testing/OWNER_STORAGE_TERMINAL.md) now
delivers an opt-in banner and scrollable source/time/uncertainty/options view
through a scoped no-store API. It exposes no cleanup or browser host-data grant.
Desktop/mobile inbox, persistence, broader resource/usage/exposure integration
and whole-case qualification remain open; see the [design](../design/99-OWNER-STORAGE-TERMINAL.md).

A user can trace every relevant model/tool decision and inspect what data was authorized or accessible to cloud workers versus observed network traffic, without leaking secrets.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/telemetry/tracing.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/telemetry/redaction.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/telemetry/usage.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/telemetry/exposure.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/api/routes/usage.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/api/routes/audit.py` — owning implementation file; reconcile existing code before creating it.
- `apps/mission-control/src/views/Usage.tsx` — owning implementation file; reconcile existing code before creating it.
- `apps/mission-control/src/views/Exposure.tsx` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `TelemetryExporter.emit(redacted_span) -> ExportStatus`
- `UsageService.view(actor, period) -> ConfidenceUsageReport`
- `ExposureService.view(actor, task_id) -> ExposureReport`

**Migration ownership:** Safe usage/audit/export metadata; reuse canonical route/task/check/effect correlation, no raw credentials/prompt logging.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-029-F01 | Emit OTel traces (task/attempt/policy/route/check) with privacy-aware sampling; run Phoenix locally as optional service in Compose and ensure AgentOS works if Phoenix down. | AOS-029-S1, AOS-029-S2, AOS-029-S3; owning files/interfaces above | AOS-029-TC01, AOS-029-TC02, AOS-029-TC03, AOS-029-TC04; parameterize every condition in this clause |
| AOS-029-F02 | Usage/cost labels known, estimated, unknown; separate plan quota estimates and actual paid API/overage; reconcile provider errors and account limits only by officially supported paths. | AOS-029-S1, AOS-029-S2, AOS-029-S3; owning files/interfaces above | AOS-029-TC01, AOS-029-TC02, AOS-029-TC03, AOS-029-TC04; parameterize every condition in this clause |
| AOS-029-F03 | Exposure view shows accessible manifest for encrypted remote CLI workspace, explicit authorized payload policy and OS/network observed metadata, with provider and consent reference. | AOS-029-S1, AOS-029-S2, AOS-029-S3; owning files/interfaces above | AOS-029-TC01, AOS-029-TC02, AOS-029-TC03, AOS-029-TC04; parameterize every condition in this clause |
| AOS-029-F04 | Ensure no raw tokens, excluded paths, credentials or arbitrary full prompt bodies in telemetry, even on exception. | AOS-029-S1, AOS-029-S2, AOS-029-S3; owning files/interfaces above | AOS-029-TC01, AOS-029-TC02, AOS-029-TC03, AOS-029-TC04; parameterize every condition in this clause |
| AOS-029-AC01 | Synthetic secret injected in prompt/env never appears in Phoenix/log/event; export disable has no effect on correctness. | AOS-029-S1, AOS-029-S2, AOS-029-S3; owning files/interfaces above | AOS-029-TC01, AOS-029-TC02, AOS-029-TC03, AOS-029-TC04; parameterize every condition in this clause |
| AOS-029-AC02 | Unknown provider token usage remains unknown; no '$0' fallback in UI. Encrypted CLI egress report says accessible vs observed, not guessed payload. | AOS-029-S1, AOS-029-S2, AOS-029-S3; owning files/interfaces above | AOS-029-TC01, AOS-029-TC02, AOS-029-TC03, AOS-029-TC04; parameterize every condition in this clause |
| AOS-029-AC03 | Can trace one goal through task→worker→verifier→approval across restart. | AOS-029-S1, AOS-029-S2, AOS-029-S3; owning files/interfaces above | AOS-029-TC01, AOS-029-TC02, AOS-029-TC03, AOS-029-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-029-S1](../cursor/prompts/AOS-029-S1.md) | AOS-012, AOS-014, AOS-028 | Local OTel/Phoenix transport with explicit privacy/redaction/sampling and task/attempt/policy/check/effect correlation. | AOS-029-TC01; command/report/exit, immutable evidence and diff |
| [AOS-029-S2](../cursor/prompts/AOS-029-S2.md) | AOS-029-S1 | Known/estimated/unknown cash/native-plan summaries and authorized/accessible/observed exposure UI/API. | AOS-029-TC02; command/report/exit, immutable evidence and diff |
| [AOS-029-S3](../cursor/prompts/AOS-029-S3.md) | AOS-029-S2 | Synthetic secret/exception payload/exporter-down fixtures, trace linkage across restart and actual local footprint report. | AOS-029-TC01, AOS-029-TC02, AOS-029-TC03, AOS-029-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-029-TC01 | security | `tests/integration/test_aos_029.py::test_telemetry_secret_sentinels` | Synthetic prompt/env/token/path sentinel never appears in logs/events/Phoenix even exception paths. |
| AOS-029-TC02 | contract | `tests/integration/test_aos_029.py::test_unknown_usage_exposure_ui` | Unknown token/quota/cash never shown as zero; workspace accessible vs observed encrypted egress explained correctly. |
| AOS-029-TC03 | chaos | `tests/integration/test_aos_029.py::test_phoenix_down_no_truth_loss` | Export disabled/unavailable leaves task/approval/evidence correctness and durable event history unchanged. |
| AOS-029-TC04 | live | `tests/integration/test_aos_029.py::test_local_trace_resource_footprint` | Goal→task→worker→verifier→approval trace linkage across restart in pinned local Phoenix; report actual idle/peak footprint. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_029.py --junitxml=evidence/AOS-029.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

## Failure, operations and rollback

Unsafe scope/config/version/malformed evidence is non-retryable denial; transient safe I/O uses bounded retry; ambiguous external effects pause in RECONCILING. Mutations check current owner/project/contract/epoch and append events atomically. Timeouts/cancellation preserve durable state; diagnostics redact sensitive content. No generic retry can create exactly-once external effects.

Capture relevant task/attempt/epoch/policy/trace and immutable evidence IDs. Roll out behind this capability gate. On regression stop affected admissions, retain history/receipts/evidence and revert code/config; migrations use tested restore/forward repair. Never blindly delete history or compensate a confirmed effect. Implement setup/diagnosis, stuck-state and scoped cleanup runbook steps with this item.

## Item completion

- [ ] Every source clause maps to actual assertions and observed evidence.
- [ ] Required scenarios PASS for one recorded candidate/environment; missing/skipped/unknown/live gaps remain blockers.
- [ ] Migration/API/adapters match the approved design; material changes have an ADR.
- [ ] Applicable live/compatibility, runbook and rollback/restore evidence complete.
- [ ] User-visible results are verifiable; worker narrative grants no authority.

Only then complete this item. A release cannot promote while its other required items remain unfinished. AOS-030 trial/owner acceptance decides complete MVP; SOTA authorization remains separate.

## Owner-requested metrics foundation (2026-10-19)

The focused performance-history component adds explicit local capture/show of
existing source-bound quality, latency, resource, CI and mutation observations.
See [PERFORMANCE_METRICS.md](../testing/PERFORMANCE_METRICS.md). This is a derived
private read model; it neither replaces canonical PostgreSQL state nor completes
this item's runtime instrumentation, Mission Control, exposure or live cases.
New experiments must retain their original source, cohort, units, denominator,
artifact hashes and failure/unknown outcomes. Current end-to-end and task-domain
accuracy remain unmeasured where no qualifying evidence exists. No original
acceptance requirement or release gate is weakened by adding this component.

## Delivered runtime measurement component

The [opt-in Build capture](../testing/RUNTIME_BUILD_METRICS.md) implements part of
S2 using the existing private performance-history schema. Canonical DB intervals
and protected receipt hashes are preserved; final-check fractions do not become
accuracy, and unmeasured cash stays unknown. Automatic capture failure does not
change task state or redispatch. Original source-bound component observations
are linked from that guide. Full tracing/exposure/usage/UI and S1/S3/gate
requirements above remain intact.

## Canonical Ask receipt capture component

[Ask runtime metrics](../testing/ASK_RUNTIME_METRICS.md) now extends private history
to explicitly selected ordinary/profile receipts, with scoped metadata-only
reads, reported numeric values, unknown quality/source/time and no inference.
[Actual PG/HTTP/CLI component evidence](../../evidence/ask-runtime-metrics-2026-10-22/report.json)
uses declared synthetic keys/model/capacity. This is partial S2; automatic
instrumentation, exposure/React/OTel and original cases/gates remain pending.

## Canonical research measurements and owner-reported judgments

[Research runtime metrics](../testing/RESEARCH_RUNTIME_METRICS.md) now connects
existing validated retained drafts, canonical event intervals/receipt outcomes
and latest exact owner-review counts to the same private history. It preserves
OWNER_REPORTED scope and undefined/missing denominators; semantic accuracy,
actual cash and model-only timing remain unknown. The command creates no model,
search, state write, judgment or training right. [Original component evidence](../../evidence/research-runtime-metrics-2026-10-23/report.json)
uses actual PG/CAS/reader/CLI with explicit model/transport/dispatch fixtures.
S2 remains partial; tracing/exposure/UI, resource samples, domain baselines and
original gates/owner acceptance above remain open.
