# AOS-016 — Local inference adapter and warm/cold/pressure benchmarking: implementation plan

**Release:** R1. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-011, AOS-015. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](../design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](../design/02-DATABASE-AND-MIGRATIONS.md), [security](../design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](../design/04-API-AND-USER-FLOWS.md), [decisions](../design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](../testing/TEST_EXECUTION.md) and [source spec](../specification/specs/AOS-016.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

A user can invoke an offline steward locally, measure response speed and memory use on the actual GPU, and fail conservatively when inference is unavailable.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/brokers/inference/base.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/brokers/inference/ollama.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/brokers/inference/api.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/brokers/inference/model_manager.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/resources/benchmark.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `InferenceProvider.generate/stream/capabilities(request)`
- `ModelManager.admit_load/model_status/unload(model_ref)`
- `BenchmarkRunner.measure(profile, model_digest, corpus) -> BenchmarkReport`

**Migration ownership:** Model/runtime/benchmark metadata and inference usage/route refs; raw API secrets outside tables/worker scope.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-016-F01 | Implement `InferenceProvider` contract for chat/generate/stream/embed with capability manifest, model version, context/token budget, retries and actual/unknown resource usage; first implementation Ollama with local endpoint. | AOS-016-S1, AOS-016-S2, AOS-016-S3; owning files/interfaces above | AOS-016-TC01, AOS-016-TC02, AOS-016-TC03, AOS-016-TC04; parameterize every condition in this clause |
| AOS-016-F02 | Choose a small legal-to-distribute instruct model from measured hardware catalog; run bounded prompt, disable cloud fallback when offline/Restricted. Warm and cold start benchmark; TTFT, tokens/s, completion and GPU/CPU RSS measured. | AOS-016-S1, AOS-016-S2, AOS-016-S3; owning files/interfaces above | AOS-016-TC01, AOS-016-TC02, AOS-016-TC03, AOS-016-TC04; parameterize every condition in this clause |
| AOS-016-F03 | Overload guard: queue/cancel at capacity, avoid multiple resident copies, CPU deterministic fallback for status/routing, communicate unavailable instead of silently calling API. | AOS-016-S1, AOS-016-S2, AOS-016-S3; owning files/interfaces above | AOS-016-TC01, AOS-016-TC02, AOS-016-TC03, AOS-016-TC04; parameterize every condition in this clause |
| AOS-016-F04 | Tie inference events to task/trace and preserve memory-source citations if used by Ask. | AOS-016-S1, AOS-016-S2, AOS-016-S3; owning files/interfaces above | AOS-016-TC01, AOS-016-TC02, AOS-016-TC03, AOS-016-TC04; parameterize every condition in this clause |
| AOS-016-AC01 | Full network disabled: steward answers bounded local prompts and emits no external requests. | AOS-016-S1, AOS-016-S2, AOS-016-S3; owning files/interfaces above | AOS-016-TC01, AOS-016-TC02, AOS-016-TC03, AOS-016-TC04; parameterize every condition in this clause |
| AOS-016-AC02 | Warm and cold runs reported separately on physical Omen, with model size and actual VRAM; memory overload refuses safely and recovers. | AOS-016-S1, AOS-016-S2, AOS-016-S3; owning files/interfaces above | AOS-016-TC01, AOS-016-TC02, AOS-016-TC03, AOS-016-TC04; parameterize every condition in this clause |
| AOS-016-AC03 | Timeout and model unload mid-stream lead to explicit degraded/unavailable status, not half a success event. | AOS-016-S1, AOS-016-S2, AOS-016-S3; owning files/interfaces above | AOS-016-TC01, AOS-016-TC02, AOS-016-TC03, AOS-016-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-016-S1](../cursor/prompts/AOS-016-S1.md) | AOS-011, AOS-015 | Typed provider protocol, Ollama adapter and fake transport fixtures with deadlines/deltas/unknown usage. | AOS-016-TC01; command/report/exit, immutable evidence and diff |
| [AOS-016-S2](../cursor/prompts/AOS-016-S2.md) | AOS-016-S1 | Measured model admission/warm-cold/load/unload/pressure path and local-only policy; no silent cloud fallback. | AOS-016-TC02; command/report/exit, immutable evidence and diff |
| [AOS-016-S3](../cursor/prompts/AOS-016-S3.md) | AOS-016-S2 | Baseline opt-in one API SDK adapter contract (MVP-X01), credential-handle separation and independently scoped live compatibility plus physical local benchmark. | AOS-016-TC01, AOS-016-TC02, AOS-016-TC03, AOS-016-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-016-TC01 | contract | `tests/integration/test_aos_016.py::test_inference_stream_failures` | Deltas/terminal/errors/unknown usage typed; partial failure not reported successful; context/token/deadline bounds enforced. |
| AOS-016-TC02 | security | `tests/integration/test_aos_016.py::test_restricted_route_no_fallback` | Restricted/offline requests cannot select API even if local model missing/OOM; denied destination cannot be activated by prompt. |
| AOS-016-TC03 | live | `tests/integration/test_aos_016.py::test_local_warm_cold_benchmark` | Actual installed model/hash/hardware produces separate warm/cold TTFT/quality/RSS/VRAM measurements; no simulated performance pass. |
| AOS-016-TC04 | live | `tests/integration/test_aos_016.py::test_approved_sdk_adapter` | Explicit eligible API route with consent/cap and protected credential handle works; mocked CI alone cannot establish live account/version compatibility. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_016.py --junitxml=evidence/AOS-016.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

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
