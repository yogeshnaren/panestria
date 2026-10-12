# Panestria — phased implementation plan, MVP through full target

**Date:** 2026-10-11. **Plan revision:** 2. **Source:** AgentOS v0.6.1 planning-fixes-1. **MVP boundary:** R3, explicitly confirmed by the owner. **Repository:** [yogeshnaren/panestria](https://github.com/yogeshnaren/panestria), public, main branch. **Historical baseline:** 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917 contained only README.md and the MIT LICENSE. **Live status:** AOS-001-S1 corrections await acceptance. AOS-001, R0, and MVP acceptance are not complete.

The delivery path is R0 → R1 → R2 → R3 → **owner MVP review and acceptance** → R4 → R5 → R6 → R7. Every original capability remains assigned to a phase or a named evidence-gated candidate. R1 and R2 are useful pilots; the complete MVP is accepted at R3. SOTA implementation requires a separate owner decision after MVP review.

This is the full phased roadmap and planning contract. Detailed implementation plans are produced one current-phase spec at a time against the actual repository; future phases keep scope, dependencies and acceptance gates without pretending their implementation details are already known.

## 1. Phase summary and stop point

| Phase | Track | User-visible milestone | Active specs | Promotion evidence |
|---|---|---|---|---|
| R0 | MVP | Durable synthetic kernel | AOS-001, AOS-002, AOS-003, AOS-004, AOS-005 | G0 |
| R1 | MVP | Personal alpha: offline Ask and one-worker Build | AOS-006, AOS-007, AOS-008, AOS-009, AOS-010, AOS-027a, AOS-011, AOS-012, AOS-014, AOS-015, AOS-016, AOS-017, AOS-018 | G1 |
| R2 | MVP | Research alpha: verified Delegate | AOS-013, AOS-019, AOS-020, AOS-021, AOS-022, AOS-023 | G2 |
| R3 | MVP | Complete MVP: two-worker Build and Mission Control | AOS-024, AOS-025, AOS-026, AOS-027b, AOS-028, AOS-029, AOS-030 | G3 |
| MVP REVIEW | Required checkpoint | Freeze a candidate, run the full suite and 14-day owner trial; accept or return to MVP fixes | AOS-030 and MVP checklist | Owner acceptance recorded; SOTA separately authorized |
| R4 | SOTA | SOTA: routing, quotas and compute | AOS-031, AOS-032, AOS-033 | G4 |
| R5 | SOTA | SOTA: context, memory and daily-use surfaces | AOS-034, AOS-035 | G5 |
| R6 | SOTA | SOTA: evaluated adaptation and capability discovery | AOS-036 | G6 |
| R7 | SOTA | SOTA: portability, multi-machine and public distribution | AOS-037 | G7 |

An item being documented or merged is not proof that a release gate passed. The [machine-readable tracker](phase-tracker.json) starts with NOT_STARTED items and NOT_RUN gates. The [MVP checklist](MVP_ACCEPTANCE_CHECKLIST.md) defines the completion evidence. The [coverage register](FULL_TARGET_COVERAGE.md) accounts for 35 baseline subsystem rows, 16 preservation pillars and their finer features.

## 2. Repository setup and planning rules

Use the `panestria` repository as the project home and retain AOS IDs as stable engineering references. The actual repository URL/default branch and complete commit tree have been inspected; recheck its HEAD before generating exact patches. See [repository baseline](REPOSITORY_BASELINE.json). The preserved source specs propose src/agentos/. The active [AOS-001 implementation plan](plans/AOS-001-implementation-plan.md) and [naming ADR](../adr/0001-namespace-panestria.md) use one panestria distribution and `src/panestria/`. The [older checklist](plans/AOS-001-checklist.md) is superseded and is not the execution plan. This namespace mapping does not modify the frozen source. The historical architecture remains unchanged. A repository name alone does not prove public package/CLI availability.

Proposed repository documentation layout:

```text
docs/specification/         repaired baseline, original archives, skills ZIP/checksums
docs/roadmap/               this phased plan, MVP checklist, coverage register
docs/decisions/             naming and implementation ADRs
plans/                     one current AOS checklist/full plan at a time
evidence/releases/         gate manifests, test reports, owner review records
tests/                     fixtures created with their implementation slices
src/<chosen-package>/      one distribution with enforced sub-package boundaries
```

1. Preserve the delivered frozen architecture, original spec archives and original skills ZIP with hashes. Keep revised spec provenance explicit.
2. Create GitHub milestones corresponding to R0–R7 and one issue per active AOS spec when repository setup is authorized; label MVP vs SOTA and not-started vs evidence-backed completion. This roadmap does not create remote issues or push commits.
3. Start with an AOS-001 checklist, then full plans for 002/003, a checklist for 004 and a full plan for 005. Planning templates and common requirements are included under specification/.
4. Target roughly one developer-day per tested implementation slice. Estimate against inspected code; split work that cannot fit. This is a granularity target, not a claim that one whole AOS item or phase takes one day.
5. Give schema, durability, sandbox, approvals, provider adapters and external-action changes full design/failure analysis. Use concise checklists for low-risk wiring and docs; preserve every applicable acceptance test.
6. Plan, implement and verify one slice; keep a working vertical path and end with evidence. Keep only the current phase's detailed plans active. Later release specs remain draft until their phase planning uses observed results.
7. Reuse the seven attached skills after inventory/migration; source inclusion is not installation or privilege. The observed 16 smoke checks/five simulated presets are prototype evidence; format validation and integration still need completion.
8. Security, owner/project scope, budgets, provenance, cancellation and recovery remain baseline work throughout MVP. Advanced optimization is later; baseline safety is never deferred to SOTA.

## 3. R0 — durable synthetic kernel (G0)

**Entry:** repository/source inventory and repaired contracts available. **Scope:** AOS-001–005. **Demonstration:** submit a synthetic goal, see a mock worker produce an isolated diff, independently verify it, approve the exact action and recover after restart.

Suggested slice order, each narrowed to approximately one developer-day when estimating:

| Slice | Parent | Concrete output and proving check |
|---|---|---|
| 0.1 | 001 | Inventory repo and skills hashes/frontmatter/scripts/licenses; record reuse, gaps and naming ADR |
| 0.2 | 001 | One Python distribution, lockfile and minimal health endpoint; clean dependency/bootstrap smoke |
| 0.3 | 001 | Import boundaries, CI and scoped PostgreSQL fixture; forbidden import fails CI and DB health succeeds |
| 0.4 | 002 | Typed immutable goal/acceptance contract with the canonical seven-value union; reject legacy aliases/raw command text |
| 0.5 | 002 | Migration, owner/project constraints, task states, row version, approval effect_digest and global ordered task_event cursor; constraint/concurrency fixtures |
| 0.6 | 003 | DBOS datasource session commits state/event/result in one PostgreSQL transaction; stable workflow identity and duplicate-submission test |
| 0.7 | 003 | Crash barriers before/after atomic commit and interrupted non-DB step; replay has no phantom completion or repeated transition/event |
| 0.8 | 004 | Synthetic worker/worktree lifecycle; success, bad path, hung process and crash fixtures |
| 0.9 | 004 | Trusted reference runner, independent diff checks and protected artifact hashes; false-done/corrupt-evidence fixtures fail |
| 0.10 | 005 | Minimal authenticated loopback API and CLI status/events/artifacts; scoped reads and replay |
| 0.11 | 005 | Exact approval/denial/expiry and end-to-end synthetic demo; restart while waiting preserves the same request |

These are sequencing candidates, not estimated calendar commitments. Build only the sub-packages needed for the current slice. R0 uses synthetic files and mocks. No live vendor accounts, arbitrary real-repo code or polished frontend is required.

**G0 exit:** reproducible fresh setup; schema/contract and concurrent-write tests; atomic state/event/replay proof; wrong paths, failed tests and stale approvals rejected; one synthetic end-to-end journey and backup/restore runbook. Review the evidence before widening to R1.

## 4. R1 — useful offline Ask and one-worker Build (G1)

**Entry:** G0 passes. **Scope:** 006–012, 014–018 and 027a. Two implementation lanes share contracts but can be worked sequentially by one developer.

- Hardened Build lane: 006 leases/effects → 007 independent trust/privacy/autonomy → 008 OS sandbox/egress → 009 loopback/approval hardening → 010 Claude Code adapter → 027a independent single-worker verification/merge approval.
- Ask/evidence lane: 011 source-linked memory and five-stage use events; 012 routing/corrections/exposure records; 014 tracing and ordered replay; 015 actual hardware probe; 016 local inference; 017 offline Ask; 018 offline/resource-pressure suite. Respect each spec's dependency edges, not just numeric order.

Start with synthetic hostile-repo fixtures before any consented personal-repo trial. Reconcile the attached goal-contract vocabulary, capture-learning stages and worker configuration. Benchmark the actual machine; simulated hardware output cannot choose a performance gate by itself.

**G1 exit:** A-1 ten-question network-disabled Ask including scoped recall; B-single actual pinned adapter compatibility and evidence-bound merge; hostile hooks/configs denied; axes varied independently; lost external-effect response reconciled; resource pressure preserves task state. Basic budget hard stops, context packs, provenance and retention controls remain included. CLI is sufficient here.

**Review milestone:** the owner can begin bounded daily use after G1 and its consent/safety boundaries pass. This is a personal alpha, not complete R3 MVP acceptance.

## 5. R2 — safe Delegate research (G2)

**Entry:** G1 passes. **Scope/order:** 013 immutable research schema → 019 search/fetch broker → 020 isolated reader → 021 source/citation/quote checks → 022 calibrated support/contradiction/uncertainty → 023 bounded Delegate workflow.

Configure a search backend explicitly and log queries as outbound disclosures. Bind citations to actual fetched snapshots and passage offsets. Separate deterministic source/quotation checks from semantic support judgments. The reader has no privileged actor tools. Keep authentication cookies and private mounts out of the public-web reader.

**G2 exit:** D-1 fixtures reject fabricated sources, wrong quotations and unsupported conclusions; prompt injection cannot invoke privileged actions; private IP/redirect/DNS-rebinding denial; size/time/truncation errors visible; one explicitly authorized live public brief with provenance and uncertainty. Ask/Build still work when Delegate is disabled.

**Review milestone:** the owner now has Ask + Delegate + single-worker Build. Review usefulness and approval burden; carry defects into MVP work rather than expanding SOTA scope.

## 6. R3 — complete MVP functionality and evidence (G3)

**Entry:** G2 passes. **Scope/order:** 024 Codex adapter → 025 bounded plan/DAG → 026 concurrent two-worker admission → 027b final integrated-tree checks/merge approval → 028 React Mission Control → 029 trace/cost/exposure views → 030 complete gates and 14-day trial.

Each worker uses an isolated worktree and the same kernel-owned policy/attempt protocol. Passing isolated tests cannot authorize an integrated tree. Mission Control reads the canonical API/event cursor; the UI never becomes another state store. Preserve vendor-neutral contracts and represent unknown quota/cost as unknown.

**Build-complete exit:** A-1, D-1 and B-1 fixtures pass, including two independently configured workers, conflict handling, final-tree verification, stale-epoch rejection and exact merge approval. All 31 MVP AOS items and the baseline obligations in section 8 have acceptance evidence. Mark an immutable MVP candidate with commit, dependency/model/CLI/hardware manifest, setup/backup/rollback instructions and a known-issues list. This is not yet owner-accepted MVP completion.

## 7. Mandatory MVP review checkpoint — stop before SOTA

Use [the MVP acceptance checklist](MVP_ACCEPTANCE_CHECKLIST.md) and AOS-030 to review the candidate. Freeze feature additions; perform the full gate suite and a 14-day daily-use trial on explicitly consented scope. A release-blocking fix changes the candidate; re-run affected tests and extend/restart the relevant observation interval so the final accepted candidate has defensible evidence. Document code/version/hardware changes; never mix trial evidence silently.

The owner reviews actual outcomes, source evidence, privacy/egress decisions, approval burden, usability, resource impact, restarts, setup and restore. Existing security/integrity defects block acceptance. Non-blocking issues may be listed with owner, priority and follow-up scope; mandatory gate failures cannot be waived into PASS.

**State distinctions:** NOT_STARTED → BUILDING_MVP → MVP_CANDIDATE → MVP_UNDER_REVIEW → MVP_ACCEPTED. MVP_ACCEPTED means the specified gates and trial passed and the owner accepted that evidence. It does not claim public-production security certification or measured state-of-the-art leadership.

**Two separate decisions:** (1) accept this MVP version; (2) authorize the next SOTA phase. Accepting MVP need not authorize expansion. After acceptance, keep it usable and continue a maintenance-only loop if the owner prefers. Start R4 implementation only when owner acceptance and SOTA authorization are recorded. Planning this roadmap does not grant that future authorization.

## 8. Cross-cutting MVP obligations to keep visible

The frozen master and revised per-item specs have different levels of detail. Carry the following baseline obligations into the named parent plans; do not let them disappear because they are smaller than a standalone AOS item. If not already explicit in a parent plan, attach a scoped acceptance addendum before marking that parent complete.

| Obligation | Parent specs | What must be demonstrated by R3 |
|---|---|---|
| MVP-X01: basic token-broker path | 012,016,029 | Local provider and one explicitly configured API SDK through the same inference contract; opt-in eligible data only, no fallback for Restricted/offline work, mocked CI plus explicitly authorized live compatibility evidence |
| MVP-X02: basic context and capability manifests | 002,008,010,011,024,025 | Minimal task/project packs and static approved tool/model/worker manifests, hashes and compatible harness prompt channels; unsafe repo instructions cannot grant authority |
| MVP-X03: memory privacy lifecycle baseline | 011,017 | Source/validity/supersession, explicit correction, pin/retention metadata and user suppression/delete interface; suppressed facts excluded from new retrieval/context; physical backup/provider deletion limitations disclosed. Automated compaction waits for R6 |
| MVP-X04: hard budget and capacity stops | 006,010,012,024,026,029 | Attempts/process/resource bounds and explicitly configured cash caps, reservation when concurrent spend is possible, no guessing unknown costs/quota and no retry storm or unauthorized switch |
| MVP-X05: local service and operational recovery | 003,005,018,030 | Documented start/restart/reboot behavior, bounded human waits/cancellation, safe artifacts, task-state continuity, backup/restore and runbooks without keeping an LLM reasoning loop alive |
| MVP-X06: small quality baseline | 017,022,027a,027b,030 | A reviewed 10–20-scenario corpus covering Ask/Delegate/Build and failure cases; independent grading plus deterministic checks. Keep development/holdout separation where feasible and preserve versions; no invented hundreds of historical examples |

These clarify the baseline MVP, not advanced optimizers or autonomous expansion. API/live tests and personal-repo trials are separately scoped when implementing; no credentials are provisioned by this planning task.

## 9. R4 — intelligent routing and compute (G4)

**Entry:** MVP_ACCEPTED and owner authorization to start SOTA. **Scope:** 031 entitlement/consent/uncertainty → 032 controlled engine comparison → 033 adaptive quota/resource/cost governor. Base safety continues from MVP.

Plan children for approved provider telemetry, eligible-backend filtering, task-class success estimates, reset forecasting, hard/soft budget pacing, capacity reservation, scarcity/shadow-price candidates and value-of-information scheduling. Compute scarcity prices only when quota units and remaining capacity are meaningfully observed. Unknown is not unlimited or free.

Benchmark compatible model artifacts across local engines with warm/cold and prefix-reuse conditions, foreground pressure and supported concurrency. Include quantization/offload/batching/cache/affinity and model eviction/slots as measurable options; record unsupported cases. Optional gateway or a different runtime is adopted only with quality/resource/security evidence.

**G4 exit:** cost per verified success, deadline success and foreground impact improve or a documented experiment rules out an unsuitable option; no privacy/consent/budget regression; reservation concurrency, provider 403/429, OOM, thermal/battery and rollback fixtures pass. Research decisions are recorded with raw measurements, not performance promises.

## 10. R5 — richer context, memory and interaction (G5)

**Entry:** G4 and current phase scope reviewed. **Scope:** 034 context/RAG/voice/desktop → 035 scoped computer use. Break each epic into concrete child plans before implementation; do not treat an entire epic as one day of work.

Substreams retain: context provenance and token budgets across harnesses; FTS/embeddings/reranking/conflict handling; local STT/TTS and opt-in voice; tray/hotkey/selected-context capture; notification inbox/quiet hours/focus modes; private phone status/approvals; browser/IDE/office/note-app integrations; multimodal/OCR/image/science/SQL/retrieval specialist manifests; observation/actor separation and human takeover.

An optional MCP front end for Hermes/other clients exposes the same scoped kernel API after it is stable. Keep native harness support; ACP adapters depend on actual compatibility and A2A federation matures in R7. No transport grants extra permission. Rich tool discovery is R6.

**G5 exit:** representative owner-selected repeated tasks show usefulness, retrieval lift and acceptable context/capture cost; cross-project/privacy and prompt-injection fixtures pass; microphone/screen capture is opt-in and visibly controllable; sensitive send/delete/payment/permission actions require exact approval; disconnect/unknown UI/cancel safely stop new actions. Each enabled platform/app has its own conformance evidence.

## 11. R6 — evaluated adaptation, registry and forgetting (G6)

**Entry:** G5; consented labeled outcomes exist. **Scope:** 036 split into evaluation/registry/lifecycle/improvement children.

Retain immutable replay and held-out data; baseline against vendor drift; component, end-to-end and safety evaluation; corrections/candidate mining; prompt/context/routing optimization; semantic+typed tool/model/skill registry; non-privileged periodic scout of approved sources; pinned/signed/permission-reviewed candidates and isolated trials; just-needed descriptor loading; canary/promotion/versioned rollback.

Add hot/warm/cold/tombstoned memory, lineage-aware suppression/purge, pin protection, compaction dry-runs, source-confidence/decay/half-life/value-score research, re-embedding on model changes, storage thresholds and honest backup/provider erasure semantics. Matched comparisons must show memory lift; candidate_helped is attribution, not causal proof.

Specialist capability acquisition remains scoped. The preserved reverse-engineering example is an authorized capability candidate, not automatic installation or a new permission. Local LoRA/QLoRA or offline policy learning is optional after sufficient consented data and superiority over prompting/retrieval are established. Standing rules, privileges, tool installs and high-impact changes require owner review.

**G6 exit:** known-bad changes fail frozen/held-out and security checks; approved promotion has measured utility without gate regression and reproducible revert; a forget request suppresses known derivatives immediately and reports physical erasure limitations; small sample uncertainty and contaminated-label risks remain visible.

## 12. R7 — portable, multi-machine, open-source operation (G7)

**Entry:** G6 and explicitly scoped supported-platform matrix. **Scope:** 037 split into platform, release, upgrade/recovery, remote-executor and operations children.

Retain Linux NVIDIA/CPU-only and Apple Silicon profiles, native Apple inference, optional trust-aware multi-device scheduling and ACP/A2A/extra harness adapters where actually supported. Remote workers cannot inherit owner credentials or data access. Multi-node DBOS/conductor or alternative execution infrastructure is an evidence-driven ADR, not a prerequisite for local MVP.

Deliver pinned/signed releases, SBOM/license provenance, offline install option, no mandatory account/telemetry, platform doctor, setup wizard, versioned API/skill compatibility, tested upgrade/backup/restore, maintainers' security response policy and contribution docs. Verify public naming/package/CLI availability before publishing. Do not claim cross-platform sandbox or signature validity without independent checks.

**G7 exit:** independent fresh install and restore/rollback, cross-platform isolation, offline Restricted egress tests, remote owner-boundary tests, signature verification, external security review and a 14-day supported-platform recovery soak. State supported/experimental/unsupported profiles plainly.

## 13. Full backlog and dependency map

Every active spec is assigned exactly once below. The phase order preserves all actual dependency edges; later phases reuse completed earlier foundations. Read the current spec, common requirements and the relevant dependency docs when planning an item.

| Spec | Phase / track | Deliverable | Dependencies |
|---|---|---|---|
| [AOS-001](specification/specs/AOS-001.md) | R0 / MVP | Repository scaffold, developer toolchain, CI and local services | — |
| [AOS-002](specification/specs/AOS-002.md) | R0 / MVP | Goal contracts, tasks, attempts and database migration v1 | AOS-001 |
| [AOS-003](specification/specs/AOS-003.md) | R0 / MVP | DBOS-backed durable single-task execution and recovery | AOS-002 |
| [AOS-004](specification/specs/AOS-004.md) | R0 / MVP | Synthetic worker, isolated Git workspace and deterministic verification | AOS-003 |
| [AOS-005](specification/specs/AOS-005.md) | R0 / MVP | Minimal goal/approval API and CLI end-to-end synthetic slice | AOS-003, AOS-004 |
| [AOS-006](specification/specs/AOS-006.md) | R1 / MVP | Lease fencing, retry bounds, outbox and external-action reconciliation | AOS-003 |
| [AOS-007](specification/specs/AOS-007.md) | R1 / MVP | Independent project trust, data privacy and autonomy policy model | AOS-002 |
| [AOS-008](specification/specs/AOS-008.md) | R1 / MVP | Sandbox profiles, mount validation and enforceable outbound controls | AOS-004, AOS-007 |
| [AOS-009](specification/specs/AOS-009.md) | R1 / MVP | Loopback API authentication, host/origin hardening and approvals | AOS-005, AOS-007 |
| [AOS-010](specification/specs/AOS-010.md) | R1 / MVP | Hardened Claude Code worker adapter and hostile-repository tests | AOS-004, AOS-008, AOS-009 |
| [AOS-027a](specification/specs/AOS-027a.md) | R1 / MVP | Single-worker verification and protected merge approval | AOS-004, AOS-009, AOS-010 |
| [AOS-011](specification/specs/AOS-011.md) | R1 / MVP | Source-linked personal memory schema and five-stage use events | AOS-002 |
| [AOS-012](specification/specs/AOS-012.md) | R1 / MVP | Routing outcomes, corrections and cloud-exposure event contracts | AOS-002, AOS-007 |
| [AOS-014](specification/specs/AOS-014.md) | R1 / MVP | OpenTelemetry correlation, canonical event replay and SSE | AOS-003, AOS-012 |
| [AOS-015](specification/specs/AOS-015.md) | R1 / MVP | Hardware probe integration and versioned capability manifest | AOS-001 |
| [AOS-016](specification/specs/AOS-016.md) | R1 / MVP | Local inference adapter and warm/cold/pressure benchmarking | AOS-011, AOS-015 |
| [AOS-017](specification/specs/AOS-017.md) | R1 / MVP | Offline Ask and source-scoped memory interaction | AOS-011, AOS-016 |
| [AOS-018](specification/specs/AOS-018.md) | R1 / MVP | Offline, degraded-mode and foreground-resource safety tests | AOS-015, AOS-016, AOS-017 |
| [AOS-013](specification/specs/AOS-013.md) | R2 / MVP | Research source snapshots, hashes, passage spans and claim evidence | AOS-002, AOS-008 |
| [AOS-019](specification/specs/AOS-019.md) | R2 / MVP | Search abstraction and SSRF-safe web retrieval broker | AOS-008, AOS-009, AOS-013 |
| [AOS-020](specification/specs/AOS-020.md) | R2 / MVP | Quarantined web reader and immutable source provenance | AOS-013, AOS-019 |
| [AOS-021](specification/specs/AOS-021.md) | R2 / MVP | Deterministic source citation and exact quotation verifier | AOS-020 |
| [AOS-022](specification/specs/AOS-022.md) | R2 / MVP | Claim-support adjudication, contradiction and uncertainty labeling | AOS-021, AOS-016 |
| [AOS-023](specification/specs/AOS-023.md) | R2 / MVP | Bounded Delegate planner, research brief output and R2 gate | AOS-019, AOS-020, AOS-021, AOS-022 |
| [AOS-024](specification/specs/AOS-024.md) | R3 / MVP | Codex supported CLI adapter and contract suite | AOS-004, AOS-008, AOS-010 |
| [AOS-025](specification/specs/AOS-025.md) | R3 / MVP | Build task DAG and bounded LangGraph reasoning/replan | AOS-003, AOS-016 |
| [AOS-026](specification/specs/AOS-026.md) | R3 / MVP | Concurrent two-worker scheduler, worktree conflict control and admission | AOS-006, AOS-010, AOS-024, AOS-025 |
| [AOS-027b](specification/specs/AOS-027b.md) | R3 / MVP | Integrated multi-worker verification and protected merge | AOS-027a, AOS-026 |
| [AOS-028](specification/specs/AOS-028.md) | R3 / MVP | React Mission Control task views, approvals and event replay | AOS-005, AOS-014, AOS-017, AOS-023, AOS-027b |
| [AOS-029](specification/specs/AOS-029.md) | R3 / MVP | OTel/Phoenix tracing, cost/usage confidence and exposure dashboard | AOS-012, AOS-014, AOS-028 |
| [AOS-030](specification/specs/AOS-030.md) | R3 / MVP | A-1/D-1/B-1 acceptance, chaos and two-week dogfood gate | AOS-017, AOS-018, AOS-019, AOS-020, AOS-021, AOS-022, AOS-023, AOS-024, AOS-025, AOS-026, AOS-027b, AOS-028, AOS-029 |
| [AOS-031](specification/specs/AOS-031.md) | R4 / SOTA | Provider subscription entitlement telemetry and consented quota-aware routing | AOS-012, AOS-026, AOS-029 |
| [AOS-032](specification/specs/AOS-032.md) | R4 / SOTA | Controlled inference engine comparison: Ollama, vLLM and SGLang | AOS-015, AOS-016, AOS-031 |
| [AOS-033](specification/specs/AOS-033.md) | R4 / SOTA | Adaptive quota/resource governor and optional secure API gateway | AOS-026, AOS-031, AOS-032 |
| [AOS-034](specification/specs/AOS-034.md) | R5 / SOTA | Provenance-aware context compiler, hybrid RAG, voice and quick desktop UX | AOS-011, AOS-017, AOS-029 |
| [AOS-035](specification/specs/AOS-035.md) | R5 / SOTA | Sandboxed computer use and authorized desktop/browser integrations | AOS-008, AOS-019, AOS-034 |
| [AOS-036](specification/specs/AOS-036.md) | R6 / SOTA | Offline evaluation, gated improvement, skill registry and memory lifecycle | AOS-012, AOS-013, AOS-021, AOS-022, AOS-034 |
| [AOS-037](specification/specs/AOS-037.md) | R7 / SOTA | Portable open-source release, multi-machine evaluation and sustained operations | AOS-001, AOS-002, AOS-003, AOS-004, AOS-005, AOS-006, AOS-007, AOS-008, AOS-009, AOS-010, AOS-011, AOS-012, AOS-013, AOS-014, AOS-015, AOS-016, AOS-017, AOS-018, AOS-019, AOS-020, AOS-021, AOS-022, AOS-023, AOS-024, AOS-025, AOS-026, AOS-027b, AOS-028, AOS-029, AOS-030, AOS-031, AOS-032, AOS-033, AOS-034, AOS-035, AOS-036 |

## 14. What happens next

The historical baseline and the superseded [AOS-001 checklist](plans/AOS-001-checklist.md) remain for provenance. The active plan is the [AOS-001 implementation plan](plans/AOS-001-implementation-plan.md). Next, accept or return the corrected S1 slice, then implement S2. AOS-002 through AOS-005 already have detailed plans; do not treat them as unwritten. S1 is not a release-gate pass, and R0 is not complete.

Build a usable R1 pilot, add R2 verified research, then finish R3 concurrency/dashboard and the release trial. Freeze and review the MVP at the explicit checkpoint. SOTA epics remain visible and measurable, with detailed child plans generated after MVP feedback rather than before hardware, workload and integration facts exist.

The old architecture's Phase 0–5 labels and this roadmap's R0–R7 labels use different granularity. Always reference the R release and AOS ID in implementation issues to avoid phase-name ambiguity. The full target is preserved; optional framework choices require evidence instead of installing every named alternative together.
