# AOS-025 — Build task DAG and bounded LangGraph reasoning/replan: implementation plan

**Release:** R3. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-003, AOS-016. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](../design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](../design/02-DATABASE-AND-MIGRATIONS.md), [security](../design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](../design/04-API-AND-USER-FLOWS.md), [decisions](../design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](../testing/TEST_EXECUTION.md) and [source spec](../specification/specs/AOS-025.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

A user intent is converted into an executable acyclic work plan with dependencies, acceptance checks and conservative bounded replanning.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/contracts/plan.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/kernel/plans.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/execution/build_plan.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/memory/context.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `PlanProposalService.propose(actor, contract, inventory) -> PlanProposal`
- `PlanValidator.validate(proposal, contract, capability_manifest) -> ValidatedDAG`
- `Supervisor.replan(actor, failure_ref, expected_plan_version) -> PlanRevision`

**Migration ownership:** 0006_plans_fleet: plan_version/plan_task_link and task DAG metadata; parent hash/version and bounded revisions.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-025-F01 | Planner consumes immutable goal contract, project inventory and capabilities, produces typed DAG with task IDs, required worker/tools, expected artifact/check and dependency edges. Enforce bounded task count, depth and budget before admission. | AOS-025-S1, AOS-025-S2, AOS-025-S3; owning files/interfaces above | AOS-025-TC01, AOS-025-TC02, AOS-025-TC03, AOS-025-TC04; parameterize every condition in this clause |
| AOS-025-F02 | Use direct structured local/model call first, optionally a small LangGraph plan-review-revise subgraph where actual cycles justify it. LangGraph checkpoint never becomes authoritative task state. | AOS-025-S1, AOS-025-S2, AOS-025-S3; owning files/interfaces above | AOS-025-TC01, AOS-025-TC02, AOS-025-TC03, AOS-025-TC04; parameterize every condition in this clause |
| AOS-025-F03 | On verifier failure, propose a new plan version with reasoning and explicit approval if contract scope, privacy or cost changes. Long-running agents end milestones with a handoff and clean artifacts; prohibit recursive infinite replanning. | AOS-025-S1, AOS-025-S2, AOS-025-S3; owning files/interfaces above | AOS-025-TC01, AOS-025-TC02, AOS-025-TC03, AOS-025-TC04; parameterize every condition in this clause |
| AOS-025-AC01 | Planner output with cycles, missing acceptance checks or unapproved capability rejected. | AOS-025-S1, AOS-025-S2, AOS-025-S3; owning files/interfaces above | AOS-025-TC01, AOS-025-TC02, AOS-025-TC03, AOS-025-TC04; parameterize every condition in this clause |
| AOS-025-AC02 | Bounded replan terminates after configured attempts; changing contract scope needs new approved version. | AOS-025-S1, AOS-025-S2, AOS-025-S3; owning files/interfaces above | AOS-025-TC01, AOS-025-TC02, AOS-025-TC03, AOS-025-TC04; parameterize every condition in this clause |
| AOS-025-AC03 | A simple synthetic one-task plan works without LangGraph; graph mode yields equivalent task contract with traceable decisions. | AOS-025-S1, AOS-025-S2, AOS-025-S3; owning files/interfaces above | AOS-025-TC01, AOS-025-TC02, AOS-025-TC03, AOS-025-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-025-S1](../cursor/prompts/AOS-025-S1.md) | AOS-003, AOS-016 | Typed bounded plan schema and deterministic DAG/capability/scope/budget validator with synthetic proposal fixtures. | AOS-025-TC01; command/report/exit, immutable evidence and diff |
| [AOS-025-S2](../cursor/prompts/AOS-025-S2.md) | AOS-025-S1 | Direct structured local inference proposal and milestone handoff context; kernel commits approved plan/task refs only. | AOS-025-TC02; command/report/exit, immutable evidence and diff |
| [AOS-025-S3](../cursor/prompts/AOS-025-S3.md) | AOS-025-S2 | Bounded repair/replan and optional small LangGraph interface parity; scope/cost/privacy changes require new contract consent. | AOS-025-TC01, AOS-025-TC02, AOS-025-TC03, AOS-025-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-025-TC01 | contract | `tests/integration/test_aos_025.py::test_dag_cycle_scope_budget` | Cycle/self-edge/missing check/unavailable worker/unapproved capability/too many nodes or aggregate overbudget rejected. |
| AOS-025-TC02 | integration | `tests/integration/test_aos_025.py::test_plan_version_and_handoff` | Validated plan versions persist immutable parent/hash; milestone output and fresh context preserve evidence and exact contract scope. |
| AOS-025-TC03 | security | `tests/integration/test_aos_025.py::test_replan_cannot_expand_authority` | Injected README/model proposal cannot widen privacy/paths/budget; contract change requires new version/consent. |
| AOS-025-TC04 | integration | `tests/integration/test_aos_025.py::test_bounded_replan_direct_graph` | Configured max replan terminates; direct one-task works without graph runtime; enabled graph yields same authoritative DAG contract. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_025.py --junitxml=evidence/AOS-025.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

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
