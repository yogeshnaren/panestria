# AOS-005 — Minimal goal/approval API and CLI end-to-end synthetic slice: implementation plan

**Release:** R0. **Format:** full; shared design supplies cross-component detail. **Implementation:** S1 routes, S2 locked decisions, and S3 synthetic journey observed; the item awaits review. **Tests:** AOS-005-TC01 through TC04 observed on disposable PostgreSQL. G0 stays incomplete because AOS-001-TC04 remains NOT_RUN. **Depends on:** AOS-003, AOS-004. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](../design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](../design/02-DATABASE-AND-MIGRATIONS.md), [security](../design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](../design/04-API-AND-USER-FLOWS.md), [decisions](../design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](../testing/TEST_EXECUTION.md) and [source spec](../specification/specs/AOS-005.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

A user can submit a synthetic goal, observe authoritative progress, review exact evidence, approve or deny a bound action, and recover across server restart.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/api/auth.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/api/routes/goals.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/api/routes/approvals.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/api/routes/events.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/api/routes/artifacts.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/cli/goals.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/cli/approvals.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/kernel/approvals.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `ApprovalService.decide(actor, approval_id, effect_digest, expected_version, decision) -> DecisionReceipt`
- `GoalQueries.get(actor, goal_id) -> GoalView`
- `EventRepository.after(actor, goal_id, seq, limit) -> EventPage`
- `ArtifactService.read(actor, artifact_id) -> VerifiedArtifact`

**Migration ownership:** Approval decision/consumption/idempotency and local session metadata; explicit scoped synthetic owner/project seed.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-005-F01 | FastAPI endpoints `/v1/goals`, `/v1/goals/{id}`, `/v1/goals/{id}/events`, `/v1/artifacts/{id}`, `/v1/approvals`, `/v1/approvals/{id}/decision`, `/v1/goals/{id}/cancel`, plus loopback-only health. | AOS-005-S1, AOS-005-S2, AOS-005-S3; owning files/interfaces above | AOS-005-TC01, AOS-005-TC02, AOS-005-TC03, AOS-005-TC04; parameterize every condition in this clause |
| AOS-005-F02 | CLI: `agentos goal submit --contract path.yaml`, `goal status`, `goal events`, `approve <id>`, `deny <id>`, `artifact show`, `goal cancel`, `r0-demo`. CLI accepts explicit goal id and prints artifact hashes and check verdicts, never hidden approvals. | AOS-005-S1, AOS-005-S2, AOS-005-S3; owning files/interfaces above | AOS-005-TC01, AOS-005-TC02, AOS-005-TC03, AOS-005-TC04; parameterize every condition in this clause |
| AOS-005-F03 | Approval binds exact action kind, effect_digest, owner/project, policy version and expiration. Deduplicate decisions; rejected/expired approvals do not execute. The approval UI is terminal-first for R0; web can be a read-only minimal view. | AOS-005-S1, AOS-005-S2, AOS-005-S3; owning files/interfaces above | AOS-005-TC01, AOS-005-TC02, AOS-005-TC03, AOS-005-TC04; parameterize every condition in this clause |
| AOS-005-F04 | Persist event cursors for replay; HTTP local auth must be sufficient to prevent arbitrary local processes and browser-origin attacks, hardened further by AOS-009 before real access. | AOS-005-S1, AOS-005-S2, AOS-005-S3; owning files/interfaces above | AOS-005-TC01, AOS-005-TC02, AOS-005-TC03, AOS-005-TC04; parameterize every condition in this clause |
| AOS-005-AC01 | A fresh environment runs `make r0-demo`; CLI creates goal, shows RUNNING, returns verifier result, requests approval, and moves to COMPLETED only after approved synthetic action. | AOS-005-S1, AOS-005-S2, AOS-005-S3; owning files/interfaces above | AOS-005-TC01, AOS-005-TC02, AOS-005-TC03, AOS-005-TC04; parameterize every condition in this clause |
| AOS-005-AC02 | Kill API before approval, restart, decide once: exact action executes once in mock; altered effect_digest/expired request denied. Wrong project/owner/task linkage fails the database constraints and service guards; an unauthorized minimum actor cannot decide or consume the request. | AOS-005-S1, AOS-005-S2, AOS-005-S3; owning files/interfaces above | AOS-005-TC01, AOS-005-TC02, AOS-005-TC03, AOS-005-TC04; parameterize every condition in this clause |
| AOS-005-AC03 | HTTP from unauthorized origin and wrong Host denied in basic test; AOS-009 later completes browser/DNS rebinding adversarial matrix. | AOS-005-S1, AOS-005-S2, AOS-005-S3; owning files/interfaces above | AOS-005-TC01, AOS-005-TC02, AOS-005-TC03, AOS-005-TC04; parameterize every condition in this clause |
| AOS-005-AC04 | CLI sees correct state after reconnect, including canonical event cursor and artifact SHA256. | AOS-005-S1, AOS-005-S2, AOS-005-S3; owning files/interfaces above | AOS-005-TC01, AOS-005-TC02, AOS-005-TC03, AOS-005-TC04; parameterize every condition in this clause |
| AOS-005-IF01 | Canonical JSON errors `{code,message,correlation_id,retryable}`. | `src/panestria/api/auth.py` | AOS-005-TC02 generates a fresh correlation id and does not copy one from the request. |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-005-S1](../cursor/prompts/AOS-005-S1.md) | AOS-003, AOS-004 | Minimal authenticated loopback routes and schema-derived CLI; safe errors/body limits/scoped reads and typed replay. | AOS-005-TC01; command/report/exit, immutable evidence and diff |
| [AOS-005-S2](../cursor/prompts/AOS-005-S2.md) | AOS-005-S1 | Immutable action preview/digest, locked approve/deny/expire decisions and continuation_kind contract-vs-merge waits. | AOS-005-TC02; command/report/exit, immutable evidence and diff |
| [AOS-005-S3](../cursor/prompts/AOS-005-S3.md) | AOS-005-S2 | Full R0 journey through contract consent, mock candidate, independent evidence and approved synthetic CAS effect; restart/deny/stale paths. | AOS-005-TC01, AOS-005-TC02, AOS-005-TC03, AOS-005-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-005-TC01 | e2e | `tests/e2e/test_aos_005.py::test_r0_positive_journey` | CLI submits and consents, observes task/evidence, approves exact candidate and sees completed synthetic goal after confirmed effect. |
| AOS-005-TC02 | security | `tests/e2e/test_aos_005.py::test_approval_digest_actor_expiry` | Wrong actor/project/digest, expired request or changed payload cannot dispatch effect; unknown check prevents completion. API denials include a generated correlation id and do not copy one from the request. |
| AOS-005-TC03 | integration | `tests/e2e/test_aos_005.py::test_decision_race_idempotency` | Approve/deny and duplicate consume races yield one decision/effect; repeated key with changed body conflicts. |
| AOS-005-TC04 | chaos | `tests/e2e/test_aos_005.py::test_wait_restart_continuation` | Restart at contract wait dispatches only after consent; restart at merge wait resumes finalize, does not launch another worker. A denied approval closes the goal as CANCELLED and starts no worker. The latest approval request wins over an older decision. When the API process is down, the CLI exits nonzero with a retryable error and does not print success. |

After tests exist, baseline command is `uv run --frozen pytest tests/e2e/test_aos_005.py --junitxml=evidence/AOS-005.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

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
## Decision versus dispatch

The POST decision handler locks/scopes the current request and records one exact digest/actor/expiry verdict/event. A separate durable continuation rechecks evidence/policy and consumes it into one effect intent. UI retries return the same receipt, not duplicate work. Test contract-consent wait and merge wait separately with continuation_kind. Cancellation can stop admissions immediately while an in-flight effect remains UNKNOWN; terminal state cannot be invented.
