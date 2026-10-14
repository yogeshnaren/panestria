# AOS-026 — Concurrent two-worker scheduler, worktree conflict control and admission: implementation plan

**Release:** R3. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-006, AOS-010, AOS-024, AOS-025. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](../design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](../design/02-DATABASE-AND-MIGRATIONS.md), [security](../design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](../design/04-API-AND-USER-FLOWS.md), [decisions](../design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](../testing/TEST_EXECUTION.md) and [source spec](../specification/specs/AOS-026.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

Two authorized workers execute independent plan steps concurrently without overwriting each other or exceeding CPU/GPU/provider/budget limits.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/kernel/scheduler.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/kernel/leases.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/kernel/budgets.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/resources/admission.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/execution/build_plan.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/verification/merge.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `Scheduler.claim_ready(actor, capacity) -> AttemptLease|Queued`
- `ResourceAdmission.reserve(uow, job, snapshot) -> Reservation`
- `BuildIntegrator.collect_fenced(attempts, base_sha) -> CandidateSet`

**Migration ownership:** Plan/fleet/reservation/candidate/common-ancestor metadata and ready-task indexes; scoped epoch and known cash constraints.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-026-F01 | Task DAG scheduler determines ready nodes, leases worker attempts with fencing epochs, admits only after effective trust/privacy/autonomy, quota, cost and resource constraints. | AOS-026-S1, AOS-026-S2, AOS-026-S3; owning files/interfaces above | AOS-026-TC01, AOS-026-TC02, AOS-026-TC03, AOS-026-TC04; parameterize every condition in this clause |
| AOS-026-F02 | Each worker receives isolated checked-out worktree branch; common ancestor tracked, diff hashes and merge-conflict checks done before integration. Limit WIP/concurrent harness processes; support queue priorities and urgent reserve without subscription quota abuse. | AOS-026-S1, AOS-026-S2, AOS-026-S3; owning files/interfaces above | AOS-026-TC01, AOS-026-TC02, AOS-026-TC03, AOS-026-TC04; parameterize every condition in this clause |
| AOS-026-F03 | On GPU/foreground pressure no new heavy workers admitted, current work deferred safely; mismatched provider plan entitlement never silently falls back to unapproved cloud. | AOS-026-S1, AOS-026-S2, AOS-026-S3; owning files/interfaces above | AOS-026-TC01, AOS-026-TC02, AOS-026-TC03, AOS-026-TC04; parameterize every condition in this clause |
| AOS-026-F04 | On a conflict, stop automatic merge and present verifier/owner with alternatives; do not allow agent A to overwrite B's artifacts. | AOS-026-S1, AOS-026-S2, AOS-026-S3; owning files/interfaces above | AOS-026-TC01, AOS-026-TC02, AOS-026-TC03, AOS-026-TC04; parameterize every condition in this clause |
| AOS-026-AC01 | Two workers modify disjoint files and pass tests; conflicting same-line edits stop before protected merge. | AOS-026-S1, AOS-026-S2, AOS-026-S3; owning files/interfaces above | AOS-026-TC01, AOS-026-TC02, AOS-026-TC03, AOS-026-TC04; parameterize every condition in this clause |
| AOS-026-AC02 | Concurrency cap enforced under 8 competing synthetic jobs; stale attempt cannot publish; failure of one does not falsely complete dependent tasks. | AOS-026-S1, AOS-026-S2, AOS-026-S3; owning files/interfaces above | AOS-026-TC01, AOS-026-TC02, AOS-026-TC03, AOS-026-TC04; parameterize every condition in this clause |
| AOS-026-AC03 | Quota unknown route receives conservative behavior and Restricted never cloud-falls-back. | AOS-026-S1, AOS-026-S2, AOS-026-S3; owning files/interfaces above | AOS-026-TC01, AOS-026-TC02, AOS-026-TC03, AOS-026-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-026-S1](../cursor/prompts/AOS-026-S1.md) | AOS-006, AOS-010, AOS-024, AOS-025 | Ready-node dependency query with atomic claim/epoch/resource/cash reservation and bounded priority ordering. | AOS-026-TC01; command/report/exit, immutable evidence and diff |
| [AOS-026-S2](../cursor/prompts/AOS-026-S2.md) | AOS-026-S1 | Two independent adapter/worktree orchestration with common-ancestor receipts; cancel/failure propagation and foreground no-new-admissions. | AOS-026-TC02; command/report/exit, immutable evidence and diff |
| [AOS-026-S3](../cursor/prompts/AOS-026-S3.md) | AOS-026-S2 | Eight-job concurrency stress, stale writes/dependency failure/unknown quota/conflict fixtures and actual two-worker footprint. | AOS-026-TC01, AOS-026-TC02, AOS-026-TC03, AOS-026-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-026-TC01 | integration | `tests/integration/test_aos_026.py::test_two_disjoint_workers` | Two allowed workers on disjoint files get separate leased workspaces/receipts without overriding results. |
| AOS-026-TC02 | integration | `tests/integration/test_aos_026.py::test_eight_jobs_capacity_budget` | Eight competing tasks never exceed cap; concurrent known-cash reservation cannot overspend; failed dependency never dispatched. |
| AOS-026-TC03 | security | `tests/integration/test_aos_026.py::test_stale_conflicting_results` | Stale epoch/cross-project result rejected; same-line overlap is conflict, no overwrite or automatic protected merge. |
| AOS-026-TC04 | live | `tests/integration/test_aos_026.py::test_two_worker_resource_limits` | Two certified live adapters respect actual configured host/process/foreground limits; unknown quota produces conservative behavior. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_026.py --junitxml=evidence/AOS-026.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

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
