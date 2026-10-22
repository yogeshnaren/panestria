# AOS-017 — Offline Ask and source-scoped memory interaction: implementation plan

**Release:** R1. **Format:** full; shared design supplies cross-component detail. **Implementation:** IN_PROGRESS (supported offline Ask and operator surfaces). **Tests:** component/source-bound evidence; full item NOT_RUN. **Depends on:** AOS-011, AOS-016. **Repository baseline:** original main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; terminal usability continuation starts at cfe09d0463af039b50fb52eab51920037df3a19f.

Read [architecture](../design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](../design/02-DATABASE-AND-MIGRATIONS.md), [security](../design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](../design/04-API-AND-USER-FLOWS.md), [decisions](../design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](../testing/TEST_EXECUTION.md) and [source spec](../specification/specs/AOS-017.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

The first-run continuation removes manual UUID/JSON assembly: explicit
`local init --offline-ask` writes private stable settings and uses the existing
scoped setup transaction, with resumable database errors and no overwrite,
automatic installation or service launch. See [setup](../testing/LOCAL_ASK_SETUP.md).
This is usability work within the current Ask surface; it does not complete the
remaining S2 memory-write surface, full A-1 or cumulative G1.

A user can quickly ask the primary local AI offline and retrieve previously approved project memory without leaking information across scopes.

The owner requested a usable terminal application before GUI expansion. The
[Ask TUI](../design/57-LOCAL-ASK-TUI.md) extends S2 with keyboard question/answer,
actual scope/status, canonical receipt/cancel and transient literal rendering.
It uses the supported local server; it does not install/start services, provide
Build/research screens, replace React/phone clauses or pass the full item/gate.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/api/routes/ask.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/cli/ask.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/memory/context.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/memory/search.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/kernel/ask.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `AskService.respond(actor, request) -> AsyncIterator[AskEvent]`
- `ContextCompiler.compose(actor, contract, memories, token_budget) -> ContextPack`
- `AskResult.provenance() -> SourceLinks`

**Migration ownership:** Scoped Ask request/idempotency/context/provenance refs; raw text retention opt-in.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-017-F01 | Build CLI `agentos ask` and thin HTTP API; classify request, select local model, retrieve memory using owner/project filters and compile small context pack with source refs and untrusted-content wrapping. | AOS-017-S1, AOS-017-S2, AOS-017-S3; owning files/interfaces above | AOS-017-TC01, AOS-017-TC02, AOS-017-TC03, AOS-017-TC04; parameterize every condition in this clause |
| AOS-017-F02 | No internet or subscription required to boot or answer; user sees cold-start/unavailable errors and provenance when memory used. Provide optional lightweight web Ask input if interface scaffold exists; not a frontend gate. | AOS-017-S1, AOS-017-S2, AOS-017-S3; owning files/interfaces above | AOS-017-TC01, AOS-017-TC02, AOS-017-TC03, AOS-017-TC04; parameterize every condition in this clause |
| AOS-017-F03 | Use deterministic intent bounds and timeouts; avoid prompt-only privacy decisions. Store only consented content, with corrections captured separately from responses. | AOS-017-S1, AOS-017-S2, AOS-017-S3; owning files/interfaces above | AOS-017-TC01, AOS-017-TC02, AOS-017-TC03, AOS-017-TC04; parameterize every condition in this clause |
| AOS-017-AC01 | A-1: 10 fixed queries offline including 3 project-memory recalls and malicious 'enable cloud' prompt; no observed/accessible outbound inference. | AOS-017-S1, AOS-017-S2, AOS-017-S3; owning files/interfaces above | AOS-017-TC01, AOS-017-TC02, AOS-017-TC03, AOS-017-TC04; parameterize every condition in this clause |
| AOS-017-AC02 | Latency distribution measured on actual hardware; provisional warm p95 TTFT ≤3 s only if hardware ADR confirms feasibility. | AOS-017-S1, AOS-017-S2, AOS-017-S3; owning files/interfaces above | AOS-017-TC01, AOS-017-TC02, AOS-017-TC03, AOS-017-TC04; parameterize every condition in this clause |
| AOS-017-AC03 | Different project memory never retrieved; missing local model returns actionable error, not unauthorized cloud response. | AOS-017-S1, AOS-017-S2, AOS-017-S3; owning files/interfaces above | AOS-017-TC01, AOS-017-TC02, AOS-017-TC03, AOS-017-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-017-S1](../cursor/prompts/AOS-017-S1.md) | AOS-011, AOS-016 | Local-only Ask handler/CLI with project/label bounds, FTS recall and context source hashes. | AOS-017-TC01; command/report/exit, immutable evidence and diff |
| [AOS-017-S2](../cursor/prompts/AOS-017-S2.md) | AOS-017-S1 | Streaming terminal status/timeout/degraded UI and separate explicit correction/memory write path. | AOS-017-TC02; command/report/exit, immutable evidence and diff |
| [AOS-017-S3](../cursor/prompts/AOS-017-S3.md) | AOS-017-S2 | A-1 ten-prompt source/scope/no-cloud fixtures and actual network-disabled quality/latency measurements. | AOS-017-TC01, AOS-017-TC02, AOS-017-TC03, AOS-017-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-017-TC01 | integration | `tests/integration/test_aos_017.py::test_ten_prompt_ask_fixture` | Ten fixed queries include three source-linked recalls and hostile enable-cloud; correct scope/provenance and terminal status. |
| AOS-017-TC02 | security | `tests/integration/test_aos_017.py::test_memory_and_prompt_scope` | Another project's memory and untrusted enable-route instructions cannot enter pack or change local-only policy. |
| AOS-017-TC03 | chaos | `tests/integration/test_aos_017.py::test_missing_model_midstream` | Missing/unloaded model or interrupted stream returns safe degraded/error without fabricated answer or completion. |
| AOS-017-TC04 | live | `tests/integration/test_aos_017.py::test_a1_network_disabled` | Actual local Ask works with public egress disabled; warm latency target locked by hardware ADR, not silently waived. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_017.py --junitxml=evidence/AOS-017.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

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

