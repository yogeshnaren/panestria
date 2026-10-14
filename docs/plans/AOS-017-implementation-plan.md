# AOS-017 — Offline Ask and source-scoped memory interaction: implementation plan

**Release:** R1. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-011, AOS-016. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](../design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](../design/02-DATABASE-AND-MIGRATIONS.md), [security](../design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](../design/04-API-AND-USER-FLOWS.md), [decisions](../design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](../testing/TEST_EXECUTION.md) and [source spec](../specification/specs/AOS-017.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

A user can quickly ask the primary local AI offline and retrieve previously approved project memory without leaking information across scopes.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/api/routes/ask.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/cli/ask.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/memory/context.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/memory/search.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/kernel/ask.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `AskService.respond(actor, request) -> AsyncIterator[AskEvent]`
- `ContextCompiler.compose(actor, contract, memories, token_budget) -> ContextPack`
- `AskResult.provenance() -> SourceLinks`

**Migration ownership:** Scoped Ask request/idempotency/context/provenance refs; raw text retention opt-in.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-017-F01 | Build CLI `agentos ask` and thin HTTP API; classify request, select local model, retrieve memory using owner/project filters and compile small context pack with source refs and untrusted-content wrapping. | AOS-017-S1, AOS-017-S2, AOS-017-S3; owning files/interfaces above | AOS-017-TC01, AOS-017-TC02, AOS-017-TC03, AOS-017-TC04; parameterize every condition in this clause |
| AOS-017-F02 | No internet or subscription required to boot or answer; user sees cold-start/unavailable errors and provenance when memory used. Provide optional lightweight web Ask input if interface scaffold exists; not a frontend gate. | AOS-017-S1, AOS-017-S2, AOS-017-S3; owning files/interfaces above | AOS-017-TC01, AOS-017-TC02, AOS-017-TC03, AOS-017-TC04; parameterize every condition in this clause |
| AOS-017-F03 | Use deterministic intent bounds and timeouts; avoid prompt-only privacy decisions. Store only consented content, with corrections captured separately from responses. | AOS-017-S1, AOS-017-S2, AOS-017-S3; owning files/interfaces above | AOS-017-TC01, AOS-017-TC02, AOS-017-TC03, AOS-017-TC04; parameterize every condition in this clause |
| AOS-017-AC01 | A-1: 10 fixed queries offline including 3 project-memory recalls and malicious 'enable cloud' prompt; no observed/accessible outbound inference. | AOS-017-S1, AOS-017-S2, AOS-017-S3; owning files/interfaces above | AOS-017-TC01, AOS-017-TC02, AOS-017-TC03, AOS-017-TC04; parameterize every condition in this clause |
| AOS-017-AC02 | Latency distribution measured on actual hardware; provisional warm p95 TTFT ≤3 s only if hardware ADR confirms feasibility. | AOS-017-S1, AOS-017-S2, AOS-017-S3; owning files/interfaces above | AOS-017-TC01, AOS-017-TC02, AOS-017-TC03, AOS-017-TC04; parameterize every condition in this clause |
| AOS-017-AC03 | Different project memory never retrieved; missing local model returns actionable error, not unauthorized cloud response. | AOS-017-S1, AOS-017-S2, AOS-017-S3; owning files/interfaces above | AOS-017-TC01, AOS-017-TC02, AOS-017-TC03, AOS-017-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-017-S1](../cursor/prompts/AOS-017-S1.md) | AOS-011, AOS-016 | Local-only Ask handler/CLI with project/label bounds, FTS recall and context source hashes. | AOS-017-TC01; command/report/exit, immutable evidence and diff |
| [AOS-017-S2](../cursor/prompts/AOS-017-S2.md) | AOS-017-S1 | Streaming terminal status/timeout/degraded UI and separate explicit correction/memory write path. | AOS-017-TC02; command/report/exit, immutable evidence and diff |
| [AOS-017-S3](../cursor/prompts/AOS-017-S3.md) | AOS-017-S2 | A-1 ten-prompt source/scope/no-cloud fixtures and actual network-disabled quality/latency measurements. | AOS-017-TC01, AOS-017-TC02, AOS-017-TC03, AOS-017-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-017-TC01 | integration | `tests/integration/test_aos_017.py::test_ten_prompt_ask_fixture` | Ten fixed queries include three source-linked recalls and hostile enable-cloud; correct scope/provenance and terminal status. |
| AOS-017-TC02 | security | `tests/integration/test_aos_017.py::test_memory_and_prompt_scope` | Another project's memory and untrusted enable-route instructions cannot enter pack or change local-only policy. |
| AOS-017-TC03 | chaos | `tests/integration/test_aos_017.py::test_missing_model_midstream` | Missing/unloaded model or interrupted stream returns safe degraded/error without fabricated answer or completion. |
| AOS-017-TC04 | live | `tests/integration/test_aos_017.py::test_a1_network_disabled` | Actual local Ask works with public egress disabled; warm latency target locked by hardware ADR, not silently waived. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_017.py --junitxml=evidence/AOS-017.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

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
