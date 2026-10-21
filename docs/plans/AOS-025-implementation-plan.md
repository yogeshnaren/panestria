# AOS-025 — Build task DAG and bounded LangGraph reasoning/replan: implementation plan

**Release:** R3. **Format:** full; shared design supplies cross-component detail. **Implementation:** IN_PROGRESS (S1 proposal preflight delivered). **Tests:** component PASS; full item NOT_RUN. **Depends on:** AOS-003, AOS-016. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](../design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](../design/02-DATABASE-AND-MIGRATIONS.md), [security](../design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](../design/04-API-AND-USER-FLOWS.md), [decisions](../design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](../testing/TEST_EXECUTION.md) and [source spec](../specification/specs/AOS-025.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

A user intent is converted into an executable acyclic work plan with dependencies, acceptance checks and conservative bounded replanning.

[Bounded proposal preflight](../design/60-BOUNDED-BUILD-DAG.md) delivers S1's typed
schema and deterministic scope/capability/graph/retry-budget validator with a
private-file CLI. [Observed component evidence](../../evidence/build-plan-preflight-2026-10-18/report.json)
is pure/fixture-only. S2/S3, current certified inventory, canonical plan/task
persistence, two-worker dispatch and full TC01/G3 remain pending.

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

## Revision 3 extension — MVP-X10, delivered in R3

The [active personal-platform contract](../specification/architecture/05-PERSONAL-PLATFORM-REVISION-3.md#mvp-x10) adds **Verified milestones, stall detection and bounded repair**. Original parent scope and historical results remain intact. These new slices deliver in **R3**, even when the parent AOS item originally ships in R1; they do not reopen historical G0 acceptance or fabricate G1 evidence. Inspect the current repository before choosing exact new files/migration revisions.

| Slice | Concrete outcome, narrowed to about one developer-day | Prerequisites |
| --- | --- | --- |
| AOS-025-S4 | Add requirement/evidence milestones, finite repair accounting and honest stall status. | AOS-025-S3, AOS-027b-S3 |
| AOS-025-S5 | Verify restart/handoff, adversarial false-done and authority-preserving repair. | AOS-025-S4 |

Use the [revision-3 slice handoff](../cursor/prompts/MVP-REV3-SLICE.md) with the selected manifest entry. File ownership candidates are in implementation-slices.json; record an ADR for a material change. Existing shared transaction/security/API requirements still apply.

| Added case | Lane | Required passing behavior |
| --- | --- | --- |
| AOS-025-TC05 | integration | Every original requirement/non-goal maps to candidate-bound evidence; false completion, missing checks or a worker-edited trusted test bundle cannot complete a goal. |
| AOS-025-TC06 | integration | Heartbeat is separate from verified progress; repeated failures/unchanged candidates expose a stall and finite repair budget rather than a silent infinite loop. |
| AOS-025-TC07 | chaos | Restart and fresh-session handoff preserve plan/evidence/model identity and reconcile ambiguous external effects before repetition. |
| AOS-025-TC08 | security | Replans cannot enlarge scope, privacy, cost or tool authority without corresponding authorization; final approval binds the integrated candidate and evidence. |

These nodes and scenarios are planned, not observed tests. Register real assertion/node/lane/evidence mappings while implementing; missing required evidence blocks G3. Rollout begins disabled, uses synthetic content until its boundary is certified, stops admissions on failure and preserves audit/receipts. R4-R7 work is not authorized by completing this extension.

## Initial canonical storage component

The [version1 plan/handoff component](../testing/CANONICAL_BUILD_PLAN.md) uses
actual migration0033_canonical_plans (the early0006 migration label was
provisional). Immutable proposal/consent/task membership/handoff tables reference
the existing canonical task/attempt/contract stores and global task_event.
Owner acceptance creates CREATED nodes only. Actual adapter and declared worker
inventory are separate; runtime qualification stays NOT_ASSESSED.

S2 remains IN_PROGRESS: five controller PG/Git/CAS cases observe storage, consent,
rollback and verified-source binding at their recorded sources; direct structured
local proposal remains pending. S3 still supplies bounded revisions/repair.
No task/goal completion, automatic worker admission or full TC02/G3 is claimed.

## Direct local proposal component

[The local planner runbook](../testing/LOCAL_BUILD_PLANNER.md) and [boundary design](../design/64-LOCAL-BUILD-PROPOSALS.md) add an explicit one-call offline draft. The model proposes editing assignments; trusted code reserves the final verification budget and compiles all original checks/path coverage. The complete graph passes the existing scope/graph/budget validator before private publication. No database, acceptance, worker or merge effect occurs. The owner separately stages/reviews/accepts exact canonical references.

S2 remains IN_PROGRESS: the direct proposal and existing handoff/storage components now have source-bound observations, including an actual pinned CPU-model draft; general quality/qualified inventory/integration and full TC02 are not established by that example. Original failed model graph evidence remains preserved. S3 finite canonical revisions, recovery and X10 progress/repair accounting remain the next dependencies.

## Finite same-contract revision component

[The bounded revision runbook](../testing/BOUNDED_PLAN_REVISIONS.md) and [design66](../design/66-BOUNDED-PLAN-REVISIONS.md) implement a linear owner-reviewed family with two or three total versions, immutable parents, protected physical-return prerequisites and cumulative original-budget charging. A superseded plan cannot dispatch, cancel the current version or complete its goal. Revised exact merge completes only the current accepted graph while preserving old failures.

S3 is IN_PROGRESS, not complete: this PUBLIC/API0 same-contract path has source-bound real PG/Git/MCP/Docker observations with explicit native fixtures. Changed authority still requires new explicit authorization; automatic qualified model repair, full TC02/03/04, optional graph parity if introduced, and X10 progress/stall/restart coverage remain unfinished. No live check or release pass is inferred. S2's direct local draft is delivered separately; its broader planning-quality/qualified-inventory requirements remain.

## Initial X10 progress inspection

[Build progress](../testing/BUILD_PROGRESS.md) projects canonical contract/non-goal/plan versions and protected check/candidate/handoff references in a consistent repeatable-read snapshot, saved privately with SHA256. It separates activity, verified checks, exact owner merge and release acceptance. It exposes held/unknown work, finite wall/version accounting and repeated unchanged failed-tree fingerprints without granting retry or completion.

S4 is IN_PROGRESS: actual source-bound controller observations cover the initial view/export and stale/tampered/false-heartbeat/repeated-failure cases. Full semantic requirement/non-goal assessment, controller enforcement of repeated-failure policy, rubric/restart qualification and unified Mission Control remain pending; S5/full TC05-TC08/G3 are not complete.

## Canonical local repair draft component

[Local repair](../testing/LOCAL_BUILD_REPAIR.md) connects a current physically stopped PUBLIC plan, protected task/check failures, frozen contract/inventory and remaining cumulative envelope to one explicitly requested offline draft. Source changes, unknown work, exhausted budgets and repeated unchanged failed candidates stop this path. Separate existing canonical revision consent, execution and final exact merge remain required. [Evidence](../../evidence/local-build-repair-2026-10-21/report.json) includes real CLI/PG/Git/MCP/Docker and explicit model/native fixtures. S3/S4 remain IN_PROGRESS: real repair-quality qualification, automatic controller, general planning inventory and original scenarios remain unfinished.

## Durable repair turn accounting (partial S3/S4/S5)

[Canonical repair intents](../design/77-DURABLE-REPAIR-INTENTS.md) now reserve and
acknowledge model I/O before dispatch, bind private outputs for historical replay,
enforce a cumulative1–2 turn cap and charge360 seconds per intent against the
original goal budget. Unknown returns block another turn and canonical revision.
[Actual connected and backup/restore evidence](../../evidence/repair-draft-intents-2026-10-21/report.json)
uses explicit model/native fixtures. S3/S4/S5 stay IN_PROGRESS; broader planning,
repair quality, automatic controller and original full scenarios remain pending.