## Revision 3 extension — MVP-X08, delivered in R3

The [active personal-platform contract](../specification/architecture/05-PERSONAL-PLATFORM-REVISION-3.md#mvp-x08) adds **Portable assistant charter, communication style and model context**. Original parent scope and historical results remain intact. These new slices deliver in **R3**, even when the parent AOS item originally ships in R1; they do not reopen historical G0 acceptance or fabricate G1 evidence. Inspect the current repository before choosing exact new files/migration revisions.

| Slice | Concrete outcome, narrowed to about one developer-day | Prerequisites |
| --- | --- | --- |
| AOS-017-S4 | Implement the minimal editable owner charter/style contract with profile provenance. | AOS-011-S6, AOS-017-S3 |
| AOS-017-S5 | Implement local presentation constraints and paired factual-retention/style checks. | AOS-017-S4 |
| AOS-017-S6 | Add portable context/model compatibility metadata and pinned-attempt replacement fixtures. | AOS-017-S5, AOS-024-S3 |

Use the [revision-3 slice handoff](../cursor/prompts/MVP-REV3-SLICE.md) with the selected manifest entry. File ownership candidates are in implementation-slices.json; record an ADR for a material change. Existing shared transaction/security/API requirements still apply.

| Added case | Lane | Required passing behavior |
| --- | --- | --- |
| AOS-017-TC05 | contract | Editable owner-approved behavior/style preferences preserve honesty, uncertainty and permissions; style settings cannot widen authority or establish psychological facts. |
| AOS-017-TC06 | integration | Paired style fixtures preserve facts, numbers and citations while recording readability, owner preference, output length and latency; unsafe rewrites abstain. |
| AOS-017-TC07 | contract | Versioned application-owned memory/style/model manifests reject incompatible tokenizers/templates/tools; active attempts remain pinned and replacement rollback preserves data. |
| AOS-017-TC08 | security | Private profile/examples stay local; cross-harness export requires explicit permitted context and retains provenance/labels; consumer clients do not silently share chats or memory. |

These nodes and scenarios are planned, not observed tests. Register real assertion/node/lane/evidence mappings while implementing; missing required evidence blocks G3. Rollout begins disabled, uses synthetic content until its boundary is certified, stops admissions on failure and preserves audit/receipts. R4-R7 work is not authorized by completing this extension.

## Current R3 extension component: encrypted structured style

[Design61](../design/61-STRUCTURED-LOCAL-STYLE.md) connects an explicitly selected
StyleProfile/charter renderer to the existing encrypted approved-field profile
Ask path. Renderer2 binds ciphertext/source/request/policy and preserves legacy
renderer1; migration0032 refuses loss of populated v2 audit. [Component evidence](../../evidence/structured-profile-style-2026-10-18/report.json)
includes actual crypto/PG/local CPU smoke with synthetic test keys, not qualified
style fidelity, owner preference or a current OS-key-backend/release certificate.
S4 remains IN_PROGRESS; private example refs, supported sensitive-mode onboarding, S5's paired
presentation evaluation and S6's portable model manifests/replacement remain
pending. No owner database/key/service was configured by this task.

The [explicit style terminal](../testing/PROFILE_STYLE_TERMINAL.md) now edits
structured preferences and separate local-context approval through an existing
qualified/enabled owner API. It preserves other fields/expiry, requires exact
version and a separate save review, and never retries an ambiguous write.
Default launchers remain unchanged; actual owner onboarding/key qualification,
full S4/S5/S6 evidence remain pending.

The [shared local charter](../testing/SHARED_LOCAL_CHARTER.md) setting now connects
ordinary and profile Ask through the existing data-free rules and pinned general
context packs. The private overlay remains separately approved/local and includes
the charter once. Actual PG/crypto/config/HTTP checks preserve old/new prepared
bytes across setting changes; model/process/key/capacity are explicit fixtures.
This is a usable S4/context component, not completed S5 quality or S6 model
compatibility/replacement. Private example references and full original evidence
remain open; no owner profile/configuration or qualification was changed.

[Lossless local presentation](../testing/LOSSLESS_LOCAL_PRESENTATION.md) now offers
an opt-in supported layout pass after exact profile revalidation. Plain paragraph
bullet markers must invert to all original bytes; unsafe/partial structure
abstains. Timing/length/content counts are saved without profile values or content
hashes, with factual/readability/preference judgments explicitly NOT_ASSESSED.
Actual paired/PG/crypto/HTTP observations use declared model/key/capacity fixtures.
This is partial S5 delivery; no semantic rewrite, full quality qualification,
ModelManifest compatibility or original case/gate is marked complete.

The [pinned CPU model manifest](../testing/PINNED_LOCAL_MODEL_MANIFEST.md) now
connects opt-in raw-text local Ask startup, immutable context metadata, claim,
provider dispatch/publication and receipts. Compatibility refusal/rollback leaves
original context and memory intact; the tokenizer is identified only by its GGUF
container, evaluation remains NOT_EVALUATED. Source-bound component evidence and
one actual cached CPU/PG/Unix-socket/ASGI journey cover this supported path. This
is partial S6, not general model replacement, other-mode qualification, full
TC07/TC08 or G3. No default, owner service/configuration or model cache was changed.

The [Build JSON pin extension](../testing/LOCAL_BUILD_MODEL_PINS.md) now snapshots
an explicitly selected public manifest before plan/repair request and durable
intent preparation. Actual startup/format/result must match; canonical repair
replay keeps the original identity after new-work settings change. The owner
export command reads existing authenticated Ask status without inference or
qualification refresh. This extends partial S6 to the supported Build drafts;
query/synthesis/GPU/general replacement and full original evidence remain open.

The [research extension](../testing/LOCAL_RESEARCH_MODEL_PINS.md) now binds local
query/synthesis intents and retained outputs to that same optional CPU JSON
identity. Current-file-independent replay/inspection and omitted legacy None
fields preserve history. Actual PG/CAS/reader component checks and one separate
actual cached CPU synthesis observation cover this path; HTTPS/request state were
explicit fixtures and semantic support remains NOT_ASSESSED. Supported CPU local
paths now retain model identity, but general replacement/compatibility, GPU,
paired quality/owner preference and full original gates/trial remain open.

The [pinned profile Ask terminal](../testing/PROFILE_ASK_TERMINAL.md) now connects
explicit row/field/purpose selection to the existing restricted local inference
boundary, with cancellation and content-free receipt recovery. Real key/model
qualification, supported service/onboarding and full original cases remain open.

The [private-example extension](../testing/PRIVATE_STYLE_EXAMPLES.md) now stores
a bounded owner-reviewed set inside the encrypted communication snapshot and
compiles it only into the explicitly selected offline overlay. Ciphertext/version
refs retain provenance; no public private-text fingerprint or training grant is
introduced. Actual PG/crypto/HTTP/PTY and one cached CPU smoke are source-bound
components. Full style/owner preference, broader cross-harness TC08 and original
release evidence remain pending; historical results above stay unchanged.
