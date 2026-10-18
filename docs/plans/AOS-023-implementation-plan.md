# AOS-023 — Bounded Delegate planner, research brief output and R2 gate: implementation plan

**Release:** R2. **Format:** full; shared design supplies cross-component detail. **Implementation:** IN_PROGRESS (retained-evidence inspection component only). **Tests:** component checks; full item NOT_RUN. **Depends on:** AOS-019, AOS-020, AOS-021, AOS-022. **Repository baseline:** original main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; current continuation starts at 94ab5c103456f188608e9cd2d53255c33bd8f586.

Read [architecture](../design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](../design/02-DATABASE-AND-MIGRATIONS.md), [security](../design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](../design/04-API-AND-USER-FLOWS.md), [decisions](../design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](../testing/TEST_EXECUTION.md) and [source spec](../specification/specs/AOS-023.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

A user can delegate a specific public-web research brief, inspect evidence and limitations, and obtain deterministic security guarantees around source retrieval.

Current partial delivery: [offline retained-evidence brief](../design/51-RETAINED-EVIDENCE-BRIEF.md)
and [owner command](../testing/RETAINED_EVIDENCE_BRIEF.md) connect existing
request/source/claim records without new egress or semantic authority. S1
admission/new-request execution and the rest of S2 remain pending. Dependency
gates/original clauses are unchanged; exporting does not admit citation/rubric
acceptance runners or complete the item.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/research/delegate.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/api/routes/research.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/cli/delegate.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/research/claims.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `DelegateService.submit(actor, request, idempotency_key) -> ResearchReceipt`
- `ResearchPlanner.propose(question, limits) -> BoundedQueries`
- `ResearchOrchestrator.run(request_ref) -> EvidenceBrief`

**Migration ownership:** Research task/goal linkage and bounded request/result artifact refs with immutable evidence manifest.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-023-F01 | Ask/Delegate/Build API routes remain distinct; R2 Delegate accepts a bounded question, allowed search providers, per-task fetch/latency/budget constraints and permitted topic data classes. | AOS-023-S1, AOS-023-S2, AOS-023-S3; owning files/interfaces above | AOS-023-TC01, AOS-023-TC02, AOS-023-TC03, AOS-023-TC04; parameterize every condition in this clause |
| AOS-023-F02 | Planner breaks request into ≤N research subqueries, calls approved search provider, fetcher and isolated reader; synthesizer constructs structured claim and source list; all factual claims go through source/quote and semantic support pipeline. | AOS-023-S1, AOS-023-S2, AOS-023-S3; owning files/interfaces above | AOS-023-TC01, AOS-023-TC02, AOS-023-TC03, AOS-023-TC04; parameterize every condition in this clause |
| AOS-023-F03 | Result includes objective question summary, evidence-backed claims, links/source snapshot IDs, uncertainty/contradictions, retrieval errors and fact-check results. Explicitly reject authenticated/private browsing and executable site instructions. | AOS-023-S1, AOS-023-S2, AOS-023-S3; owning files/interfaces above | AOS-023-TC01, AOS-023-TC02, AOS-023-TC03, AOS-023-TC04; parameterize every condition in this clause |
| AOS-023-F04 | R2 security gates include SSRF, DNS rebinding, prompt-injection reader/actor split and provider search disclosure logging. | AOS-023-S1, AOS-023-S2, AOS-023-S3; owning files/interfaces above | AOS-023-TC01, AOS-023-TC02, AOS-023-TC03, AOS-023-TC04; parameterize every condition in this clause |
| AOS-023-AC01 | D-1: ≥5 fixture briefs including fabricated quote, fabricated URL, claim contradiction, injection and SSRF attempt. All negative fixtures explicitly fail/abstain. | AOS-023-S1, AOS-023-S2, AOS-023-S3; owning files/interfaces above | AOS-023-TC01, AOS-023-TC02, AOS-023-TC03, AOS-023-TC04; parameterize every condition in this clause |
| AOS-023-AC02 | One authorized live public-web brief completes and every displayed citation resolves to retained successfully fetched source. | AOS-023-S1, AOS-023-S2, AOS-023-S3; owning files/interfaces above | AOS-023-TC01, AOS-023-TC02, AOS-023-TC03, AOS-023-TC04; parameterize every condition in this clause |
| AOS-023-AC03 | Network-disabled Ask still operates unchanged; no delegated task can open user secrets or call shell actor. | AOS-023-S1, AOS-023-S2, AOS-023-S3; owning files/interfaces above | AOS-023-TC01, AOS-023-TC02, AOS-023-TC03, AOS-023-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-023-S1](../cursor/prompts/AOS-023-S1.md) | AOS-019, AOS-020, AOS-021, AOS-022 | Distinct Delegate request/admission with configured provider/consent and strict subquery/source/byte/time/budget bounds. | AOS-023-TC01; command/report/exit, immutable evidence and diff |
| [AOS-023-S2](../cursor/prompts/AOS-023-S2.md) | AOS-023-S1 | Fetch→read→claim→cite→support pipeline with complete errors/truncation/uncertainty and deterministic offline fixture mode. | AOS-023-TC02; command/report/exit, immutable evidence and diff |
| [AOS-023-S3](../cursor/prompts/AOS-023-S3.md) | AOS-023-S2 | D-1 adversarial briefs and separately authorized live public brief; disable Delegate without changing offline Ask/Build. | AOS-023-TC01, AOS-023-TC02, AOS-023-TC03, AOS-023-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-023-TC01 | e2e | `tests/e2e/test_aos_023.py::test_d1_fixture_briefs` | Five briefs cover fake URL/quote, contradiction, injection and SSRF; negatives fail/abstain explicitly. |
| AOS-023-TC02 | security | `tests/e2e/test_aos_023.py::test_delegate_scope_and_budgets` | Private authenticated browsing/shell/secret access denied; subqueries/sources/deadlines/paid caps cannot grow from model text. |
| AOS-023-TC03 | integration | `tests/e2e/test_aos_023.py::test_ask_build_independence` | Delegate disabled/search down does not break Ask or Build and no silent provider fallback occurs. |
| AOS-023-TC04 | live | `tests/e2e/test_aos_023.py::test_live_public_evidenced_brief` | Authorized question completes with every citation retained/resolvable, query disclosure and support/error labels. |

After tests exist, baseline command is `uv run --frozen pytest tests/e2e/test_aos_023.py --junitxml=evidence/AOS-023.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

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
