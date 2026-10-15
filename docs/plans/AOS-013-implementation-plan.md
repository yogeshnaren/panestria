# AOS-013 — Research source snapshots, hashes, passage spans and claim evidence: implementation plan

**Release:** R2. **Format:** full; shared design supplies cross-component detail. **Implementation:** IN_PROGRESS (data contracts only). **Tests:** 42 contract checks PASS; full item cases NOT_RUN. **Depends on:** AOS-002, AOS-008. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](../design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](../design/02-DATABASE-AND-MIGRATIONS.md), [security](../design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](../design/04-API-AND-USER-FLOWS.md), [decisions](../design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](../testing/TEST_EXECUTION.md) and [source spec](../specification/specs/AOS-013.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

Current narrow task implements [closed research data contracts](../design/17-RESEARCH-SOURCE-CONTRACTS.md). Pydantic validation does not establish actual fetch, artifact integrity, byte-boundary, verifier or source authority. Schema and reader/broker/resolver work remain pending; no full AOS-013 case is promoted by the contract suite.

A research claim is traceable to an actual retained and fetched source, with exact text offset and source content hash, not just a URL in generated prose.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/contracts/research.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/research/sources.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/research/extract.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/research/claims.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/kernel/repositories/research.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `SourceStore.commit_fetch(actor, receipt, raw_blob, text_blob) -> SnapshotRef`
- `PassageResolver.resolve(snapshot_ref, start_offset, end_offset) -> VerifiedPassage`
- `ClaimStore.attach_evidence(actor, claim_ref, passages) -> ClaimEvidence`

**Migration ownership:** Next additive revision after current 0022; historical prospective label `0005_research`: research_request/source_snapshot/claim/claim_passage/verification_report; raw/text hashes, extraction/offset versions and scope.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-013-F01 | Schema `research_source_snapshot` includes request URL, verified terminal URL, redirects, timestamp, status, type, byte limit, SHA-256 raw fetch hash, normalized text hash, extractor version, privacy class and encrypted/protected store key. | AOS-013-S1, AOS-013-S2, AOS-013-S3; owning files/interfaces above | AOS-013-TC01, AOS-013-TC02, AOS-013-TC03, AOS-013-TC04; parameterize every condition in this clause |
| AOS-013-F02 | Retain source text with stable UTF-8 offsets and extractor-specific mapping to original bytes where possible; passages referenced as `(source_id,start,end,normalization_version)`. | AOS-013-S1, AOS-013-S2, AOS-013-S3; owning files/interfaces above | AOS-013-TC01, AOS-013-TC02, AOS-013-TC03, AOS-013-TC04; parameterize every condition in this clause |
| AOS-013-F03 | `claim_evidence` stores claim text/hash, one-to-many source passage refs, quote-match status, support verdict, conflict set and source-fetch errors. | AOS-013-S1, AOS-013-S2, AOS-013-S3; owning files/interfaces above | AOS-013-TC01, AOS-013-TC02, AOS-013-TC03, AOS-013-TC04; parameterize every condition in this clause |
| AOS-013-F04 | Canonical source IDs only minted by trusted reader, not model text; static corpus fixtures for redirects, corrupted/truncated content, table extraction ambiguity. | AOS-013-S1, AOS-013-S2, AOS-013-S3; owning files/interfaces above | AOS-013-TC01, AOS-013-TC02, AOS-013-TC03, AOS-013-TC04; parameterize every condition in this clause |
| AOS-013-AC01 | Invalid source ID, missing passage, offset outside snapshot, changed source body, and fabricated URL all rejected. | AOS-013-S1, AOS-013-S2, AOS-013-S3; owning files/interfaces above | AOS-013-TC01, AOS-013-TC02, AOS-013-TC03, AOS-013-TC04; parameterize every condition in this clause |
| AOS-013-AC02 | Exact-quote fixture passes only when normalization recorded; page with truncated table marked insufficient, not invented. | AOS-013-S1, AOS-013-S2, AOS-013-S3; owning files/interfaces above | AOS-013-TC01, AOS-013-TC02, AOS-013-TC03, AOS-013-TC04; parameterize every condition in this clause |
| AOS-013-AC03 | Fetch records immutable; claim verdict references explicit extractor version and source hash. | AOS-013-S1, AOS-013-S2, AOS-013-S3; owning files/interfaces above | AOS-013-TC01, AOS-013-TC02, AOS-013-TC03, AOS-013-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-013-S1](../cursor/prompts/AOS-013-S1.md) | AOS-002, AOS-008 | Immutable source/claim/Pydantic schema and Alembic metadata, protected raw/text artifact refs. | AOS-013-TC01; command/report/exit, immutable evidence and diff |
| [AOS-013-S2](../cursor/prompts/AOS-013-S2.md) | AOS-013-S1 | Canonical NFC UTF-8 text and half-open byte passage offsets; explicit charset/truncation/version semantics. | AOS-013-TC02; command/report/exit, immutable evidence and diff |
| [AOS-013-S3](../cursor/prompts/AOS-013-S3.md) | AOS-013-S2 | Hash/source/scope/offset fabrication fixtures and offline stored-evidence reconstruction. | AOS-013-TC01, AOS-013-TC02, AOS-013-TC03, AOS-013-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-013-TC01 | migration | `tests/integration/test_aos_013.py::test_research_scope_integrity` | Wrong project/goal/source/claim linkage fails; immutable fetch rows cannot silently overwrite extractor version. |
| AOS-013-TC02 | contract | `tests/integration/test_aos_013.py::test_utf8_offsets_hashes` | Non-ASCII passage offsets validate byte boundaries; out-of-range/split character/hash mismatch rejected. |
| AOS-013-TC03 | security | `tests/integration/test_aos_013.py::test_fabricated_source_reference` | Model-generated URL/ID without broker-retained successful fetch cannot pass evidence resolution. |
| AOS-013-TC04 | integration | `tests/integration/test_aos_013.py::test_snapshot_versions_truncation` | Changed body/re-extraction creates new snapshot; truncated content stays incomplete and never invents missing table text. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_013.py --junitxml=evidence/AOS-013.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

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
