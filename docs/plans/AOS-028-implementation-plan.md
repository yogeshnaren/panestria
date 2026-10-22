# AOS-028 — React Mission Control task views, approvals and event replay: implementation plan

**Release:** R3. **Format:** full; shared design supplies cross-component detail. **Implementation:** IN_PROGRESS (backend/terminal component). **Tests:** component checks PASS; original release scenarios NOT_RUN. **Depends on:** AOS-005, AOS-014, AOS-017, AOS-023, AOS-027b. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](../design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](../design/02-DATABASE-AND-MIGRATIONS.md), [security](../design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](../design/04-API-AND-USER-FLOWS.md), [decisions](../design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](../testing/TEST_EXECUTION.md) and [source spec](../specification/specs/AOS-028.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

A locally served dashboard shows Ask, Delegate and Build intake, real task state, source evidence, worker fleet and exact pending approvals without creating a second state machine.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/api/openapi_export.py` — owning implementation file; reconcile existing code before creating it.
- `apps/mission-control/src/api/client.ts` — owning implementation file; reconcile existing code before creating it.
- `apps/mission-control/src/hooks/useTaskEvents.ts` — owning implementation file; reconcile existing code before creating it.
- `apps/mission-control/src/views/Intake.tsx` — owning implementation file; reconcile existing code before creating it.
- `apps/mission-control/src/views/GoalDetail.tsx` — owning implementation file; reconcile existing code before creating it.
- `apps/mission-control/src/views/Approvals.tsx` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `GeneratedOpenAPIClient request/response enums`
- `useTaskEvents(goalId, initialCursor) -> CanonicalViewState`
- `ApprovalPreviewView.submit(current_effect_digest, decision) -> Pending|Receipt`

**Migration ownership:** No new authoritative UI state tables; use kernel API/DB and existing sessions.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-028-F01 | React/Vite typed client generated from OpenAPI; goal/task list and detail, event timeline, approval inbox, artifact/diff/test evidence and three distinct inputs. Focus keyboard/accessible minimal workflows before graphs. | AOS-028-S1, AOS-028-S2, AOS-028-S3; owning files/interfaces above | AOS-028-TC01, AOS-028-TC02, AOS-028-TC03, AOS-028-TC04; parameterize every condition in this clause |
| AOS-028-F02 | SSE with event cursors, reconnect/backfill and idempotent reducer; reconcile with canonical API after reconnect. Handle unknown/RECONCILING/approval states explicitly, never optimistic display of COMPLETED. | AOS-028-S1, AOS-028-S2, AOS-028-S3; owning files/interfaces above | AOS-028-TC01, AOS-028-TC02, AOS-028-TC03, AOS-028-TC04; parameterize every condition in this clause |
| AOS-028-F03 | Host/origin/CSRF and local authorization integrated with AOS-009; hide Restricted content from unauthorized client context; safe markdown/source rendering and no executable HTML. | AOS-028-S1, AOS-028-S2, AOS-028-S3; owning files/interfaces above | AOS-028-TC01, AOS-028-TC02, AOS-028-TC03, AOS-028-TC04; parameterize every condition in this clause |
| AOS-028-F04 | Optional trace links to Phoenix and display accessible vs observed egress, unknown usage not $0. | AOS-028-S1, AOS-028-S2, AOS-028-S3; owning files/interfaces above | AOS-028-TC01, AOS-028-TC02, AOS-028-TC03, AOS-028-TC04; parameterize every condition in this clause |
| AOS-028-AC01 | Browser reconnect midway through workflow shows all events exactly once in UI. | AOS-028-S1, AOS-028-S2, AOS-028-S3; owning files/interfaces above | AOS-028-TC01, AOS-028-TC02, AOS-028-TC03, AOS-028-TC04; parameterize every condition in this clause |
| AOS-028-AC02 | Approval preview mismatch or stale digest blocks submission; task remains pending on network errors. | AOS-028-S1, AOS-028-S2, AOS-028-S3; owning files/interfaces above | AOS-028-TC01, AOS-028-TC02, AOS-028-TC03, AOS-028-TC04; parameterize every condition in this clause |
| AOS-028-AC03 | Keyboard navigation/contrast and no secret content in URL/logs; cross-origin mutation denied. | AOS-028-S1, AOS-028-S2, AOS-028-S3; owning files/interfaces above | AOS-028-TC01, AOS-028-TC02, AOS-028-TC03, AOS-028-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-028-S1](../cursor/prompts/AOS-028-S1.md) | AOS-005, AOS-014, AOS-017, AOS-023, AOS-027b | React/TypeScript/Vite same-origin shell, generated API types and accessible Ask/Delegate/Build intake with authoritative snapshot views. | AOS-028-TC01; command/report/exit, immutable evidence and diff |
| [AOS-028-S2](../cursor/prompts/AOS-028-S2.md) | AOS-028-S1 | Task/fleet/timeline/evidence/approval UI and decimal-cursor SSE reducer with bounded reconnect/retention resync. IN_PROGRESS: protected progress, PUBLIC exact review/consent, offline Ask and PUBLIC Delegate staging inputs delivered; Build intake, full inbox/dispatch, qualified Delegate execution and item qualification remain. | AOS-028-TC02; command/report/exit, immutable evidence and diff; [Ask guide](../testing/MISSION_OFFLINE_ASK.md), [Delegate staging](../testing/MISSION_RESEARCH_INTAKE.md) and source-bound evidence |
| [AOS-028-S3](../cursor/prompts/AOS-028-S3.md) | AOS-028-S2 | Synthetic browser E2E for stale approvals/errors/auth/redaction/markdown/keyboard and operator UX evidence. | AOS-028-TC01, AOS-028-TC02, AOS-028-TC03, AOS-028-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-028-TC01 | e2e | `tests/e2e/test_aos_028.py::test_ui_reconnect_authoritative` | Mid-run reconnect restores every unique event and final snapshot; >2^53 cursor exact; UI cannot invent completed state. |
| AOS-028-TC02 | security | `tests/e2e/test_aos_028.py::test_ui_approval_auth_markdown` | Stale digest prevents submit; expired session clears private view; active HTML/dangerous links and foreign origin mutation rejected. |
| AOS-028-TC03 | e2e | `tests/e2e/test_aos_028.py::test_three_intakes_and_failures` | Ask/Delegate/Build each has usable input/status/evidence; pending/error/UNKNOWN/refusal shown accurately. |
| AOS-028-TC04 | e2e | `tests/e2e/test_aos_028.py::test_keyboard_focus_evidence_preview` | Keyboard/focus/contrast and exact action evidence preview allow owner decision; no secret content in URLs/logs. |

After tests exist, baseline command is `uv run --frozen pytest tests/e2e/test_aos_028.py --junitxml=evidence/AOS-028.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

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

## Revision 3 extension — MVP-X12, delivered in R3

The [active personal-platform contract](../specification/architecture/05-PERSONAL-PLATFORM-REVISION-3.md#mvp-x12) adds **Private read-only phone companion**. Original parent scope and historical results remain intact. These new slices deliver in **R3**, even when the parent AOS item originally ships in R1; they do not reopen historical G0 acceptance or fabricate G1 evidence. Inspect the current repository before choosing exact new files/migration revisions.

| Slice | Concrete outcome, narrowed to about one developer-day | Prerequisites |
| --- | --- | --- |
| AOS-028-S4 | Implement explicit private TLS/device/read-only scope behind a disabled-by-default ingress profile. | AOS-009-S3, AOS-008-S5, AOS-028-S3 |
| AOS-028-S5 | Implement responsive status/attention views and safe cache/staleness behavior. | AOS-028-S4, AOS-029-S3 |
| AOS-028-S6 | Complete adversarial device/reconnect checks and separately scoped real-phone qualification. | AOS-028-S5 |

Use the [revision-3 slice handoff](../cursor/prompts/MVP-REV3-SLICE.md) with the selected manifest entry. File ownership candidates are in implementation-slices.json; record an ADR for a material change. Existing shared transaction/security/API requirements still apply.

| Added case | Lane | Required passing behavior |
| --- | --- | --- |
| AOS-028-TC05 | security | Explicit device pairing/revocation, application authentication, TLS private ingress and exact Host/Origin checks deny replayed or untrusted devices; loopback API remains the default. |
| AOS-028-TC06 | e2e | Responsive phone views show authorized task/worker/evidence status and a minimal attention inbox with last-seen/stale/offline states. |
| AOS-028-TC07 | security | Read-only device sessions cannot submit jobs, approve merges, write data, change grants or export restricted profiles; unauthorized artifacts and sensitive service-worker caches are denied. |
| AOS-028-TC08 | live | Actual owner-selected phone/browser/private-network deployment demonstrates reconnect, revocation, offline workstation behavior and truthful status without requiring public ingress or claiming background push. |

These nodes and scenarios are planned, not observed tests. Register real assertion/node/lane/evidence mappings while implementing; missing required evidence blocks G3. Rollout begins disabled, uses synthetic content until its boundary is certified, stops admissions on failure and preserves audit/receipts. R4-R7 work is not authorized by completing this extension.

## Observed backend/terminal component, 2026-10-21

The owner prioritizes TUI workflows before GUI work. The [project overview](../design/75-PROJECT-ACTIVITY-TERMINAL.md) supplies canonical, content-free actor/project snapshots and a standalone model-free loopback terminal. It uses actual Ask and goal tables; no shadow task state or approval authority. [35 connected checks](../../evidence/project-activity-2026-10-21/report.json) exercise real PG/HTTP/CLI/PTY and explicit inference fixtures. S1 is partial; React/generated clients/intake, SSE replay, timeline/artifact/approval integration, original browser cases and phone/device qualification remain pending. No release case is marked passed by these new tests.
