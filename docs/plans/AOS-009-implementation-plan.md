# AOS-009 — Loopback API authentication, host/origin hardening and approvals: implementation plan

**Release:** R1. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-005, AOS-007. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](../design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](../design/02-DATABASE-AND-MIGRATIONS.md), [security](../design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](../design/04-API-AND-USER-FLOWS.md), [decisions](../design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](../testing/TEST_EXECUTION.md) and [source spec](../specification/specs/AOS-009.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

Even local browser pages or untrusted network content cannot submit AgentOS actions, invoke approvals or hijack a localhost API.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/api/auth.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/api/sessions.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/api/csrf.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/api/middleware.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/kernel/approvals.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `ActorResolver.resolve(request) -> ActorContext`
- `BrowserSessionService.pair(local_code, origin) -> SessionReceipt`
- `MutationGuard.validate(request, actor, csrf) -> GuardContext`
- `ApprovalService.consume(uow, approval_id, intent) -> ExistingEffect|NewEffect`

**Migration ownership:** Local token/session/pairing metadata, auth revocation and approval consumed binding; secret values stored outside untrusted workspaces.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-009-F01 | Enforce loopback bind, allowlisted Host, trusted Origin, session auth, anti-CSRF on mutations, no wildcard CORS and browser security headers. Detect DNS rebinding via Host validation and trusted origin checks. | AOS-009-S1, AOS-009-S2, AOS-009-S3; owning files/interfaces above | AOS-009-TC01, AOS-009-TC02, AOS-009-TC03, AOS-009-TC04; parameterize every condition in this clause |
| AOS-009-F02 | Approval is exact `(owner, project, task, effect_hash, action, policy_version, expiry)` and single-consumption. Mutating operation checks policy again on execution; approve button never executes a different payload. | AOS-009-S1, AOS-009-S2, AOS-009-S3; owning files/interfaces above | AOS-009-TC01, AOS-009-TC02, AOS-009-TC03, AOS-009-TC04; parameterize every condition in this clause |
| AOS-009-F03 | Rate-limit endpoints and cap body sizes; API content-type/schema validation; prevent cached sensitive artifact responses. Implement non-browser CLI auth without bypassing owner identity. | AOS-009-S1, AOS-009-S2, AOS-009-S3; owning files/interfaces above | AOS-009-TC01, AOS-009-TC02, AOS-009-TC03, AOS-009-TC04; parameterize every condition in this clause |
| AOS-009-F04 | Do not expose remotely except user-configured Tailscale/SSH binding with explicit stronger auth and threat review. | AOS-009-S1, AOS-009-S2, AOS-009-S3; owning files/interfaces above | AOS-009-TC01, AOS-009-TC02, AOS-009-TC03, AOS-009-TC04; parameterize every condition in this clause |
| AOS-009-AC01 | Foreign origin POST, wrong Host, DNS rebinding host, expired and duplicate approval denied. | AOS-009-S1, AOS-009-S2, AOS-009-S3; owning files/interfaces above | AOS-009-TC01, AOS-009-TC02, AOS-009-TC03, AOS-009-TC04; parameterize every condition in this clause |
| AOS-009-AC02 | Contract mutation after approval invalidates old digest; race approving/rejecting has one final result. | AOS-009-S1, AOS-009-S2, AOS-009-S3; owning files/interfaces above | AOS-009-TC01, AOS-009-TC02, AOS-009-TC03, AOS-009-TC04; parameterize every condition in this clause |
| AOS-009-AC03 | Authorized local CLI unaffected; referrer/CSRF bypass tests and websocket/SSE origin cases covered. | AOS-009-S1, AOS-009-S2, AOS-009-S3; owning files/interfaces above | AOS-009-TC01, AOS-009-TC02, AOS-009-TC03, AOS-009-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-009-S1](../cursor/prompts/AOS-009-S1.md) | AOS-005, AOS-007 | CLI token/actor storage and exact Host/Origin/body/media/rate middleware; safe same-origin API semantics. | AOS-009-TC01; command/report/exit, immutable evidence and diff |
| [AOS-009-S2](../cursor/prompts/AOS-009-S2.md) | AOS-009-S1 | One-use pairing, scoped cookie/session/CSRF and expiry/revoke; no URL tokens or wildcard CORS. | AOS-009-TC02; command/report/exit, immutable evidence and diff |
| [AOS-009-S3](../cursor/prompts/AOS-009-S3.md) | AOS-009-S2 | Actual browser/cookie/SSE and stale-decision races with bounded failure/error audit. | AOS-009-TC01, AOS-009-TC02, AOS-009-TC03, AOS-009-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-009-TC01 | security | `tests/integration/test_aos_009.py::test_origin_host_csrf_matrix` | Wrong Host/Origin, forged mutation, missing browser CSRF and expired sessions denied; authenticated CLI missing Origin remains correctly scoped. |
| AOS-009-TC02 | security | `tests/integration/test_aos_009.py::test_pairing_and_secret_redaction` | One-time code rate/expiry/reuse enforced; tokens and pairing content absent from URLs/logs/events. |
| AOS-009-TC03 | integration | `tests/integration/test_aos_009.py::test_approval_decision_consumption_races` | Changed contract/candidate/policy/actor invalidates digest; one approved effect consumed under races. |
| AOS-009-TC04 | e2e | `tests/integration/test_aos_009.py::test_browser_session_revocation` | Revoke session prevents SSE reconnect/artifact access and mutation; UI clears private view without inventing task completion. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_009.py --junitxml=evidence/AOS-009.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

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
