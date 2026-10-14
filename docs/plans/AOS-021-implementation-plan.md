# AOS-021 — Deterministic source citation and exact quotation verifier: implementation plan

**Release:** R2. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-020. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](../design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](../design/02-DATABASE-AND-MIGRATIONS.md), [security](../design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](../design/04-API-AND-USER-FLOWS.md), [decisions](../design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](../testing/TEST_EXECUTION.md) and [source spec](../specification/specs/AOS-021.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

A research brief cannot mark a factual claim evidenced unless every cited source actually exists and quoted passages exactly match the retained source text under documented normalization.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/verification/citations.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/research/claims.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/cli/evidence.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `CitationVerifier.validate_refs(actor, claim, source_manifest) -> CitationResult`
- `QuoteVerifier.match(snapshot, byte_range, quote, normalization_version) -> QuoteResult`
- `EvidenceVerifier.verify_report(report_ref) -> DeterministicEvidenceReport`

**Migration ownership:** Quotation normalization/offset/hash/version/verdict metadata; never overwrite legacy evidence silently.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-021-F01 | Integrate candidate `verified-research-brief` skill after inspection. Parse brief into structured claims, citations, quotations and passage offsets; reject source IDs not minted from retained fetches. | AOS-021-S1, AOS-021-S2, AOS-021-S3; owning files/interfaces above | AOS-021-TC01, AOS-021-TC02, AOS-021-TC03, AOS-021-TC04; parameterize every condition in this clause |
| AOS-021-F02 | Exact quote normalization policy must specify Unicode NFKC or NFC choice, whitespace collapsing, HTML entity handling, punctuation and case behavior; retain both original and normalized snippets, and never normalize away substantive edits. | AOS-021-S1, AOS-021-S2, AOS-021-S3; owning files/interfaces above | AOS-021-TC01, AOS-021-TC02, AOS-021-TC03, AOS-021-TC04; parameterize every condition in this clause |
| AOS-021-F03 | Each claim uses real `source_id`, `start/end` and extractor version; offsets checked against source SHA. `SUPPORTED` requires subsequent AOS-022 semantic check; citation check alone yields `EVIDENCE_PRESENT`, not factual support. | AOS-021-S1, AOS-021-S2, AOS-021-S3; owning files/interfaces above | AOS-021-TC01, AOS-021-TC02, AOS-021-TC03, AOS-021-TC04; parameterize every condition in this clause |
| AOS-021-F04 | Deterministic verifier must operate without remote model and be rerunnable against immutable fixtures. | AOS-021-S1, AOS-021-S2, AOS-021-S3; owning files/interfaces above | AOS-021-TC01, AOS-021-TC02, AOS-021-TC03, AOS-021-TC04; parameterize every condition in this clause |
| AOS-021-AC01 | Pass exact quote with expected Unicode/whitespace normalization; reject fabricated quotation, out-of-range passage, URL-only citation and hash mismatch. | AOS-021-S1, AOS-021-S2, AOS-021-S3; owning files/interfaces above | AOS-021-TC01, AOS-021-TC02, AOS-021-TC03, AOS-021-TC04; parameterize every condition in this clause |
| AOS-021-AC02 | Claim with real source but unrelated passage passes source/quote check only and remains awaiting support review. | AOS-021-S1, AOS-021-S2, AOS-021-S3; owning files/interfaces above | AOS-021-TC01, AOS-021-TC02, AOS-021-TC03, AOS-021-TC04; parameterize every condition in this clause |
| AOS-021-AC03 | Fixtures are deterministic across process restarts; re-extraction with new version records new mapping not silent overwrite. | AOS-021-S1, AOS-021-S2, AOS-021-S3; owning files/interfaces above | AOS-021-TC01, AOS-021-TC02, AOS-021-TC03, AOS-021-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-021-S1](../cursor/prompts/AOS-021-S1.md) | AOS-020 | Port inspected citation skill to canonical source hashes/byte offsets and typed claim manifests; reject legacy unsafe source IDs. | AOS-021-TC01; command/report/exit, immutable evidence and diff |
| [AOS-021-S2](../cursor/prompts/AOS-021-S2.md) | AOS-021-S1 | Case-sensitive NFC/whitespace quote matcher with source/text boundary verification and explicit diagnostics. | AOS-021-TC02; command/report/exit, immutable evidence and diff |
| [AOS-021-S3](../cursor/prompts/AOS-021-S3.md) | AOS-021-S2 | Offline rerunnable positive/fabrication/Unicode/laundering fixtures and CLI evidence report separate from support. | AOS-021-TC01, AOS-021-TC02, AOS-021-TC03, AOS-021-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-021-TC01 | contract | `tests/integration/test_aos_021.py::test_exact_quote_normalization` | Exact NFC/whitespace variants match; changed case/numbers/punctuation/substantive quote edit does not normalize away. |
| AOS-021-TC02 | security | `tests/integration/test_aos_021.py::test_fabricated_quote_url_offsets` | URL-only/fabricated source/out-of-range/split UTF-8/hash mismatch fail before semantic judging. |
| AOS-021-TC03 | integration | `tests/integration/test_aos_021.py::test_citation_not_support` | Real unrelated passage can show EVIDENCE_PRESENT but not SUPPORTED; no automatic factual pass. |
| AOS-021-TC04 | integration | `tests/integration/test_aos_021.py::test_offline_reproducibility` | Same immutable fixtures yield same results after restart; new extractor version needs new mapping. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_021.py --junitxml=evidence/AOS-021.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

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
