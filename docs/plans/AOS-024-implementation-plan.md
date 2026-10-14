# AOS-024 — Codex supported CLI adapter and contract suite: implementation plan

**Release:** R3. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-004, AOS-008, AOS-010. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](../design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](../design/02-DATABASE-AND-MIGRATIONS.md), [security](../design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](../design/04-API-AND-USER-FLOWS.md), [decisions](../design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](../testing/TEST_EXECUTION.md) and [source spec](../specification/specs/AOS-024.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

A second approved vendor harness can perform bounded work under exactly the same AgentOS worker contract and sandbox permissions as the first.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/brokers/harness/codex.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/brokers/harness/event_parser.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/brokers/harness/process_runner.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/sandbox/native_tool_gateway.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `CodexAdapter.validate/start/events/observe/cancel/collect(job)`
- `CodexCompatibilityProbe.inspect(binary, profile, auth_handle) -> Manifest`

**Migration ownership:** Second adapter version/auth-mode/profile/consent metadata, normalized vendor receipt/thread refs; no consumer credential brokerage.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-024-F01 | Implement Codex CLI adapter using officially supported headless/JSON interface and signed-in user's own permitted account. Do not handle consumer credentials directly or pool accounts; background usage requires express consent if applicable. | AOS-024-S1, AOS-024-S2, AOS-024-S3; owning files/interfaces above | AOS-024-TC01, AOS-024-TC02, AOS-024-TC03, AOS-024-TC04; parameterize every condition in this clause |
| AOS-024-F02 | Pin binary/protocol version; validate auth status using supported commands, protect config state from repo files, constrain execution worktree and tool permissions; never inherit arbitrary unattended approvals. | AOS-024-S1, AOS-024-S2, AOS-024-S3; owning files/interfaces above | AOS-024-TC01, AOS-024-TC02, AOS-024-TC03, AOS-024-TC04; parameterize every condition in this clause |
| AOS-024-F03 | Map Codex events/errors/usage to common schema; differentiate auth-required, 429, failure, structured output parse failure, no native resume and uncertain process effects. | AOS-024-S1, AOS-024-S2, AOS-024-S3; owning files/interfaces above | AOS-024-TC01, AOS-024-TC02, AOS-024-TC03, AOS-024-TC04; parameterize every condition in this clause |
| AOS-024-F04 | Adapter testing uses recorded sanitized synthetic events plus live optional smoke tests only on a synthetic repo under user consent. | AOS-024-S1, AOS-024-S2, AOS-024-S3; owning files/interfaces above | AOS-024-TC01, AOS-024-TC02, AOS-024-TC03, AOS-024-TC04; parameterize every condition in this clause |
| AOS-024-AC01 | Synthetic Codex JSON fixture parses to normalized events; corrupted stream and unknown field fail safely. | AOS-024-S1, AOS-024-S2, AOS-024-S3; owning files/interfaces above | AOS-024-TC01, AOS-024-TC02, AOS-024-TC03, AOS-024-TC04; parameterize every condition in this clause |
| AOS-024-AC02 | Malicious repo config cannot widen worktree or command scope. Cancellation, timeout, unauthorized auth and 429 yield correct states. | AOS-024-S1, AOS-024-S2, AOS-024-S3; owning files/interfaces above | AOS-024-TC01, AOS-024-TC02, AOS-024-TC03, AOS-024-TC04; parameterize every condition in this clause |
| AOS-024-AC03 | Parallel adapter test verifies no Claude-specific fields leak into kernel API. | AOS-024-S1, AOS-024-S2, AOS-024-S3; owning files/interfaces above | AOS-024-TC01, AOS-024-TC02, AOS-024-TC03, AOS-024-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-024-S1](../cursor/prompts/AOS-024-S1.md) | AOS-004, AOS-008, AOS-010 | Current supported exec/JSONL/login-status interface pinned and mapped with sanitized fixture protocol; no model/kernel field coupling. | AOS-024-TC01; command/report/exit, immutable evidence and diff |
| [AOS-024-S2](../cursor/prompts/AOS-024-S2.md) | AOS-024-S1 | Scoped config/workspace/native+OS permissions and bounded process/credential-tool isolation; no untested resume or approval bypass. | AOS-024-TC02; command/report/exit, immutable evidence and diff |
| [AOS-024-S3](../cursor/prompts/AOS-024-S3.md) | AOS-024-S2 | Hostile repo/cancel/auth/quota/truncation fixtures plus consented synthetic live adapter parity evidence. | AOS-024-TC01, AOS-024-TC02, AOS-024-TC03, AOS-024-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-024-TC01 | contract | `tests/integration/test_aos_024.py::test_codex_normalized_stream` | Success/error/auth/quota/item/turn events normalize; unknown/truncated state data refuses unsafe transition, no Claude-specific public fields. |
| AOS-024-TC02 | security | `tests/integration/test_aos_024.py::test_codex_repo_config_permissions` | Repo config/AGENTS/MCP cannot widen sandbox, read credentials or protected parent refs; native/outer limits measured. |
| AOS-024-TC03 | chaos | `tests/integration/test_aos_024.py::test_codex_cancel_start_loss` | Silent timeout/child process cancellation and lost start receipt accurately reconciled; no automatic native resume. |
| AOS-024-TC04 | live | `tests/integration/test_aos_024.py::test_codex_live_adapter_parity` | Exact owner-authenticated binary/profile runs synthetic task under same protocol; required features/auth mode tested, not inferred from docs. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_024.py --junitxml=evidence/AOS-024.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

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
