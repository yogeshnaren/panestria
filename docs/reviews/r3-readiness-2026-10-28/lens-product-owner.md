# Panestria pre-production audit: Product Owner lens (requirements fidelity and drift)

Repo HEAD inspected: `33e61dc` (main, PR #212), clean tree, 2026-10-28. Local git history is grafted (329 commits, earliest is PR #163 merge `c413e78`, 2026-10-21), so pre-10-21 history cannot be audited locally.
Method: read the authoritative docs; ran the repo's own read-only inventory (`python -B -m panestria.verification.readiness --gate G1|G2|G3 [--pretrial]`, output saved as `ready_G*.json` in this scratchpad); `pytest --collect-only` (2482 tests collected, 68 live); python scripts over `test-catalog.json`, `release-gates.json`, `requirement-traceability.json`, `phase-tracker.json`, `implementation-slices.json`; grep over `src/`, `tests/`, `evidence/`, `docs/`. No repo files modified. I did not run the DB/Docker-backed suites (other reviewers share ports 55440). The 3 failures I saw in `tests/contract/test_aos_001_toolchain.py` come from the host's uv 0.11.32 vs `required-version = "0.12.3"` (pyproject.toml:48). I treat them as an environment finding (F-17), not a product defect.

Confidence: CONFIRMED = reproduced by command or direct file quote. PLAUSIBLE = inferred.

---------------------------------------------------------------------------------------------------

## 1. Status truth

### 1.1 What the machine-readable sources claim (CONFIRMED)
| Source | R0/G0 | R1/G1 | R2/G2 | R3/G3 |
|---|---|---|---|---|
| docs/phase-tracker.json (python dump) | COMPLETE / PASS (candidate f161193, evidence/G0/evaluation.json) | IN_PROGRESS / NOT_RUN; 13 items all IN_PROGRESS; 6 of 13 have 0 evidence_refs (AOS-006, 007, 009, 011, 012, 014) | IN_PROGRESS / NOT_RUN | DRAFT / NOT_RUN; AOS-024, 026, 027b, 028, 029, 030 status NOT_STARTED with 0 evidence refs; `mvp.state=IN_PROGRESS`, `owner_acceptance=PENDING`, `candidate_commit=null` |
| docs/testing/release-gates.json | G0 PASS | G1 NOT_RUN (72 cases) | G2 NOT_RUN (96) | G3 NOT_RUN (157; 156 pretrial + AOS-030-TC04) |
| docs/PANESTRIA_PHASED_IMPLEMENTATION_PLAN.md:3 | "R0 COMPLETE/G0 PASS; R1 IN_PROGRESS/G1 NOT_RUN; R2/R3 release scope DRAFT with component implementation in progress; G2/G3 NOT_RUN" | | | |
| docs/MVP_ACCEPTANCE_CHECKLIST.md:3 | "MVP state IN_PROGRESS, not accepted"; every final-candidate box unchecked; all six fault drills "pending / NOT_RUN" | | | |
| docs/IMPLEMENTATION_PROGRESS.md "Current delivery checkpoint" (~line 39) | "R3 is building; the MVP has not reached candidate acceptance"; "G1/G2/G3 not passed; paid SDK TC04 deferred, no 14-day trial or owner acceptance" | | | |

Assessment of the headline claim: the top-level truth is honest and conservative. No gate above G0 is claimed passed, and no doc claims MVP acceptance. This is a real strength. The drift is in the secondary status surfaces and in the per-item and per-case rows.

### 1.2 Stale or internally contradictory status text (CONFIRMED)
- docs/GOAL_PROGRESS.md:5 "R1 implementation is IN_PROGRESS on `r1-alpha`" and :41 "R2/R3/SOTA implementation has not begun." Latest dated entry is 2026-10-14. The tracker marks R2 IN_PROGRESS, and `src/panestria/brokers/research`, `execution/research_*.py`, `kernel/plan_*.py`, `apps/mission-control` and `api/phone.py` all exist. The file was last touched 2026-10-21 (c413e78). This is the doc that AGENTS.md-style "goal" flows point at; it understates reality by roughly 9 days and 190 merges.
- docs/SETUP.md:3 "R0 is not accepted." R0 was accepted 2026-10-13 (GOAL_PROGRESS.md:3, tracker). Setup is the first doc an operator reads.
- docs/README.md:5 "AOS-001, R0, and the R3 MVP are incomplete." AOS-001 and R0 are COMPLETE per the tracker.
- docs/operations/RUNBOOK-AND-RELEASE.md:3 "Commands are planned contracts, not currently available application operations"; :~40 says `upgrade head` "applies 0001_scaffold, 0002_kernel, 0003_approval_preview, and 0004_check_candidate". `migrations/versions` has 41 files, head is `0040_phone_devices`.
- docs/requirement-traceability.json: `status` is "DESIGN_MAPPING_NOT_RUNTIME_PROOF", and 227 of 228 requirements are `NOT_IMPLEMENTED`, including every AOS-001..005 clause (e.g. AOS-001-F01 `NOT_IMPLEMENTED`) although R0 is COMPLETE/PASS and src has 55k LOC. Only MVP-X07 is IN_PROGRESS. The file is therefore not usable as a status instrument.
- docs/testing/test-catalog.json (last changed 2026-10-21): 137 of 157 cases NOT_RUN. Five cases have retained passing live results (`evidence/r1-offline-qualification-2026-10-18/report.json`: AOS-015-TC03, AOS-016-TC03, AOS-017-TC04, AOS-018-TC02, AOS-018-TC04) and the catalog still says NOT_RUN. That is conservative, but the schema has no state for "observed pass on an older commit, stale for the current candidate", so the owner cannot see real R1 progress from the catalog.
- docs/phase-tracker.json under-reports R3 work that exists: AOS-027b "NOT_STARTED / 0 evidence", yet `docs/testing/FINAL_TREE_INTEGRATION.md`, `tests/integration/test_final_plan_integration.py:89` (individual-pass / combined-fail) and `evidence/final-tree-integration-2026-10-20/report.json` (4 runs, 34 tests green, `release_gate: NOT_ASSESSED`) exist. AOS-026 "NOT_STARTED" while `kernel/scheduler.py:134-138` enforces plan and worker parallel limits and `execution/native_plan.py:351` runs a ThreadPoolExecutor with `max_workers = maximum_parallel (2)`. AOS-029 "NOT_STARTED" while `telemetry/tracing.py`, `overview.py`, `performance.py` and `contracts/learning.py` (authorized/accessible/observed) exist. Honest-but-lossy: the tracker cannot say "component delivered, case unregistered".
- Positive consistency: README.md:3, CONTRIBUTING.md:3, docs/START_HERE.md:5, docs/CURSOR_START_HERE.md:18, MVP_ACCEPTANCE_CHECKLIST.md:3, plan:3 and tracker all agree R0 complete, R1 in progress, MVP not accepted.

Verdict on "is GOAL_PROGRESS stale?": yes, CONFIRMED. R1 is still not promoted (G1 NOT_RUN is correct), but the "R2/R3 not begun" sentence is false.

### 1.3 Code/evidence vs claims, per release
- R0: supported. `evidence/G0/evaluation.json`, `contracts/phase/r0-phase.acceptance.json`. Caveat: under today's readiness inventory only 9 of the 20 G0 cases have a literal registration (R0 receipts are historical and pre-date `gate_case_id`); the inventory itself says this does not invalidate R0 (docs/reviews/MVP-READINESS-2026-10-15.md).
- R1: substantially built at component level (offline Ask CLI/TUI/browser, memory, vault, sandbox, native Claude Build, protected merge). Live component pass exists (`r1-offline-qualification-2026-10-18/report.json`: 10/10 offline questions, cold TTFT 2.04 s, warm p95 0.041 s, network none, foreground WAIT then PERMIT) at candidate `d1ee854`, which is not the HEAD and not a same-candidate G1 evaluation. Unmet per the repo's own text: AOS-016-TC04 (paid SDK smoke "owner-deferred"), cumulative same-candidate G1, billing evidence "stale / background OFF" (IMPLEMENTATION_PROGRESS.md ~46, ~59).
- R2: partially built (guided manual research stages, fetch broker, reader, claim review, entailment probes). `IMPLEMENTATION_PROGRESS.md` delivery table: "Actual search is owner-deferred; qualified bounded planning/support, aggregate workflow and complete D-1/G2 remain". AOS-023 ("bounded Delegate planner... and R2 gate") is therefore not met.
- R3: partially built (final-tree integration, scheduler, two-Claude-worker plan driver, Mission Control intake/review modes, private phone ingress component, quota queue, storage awareness). Not built: Codex adapter (AOS-024), gate evaluator and fault drills (AOS-030), trace/cost/exposure UI (AOS-029), real-device phone check.

---------------------------------------------------------------------------------------------------

## 2. Traceability

### 2.1 Aggregate computation (CONFIRMED, from `readiness` JSON and `pytest --collect-only`)
- G3: 157 required; 58 with a literal `gate_case_id` registration; 99 missing. Pretrial (156): 58 registered, 98 missing.
- G1: 72 required, 57 registered (15 missing). G2: 96 required, 57 registered (39 missing).
- By release: R0 9/20; R1-parent items 49/74; R2 **0/24**; R3 **0/39**. Revision-3 extension cases: **1/33** (only AOS-011-TC05). Live-required cases: 12/25 registered.
- Registered nodes all collect (85/85 nodes found in the pytest collection), so registrations are real, not dangling.
- Only 44 of 157 cases have the catalog's `planned_nodeid` actually present; 21 of 45 planned test files do not exist (tests/e2e/test_aos_023/028/030.py, test_mvp_x07..x14.py, tests/integration/test_aos_013/019-022/024-027b/029.py).
- Registered vs total test base: 2482 collected tests; 85 nodes carry a case ID (about 3.4%). Everything else, including the ~50 test files for research, phone, plan scheduler, quota, background, storage, is unbound to the release catalog.
- Trend: the 2026-10-15 inventory reported 56/157 registered (docs/reviews/MVP-READINESS-2026-10-15.md:9). Today it is 58/157. Over those 13 days about 190 PRs/commits merged (`git log --since=2026-10-15` = 329 commits). Case registration was effectively frozen while feature work ran, so the traceability gap is widening in relative terms.
- Evidence linkage: 171 evidence directories; only 82 are referenced from tracker/slices/catalog/traceability; 9 of 150 `evidence/*/report.json` mention any AOS-xxx-TCyy. Evidence is rich and honest (every report carries `release_gate: NOT_ASSESSED/NOT_EVALUATED` and a `remaining` list) but it is component-scoped, not case-bound.
- No gate evaluator exists: `src/panestria/verification/readiness.py` is explicitly `release_verdict: NOT_EVALUATED` and "never a release gate evaluator". `docs/testing/TEST_EXECUTION.md` ("Gate evaluator contract") describes one; AOS-030-S1 is NOT_STARTED. G1/G2/G3 therefore cannot be mechanically passed today, even in principle.

### 2.2 R3 AOS items and revision-3 obligations
Legend: code = implementing modules exist; tests = case IDs registered (R) / related tests exist but are unregistered (U); evidence = retained evidence directory.

| Item | Code present? | Tests registered/collected? | Evidence? | Gap |
|---|---|---|---|---|
| AOS-024 Codex adapter | **No.** `grep -ri codex src tests` returns nothing. Provider enums list only local-ollama / openai-api / claude-code (`telemetry/tracing.py:22`, `contracts/learning.py:28`). No ADR defers it | 0/4 registered; `tests/integration/test_aos_024.py` does not exist | none | Entire item absent. Second vendor adapter missing, so B-1 "both pinned vendor adapters" (checklist) and AOS-026-TC04 / AOS-027b-TC04 / AOS-030-TC03 live cases are unreachable |
| AOS-025 Plan DAG / replan | Yes: `contracts/plan.py`, `execution/build_plan.py` (402 LOC), `kernel/plan_store.py`, `plan_revisions.py`, `execution/local_plan.py`, `local_repair.py`. LangGraph absent (spec: optional) | 0/8 (4 base + 4 X10) registered; unregistered tests: `test_plan_revisions.py`, `test_canonical_plan_store.py`, `test_local_build_repair.py`, `tests/contract/test_build_plan.py` | `canonical-plans-2026-10-18/20`, `bounded-plan-revisions-2026-10-20`, `local-build-repair-2026-10-21` | Registration; `ProgressLedger` / `RepairPolicy` names absent (implemented as plan revisions + finite repair) |
| AOS-026 Two-worker scheduler | Partial: `kernel/scheduler.py`, `execution/native_plan.py` (2 parallel Claude workers), `sandbox/worktree.py`. "Two workers" means two **Claude** workers, not two vendor adapters | 0/4; `test_plan_scheduler.py`, `test_native_plan_execution.py` unregistered | `plan-scheduler-2026-10-20`, `native-plan-execution-2026-10-20` | Eight-job stress (TC02) not found; TC04 live needs two certified adapters. Tracker says NOT_STARTED |
| AOS-027b Integrated final-tree merge | Yes: `execution/build_merge.py`, `protected_merge.py`, `verification/merge.py`, `docs/testing/FINAL_TREE_INTEGRATION.md` | 0/4; `test_final_plan_integration.py`, `test_protected_merge.py` | `final-tree-integration-2026-10-20` (34 tests, `NOT_ASSESSED`), `final-integration-intent-2026-10-20` | Registration; owner conflict resolution and replanning explicitly "not implemented" (FINAL_TREE_INTEGRATION.md); no live B-1 |
| AOS-028 Mission Control | Partial: `apps/mission-control/src` ~800 lines TSX (BuildIntake, BuildReview, BuildEvidence, PlanRun, ResearchIntake, ReviewInbox, OfflineAsk, StorageNotices) + `api/mission_web.py`, `api/phone.py` | 0/8; planned `tests/e2e/test_aos_028.py` and `test_mvp_x12.py` missing; Node tests in `apps/mission-control/tests/*.mjs` (12 files) unregistered | `mission-*-2026-10-21/23`, `phone-observer-views`, `private-phone-ingress`, `phone-pair-response-body` | No fleet/worker view, no trace/cost/exposure view, no keyboard/contrast test (TC04), no real-device phone check (TC08 LIVE, "owner-deferred") |
| AOS-029 Trace/cost/exposure | Partial: `telemetry/tracing.py` (bounded local OTel spans), `overview.py`, `performance.py`, `/v1/ask/{id}/ledger`; contract for authorized/accessible/observed | 0/4 | `performance-overview`, `ask-runtime-metrics`, `build-runtime-metrics`, `research-runtime-metrics` | No Phoenix (TC04 requires "pinned local Phoenix"; spec also says Phoenix optional: internal spec tension, no ADR). No exposure or cost dashboard in Mission Control; no `/v1/usage` or `/v1/audit` in `docs/api/openapi.json` |
| AOS-030 Gates, drills, trial | Almost none: `verification/readiness.py` only. No gate evaluator, no six-drill harness, no trial log tooling (`grep -ri trial src` only hits readiness) | 0/7; `tests/e2e/test_aos_030.py`, `test_mvp_x14.py` missing | none | Entire item absent beyond inventory |
| MVP-X07 profile/classification | Yes: `memory/vault.py`, `keys.py`, `profile.py`, `classification.py`, `contracts/classification.py`, migration, ADR 0003 | 1/4 (TC05 only) | `profile-vault/keys/context-2026-10-15`, `classification` tests, `test_profile_vault_restore.py` | TC06-08 unregistered; `ClassificationResolver` name absent (implemented as ledger) |
| MVP-X08 charter/style/model context | Yes: `memory/style.py`, `presentation.py`, `contracts/style.py`, `context.py`, `inference/manifest.py`, `config_model.py`, private style examples | 0/4 | `structured-profile-style`, `private-style-examples`, `lossless-presentation`, `pinned-model-manifest`, `local-charter-context` | Registration only; owner readability preference evaluation not found |
| MVP-X09 connection grants | Yes: `contracts/connections.py`, `kernel/connection_broker.py`, `connection_roots.py`, `native_connection.py`; CLI terminal | 0/4 | `connection-reviews-2026-10-16`, `connection-root-sessions`, `native-connection-grants`, `fetch-connection-grants` | General secret broker / account lifecycle explicitly open (IMPLEMENTATION_PROGRESS delivery table "General account/root/secret lifecycle and actual conformance") |
| MVP-X10 progress / repair | Partial: finite repair, plan lifecycle, progress; no `ProgressLedger`/`RepairPolicy` symbols | 0/4 | `build-progress`, `repair-draft-intents`, `plan-lifecycle` | Registration; semantic milestone review not found |
| MVP-X11 quota + offline capture | Yes (broad): `kernel/quota.py`, `background*.py`, `execution/background_*.py`, `learning/curation.py`, `contracts/background.py`, `curation.py` | 0/6 | `quota-observations`, `background-*-2026-10-21/23`, `curated-example-rights-2026-10-23` | Billing evidence "stale / background OFF"; "increase urgency as reset approaches" is only a reported `seconds_to_reported_reset` (`kernel/background.py:273`) (PLAUSIBLE gap); queue is finite, serial, 1 job, no daemon; `OfflineResult`/`TrainingEligibility` classes absent by name |
| MVP-X12 phone | Yes (component): `api/phone.py`, `kernel/phone.py`, migration 0040, `config_phone.py`, Mission Control phone observer | 0/4 (TC08 LIVE) | `private-phone-ingress-2026-10-23`, `phone-observer-views`, `phone-pair-response-body` | Real device, reconnect, revocation on actual phone is "owner-deferred" (IMPLEMENTATION_PROGRESS ~46); intermittent native-worker stop "unexplained" (~232); cert must match literal RFC1918/CGNAT IP |
| MVP-X13 resources + storage | Yes (component): `resources/{admission,hardware,storage,storage_history,storage_status}.py`, `sandbox/*`, `inference/process_memory.py` | 0/4 (TC08 LIVE) | `storage-*`, `r1-model-process-memory`, `cpu-admission`, `sandbox-oom-observation` | No predeclared host-specific budgets document found (`grep predeclared|qualification budget docs/testing` hits only an unrelated verifier doc); no PSI usage (`grep PSI src` empty); unified notifications still open per spec text itself |
| MVP-X14 reuse / REA | Docs/ADR only (`adr/0005-build-vs-adopt.md`) | 0/3; planned `tests/e2e/test_mvp_x14.py` missing | none | No REA decision records, no comparative corpus, no parity/rollback evidence for adopted components |

### 2.3 R1 / R2 compact table (cumulative)
| Group | Code | Registered cases | Notes |
|---|---|---|---|
| AOS-006 leases/effects, 007 policy axes, 008 sandbox, 009 API auth, 010 Claude adapter, 027a single-worker merge | present (`kernel/leases.py`, `effects.py`, `policy/`, `sandbox/`, `api/auth.py,security.py`, `brokers/harness/`, `protected_merge.py`) | 006 4/4, 007 4/4, 008 4/8 (4 live; 4 X09), 009 3/4, 010 3/4, 027a 3/4 | AOS-008 live-annotation mismatches for TC01/TC02, 027a-TC01, 018-TC02 flagged by the tool itself |
| AOS-011 memory, 012 routing/corrections/exposure, 014 tracing/SSE, 015 hardware, 016 local inference, 017 Ask, 018 resource | present | 011 5/8, 012 4/10, 014 4/4 (2 mapped), 015 4/4, 016 3/4 (0 planned node found), 017 4/8, 018 4/8 | X-case halves (the 33 extensions) are the unregistered part |
| AOS-013 research schema, 019 broker, 020 reader, 021 citation verifier, 022 support adjudication, 023 Delegate workflow | 013/019/020/021/022 present (`contracts/research*.py`, `brokers/research/fetch.py`, `execution/research_*.py`, `verification/entailment.py`, `research_text.py`); 023 only partial (manual guided stages, `execution/research_brief.py`, `research_synthesis.py`) | **0/24** | At least ~30 research tests exist (`test_research_*`, `test_isolated_research_reader.py`, `test_local_entailment_live.py`, `test_search_admission.py`, `test_configured_search.py`) and ~25 evidence dirs, but not one carries a `gate_case_id`. The G2 inventory cannot be satisfied by what exists |

### 2.4 Interpretation
Most feature code is real and heavily tested. What is broken is the binding between those tests and the 157-case contract, and the machinery that would turn bound results into a gate verdict. A release evaluator run today would return INCOMPLETE for 99 of 157 cases even if every existing test is green. That is the P0 for evidence discipline.

---------------------------------------------------------------------------------------------------

## 3. Drift

### 3.1 Scope creep into R4-R7 (CONFIRMED: none in code)
Grep over `src/` and `apps/mission-control/src` for vllm, sglang, lora/qlora, tts, whisper, computer-use, forecast, federation, distill, canary, langgraph, quick-capture: no hits (only `holdout` in `contracts/curation.py`, which MVP-X11 requires). `holdout` is development/holdout separation for curated examples and is in scope. `sota_implementation_authorized=false` is respected in code. Strength.

### 3.2 Quiet reinterpretation or narrowing of spec (findings)
- D1 (CONFIRMED) "Two vendor adapters" became "two Claude workers". Spec AOS-024 goal: "A second approved vendor harness... under exactly the same worker contract". The R3 plan says "two independently configured workers". The delivered driver accepts "one or two independent `claude-public-bash` nodes" (docs/testing/NATIVE_PLAN_EXECUTION.md:~33). There is no ADR recording the narrowing; checklist B-1 still demands both vendors.
- D2 (CONFIRMED) Native Build is PUBLIC-only. OWNER_BUILD_CLI.md:1 "Review a real PUBLIC Claude Build"; examples come from `tools/create_public_build_example.py` ("a tiny PUBLIC source repo"). Safe, but B-1 on the owner's own (INTERNAL/CONFIDENTIAL) repos is not available through a subscription worker; only the local-model path (`offline_build.py`, `local_plan.py`) can touch private data. Spec axes (trust, privacy, autonomy) are implemented as denies rather than as usable private-repo Build. No ADR.
- D3 (CONFIRMED) Phoenix replaced by local bounded OTel spans (`telemetry/tracing.py`) while AOS-029-TC04 literally requires "pinned local Phoenix" (test-catalog). Spec text is self-inconsistent (Phoenix "optional"); no decision record resolves which governs.
- D4 (CONFIRMED) Delegate is manual/guided stages, not the "bounded Delegate planner... workflow" of AOS-023 (IMPLEMENTATION_PROGRESS delivery table). The owner has deferred actual search. Acceptable as component progress, but D-1 is not a user journey yet.
- D5 (PLAUSIBLE) Background queue narrowed to finite, serial, one job per tick, no OS service (BACKGROUND_QUEUE_CONTROLLER.md "installs no OS service", "--ticks 12 --jobs 1"). Compatible with X11 "start with one bounded job"; "increase urgency as reset approaches" and the 40%-before-reset scenario are only partially expressed (`kernel/background.py:273` returns seconds-to-reset; no prioritisation found).
- D6 (CONFIRMED) MVP-X13 storage clarification (2026-10-18) states "unified notifications and operation preflight remain pending"; they were added to the spec as R3 scope after the baseline and are partial by the spec's own words.
- D7 (CONFIRMED) Surface proliferation instead of the specified Mission Control: 17 Typer sub-apps and 122 CLI commands, plus separate TUIs for Ask, Build review, Research claim review, Guided research, Project activity, profile style. The spec's AOS-028 asks for one React Mission Control with three usable intakes; the terminal tools are additive. This is a UX/maintenance cost, not a violation.
- D8 (CONFIRMED) Acceptance criteria were weakened nowhere that I could find; the opposite pattern dominates: reports say "not a release", "NOT_ASSESSED", "no mock, skip or missing live evidence is a release PASS". Good discipline.

### 3.3 Contract drift (code models vs schemas)
- Generated schemas match code: `rendered_schemas()` vs `docs/contracts/{acceptance-check,action-preview,goal-contract}.schema.json` = MATCH (python -B check).
- But three schema locations coexist: `docs/specification/contracts/` (original), `docs/schemas/` (hand-authored: titled "AgentOS v1 ...", no `$defs`, different shape from code), `docs/contracts/` (generated). `docs/schemas/acceptance-check.schema.json` and `goal-contract.schema.json` differ from the generated ones (`diff -q`). Nothing in tests/Makefile/CI references `docs/schemas` (grep empty), so it is an unguarded stale duplicate. (CONFIRMED)
- Only 3 of ~65 `contracts/*.py` models have exported JSON Schema; OpenAPI is exported with 39 paths and checked by `tests/e2e/test_aos_005.py::test_openapi_matches_the_mounted_routes`; the TS client `schema.d.ts` (3491 lines) is generated in CI. Spec interface names (`ClassificationResolver`, `ProgressLedger`, `RepairPolicy`, `BackgroundWorkItem`, `OfflineResult`, `TrainingEligibility`) are absent as symbols. The spec calls them "proposed interfaces", so this is naming drift, not a defect.

### 3.4 Documentation sprawl (CONFIRMED numbers)
- `find docs -type f | wc -l` = 483 (439 md). Outside `docs/specification`: 378 md files, 26,119 lines.
- `docs/testing/*.md`: 106 files, 8,198 lines, most named for a single PR-sized component (e.g. BACKGROUND_WORKER_AUTHORITY.md, NATIVE_BASH_BUILD.md). `docs/cursor/`: 95 files. `docs/PANESTRIA_R0_R3_FULL_IMPLEMENTATION_DESIGN.md`: 3,314 lines.
- `docs/IMPLEMENTATION_PROGRESS.md`: 1,061 lines / 80 KB, 50 sections, nearly all headed "Current ...". Same text carries "Updated 2026-10-23" at the top and 10-14..10-18 narrative below. Formatting corruption throughout: "At4MiB" (line 23), "retains45" (27), "merged9a7d..." / "PR101 actually merged" / "clean21bfa80" (tail). Readers cannot tell what is current.
- `docs/MVP_EXECUTION_CHECKPOINT.md` (591 lines) self-labels as historical (lines 3-6) but remains in the top-level docs/ listing.
- Evidence: 171 directories, 710 files, 37 MB, committed. 89 of 171 directories are unreferenced from any manifest.
- Seven overlapping status surfaces (README, CONTRIBUTING, START_HERE, CURSOR_START_HERE, GOAL_PROGRESS, IMPLEMENTATION_PROGRESS, phase-tracker plus checkpoint) with the contradictions in 1.2.
- Verdict: unmaintainable by hand. Facts are accurate in the small and the machine manifests are partially synchronized (slices updated 2026-10-23), but catalog/tracker/traceability were last regenerated 2026-10-21 while the work continued.

---------------------------------------------------------------------------------------------------

## 4. Product-level gaps blocking a production MVP

### 4.1 Journeys
- A-1 Ask: closest to done. Offline Ask via `panestria local init/serve`, TUI and browser mode; live 10/10 network-disabled run with scoped recall; foreground pressure WAIT/PERMIT. Gaps: no hardware-specific latency target recorded ("Confirm a hardware-specific target before acceptance", checklist line 18; no predeclared budget file found); evidence is at old candidate `d1ee854`; setup is a multi-step CLI path with UUIDs and private dirs (LOCAL_ASK_SETUP.md: alembic upgrade, `local init`, serve in terminal A, TUI in terminal B) and requires a manually prepared model cache and Node 20.19+ plus manual `npm run build` for the browser page (MISSION_CONTROL_OBSERVER.md; dist "not committed or bundled into the Python wheel"). Hardware/product score here: usable by the author, not by a new owner.
- D-1 Delegate: not a journey yet. Manual staged collection and claim review exist; actual search deferred by owner; aggregate workflow (AOS-023) absent; no "one explicitly authorized live public brief" retained (closest: `retained-research-brief-2026-10-18`, `sonnet-public-verifier-2026-10-23`, still component evidence). Calibrated support/contradiction judgments: entailment corpus and Sonnet calibration exist but G2 gate NOT_RUN.
- B-1 Build: partially real. One or two Claude workers run in parallel on PUBLIC synthetic repos, integrated final-tree checks run, exact owner merge works; a background-owner journey completed one PUBLIC synthetic job with two serial Claude workers (`evidence/background-owner-journey-2026-10-21`). Missing: second vendor (AOS-024), eight-job stress, owner conflict resolution (explicitly not implemented), private repo support (D2), live B-1 with two certified vendor adapters. Ops cost to the owner: 5+ CLI commands with UUIDs and SHA acknowledgments (NATIVE_PLAN_EXECUTION.md).
- Intermittent failure: an "intermittent native-worker stop" remains "unexplained" (IMPLEMENTATION_PROGRESS.md ~232, ~7). CONFIRMED as documented open issue.

### 4.2 Six fault drills (checklist, all "pending / NOT_RUN")
Component coverage exists for each, but there is no drill harness or retained drill evidence (AOS-030-TC02 file `tests/e2e/test_aos_030.py` missing):
1. Ambiguous external effect: `tests/integration/test_aos_006.py`, `test_protected_merge.py`, lost-reply fixtures: component only.
2. Prompt injection: `test_isolated_research_reader.py`, hostile-repo fixtures in AOS-010: component only.
3. Exhausted entitlement: `test_background_queue.py`/quota observed-exhaustion wait (kernel/background.py:212): component only.
4. GPU/resource pressure: live AOS-018-TC04 passes at `d1ee854`: older candidate.
5. False done: R0 verifier suite: R0 only.
6. Approval change after crash: `test_approval_revocation.py`: component only.
Status: 0 of 6 demonstrated as drills on a frozen candidate (CONFIRMED by MVP_ACCEPTANCE_CHECKLIST table).

### 4.3 Fourteen-day owner trial readiness
- Prerequisite (156 pretrial cases evidenced, candidate frozen with manifest) is far: 58 registered, 0 gates above G0 passed, no evaluator.
- No trial instrumentation: nothing in `src/` writes a daily-use log, approval-burden, correction-rate or incident record (`grep -ri trial src` hits only `readiness.py`); RUNBOOK "Trial record" section is prose.
- Blocking live dependencies recorded as owner-deferred or stale: paid SDK smoke (AOS-016-TC04), actual search, real-phone setup, billing evidence stale / background OFF, earlier Claude monthly spend limit (GOAL_PROGRESS.md:7-9). `phase-tracker.json`: `candidate_commit=null`, `gate_manifest=null`.
- Estimate (PLAUSIBLE): not startable this week.

### 4.4 Fresh install / backup / restore / rollback
- No service/daemon packaging (no systemd unit anywhere outside the frozen spec reference; background controller "installs no OS service"). Reboot recovery is durable state but manual relaunch of API, server, model, DB container.
- Install friction: `uv` must be exactly 0.12.3 (`pyproject.toml:48`) and is not stated in README/SETUP (grep empty); on 0.11.32 `make`/`uv run` fail (observed). Fresh-host proof exists only for R0 (AOS-001-TC04).
- Backup/restore: only per-component pg_dump/pg_restore tests (`test_memory_restore.py`, `test_profile_vault_restore.py`, `test_quota_migration.py`, `test_returned_build_release.py`). No operator command, no whole-system backup including DBOS tables, vault key custody, artifact store and evidence. RUNBOOK:3 "planned contracts, not currently available".
- Rollback: forward-only migrations; downgrade refuses to erase phone-device history (PRIVATE_PHONE_INGRESS.md). Checklist item "backup/rollback steps and known issues list" unmet.
- Reset helper `make reset-synthetic-data` removes only the synthetic volume (good safety), but no real-data lifecycle exists.

### 4.5 Mission Control usefulness
Real but narrow: read-only observer, three-mode intakes, build review, review inbox, storage notices, phone observer behind explicit TLS ingress; ~800 TSX lines; no worker/fleet view, trace deep-links, cost-confidence or authorized/accessible/observed exposure panels (checklist: "Mission Control shows accurate status, approvals, evidence, traces, cost confidence and ... exposure separately": unmet); keyboard/contrast test (AOS-028-TC04) absent; phone not verified on a real device; not packaged with the Python distribution.

---------------------------------------------------------------------------------------------------

## 5. Findings ranked

P0 (blocks calling anything beyond G0 "done"; blocks trial start)
- F-01 CONFIRMED. No gate evaluator and case binding collapsed. 58/157 (G3), 57/72 (G1), 57/96 (G2) registered; R2 0/24, R3 0/39, revision-3 extensions 1/33; 21 of 45 planned test files do not exist; AOS-030-S1 NOT_STARTED. Evidence: `ready_G3.json` (readiness tool), `docs/testing/test-catalog.json`, `src/panestria/verification/readiness.py` docstring "never a release gate evaluator". Registration count moved 56→58 in 13 days while ~190 commits merged.
- F-02 CONFIRMED. AOS-024 Codex adapter does not exist; no ADR defers it. `grep -ri codex src tests` empty. B-1's "both pinned vendor adapters" and four live cases (AOS-024-TC04, 026-TC04, 027b-TC04, 030-TC03) cannot pass. "Two-worker" currently means two Claude workers (D1).
- F-03 CONFIRMED. No operator-grade backup/restore/rollback/upgrade/service story; RUNBOOK says "planned contracts"; migrations 40 vs runbook text 0004; no daemon. Fresh-install/backup/restore/rollback checklist block is unmet.
- F-04 CONFIRMED. Fault drills 0/6 as drills; 14-day trial cannot start (no frozen candidate, no instrumentation, owner-deferred live items: paid SDK, search, real phone, billing evidence stale / background OFF).

P1
- F-05 CONFIRMED. Status surfaces contradict each other: GOAL_PROGRESS.md:5,41; SETUP.md:3; docs/README.md:5; requirement-traceability.json 227/228 NOT_IMPLEMENTED incl. accepted R0; tracker NOT_STARTED for AOS-026/027b/029 though code and evidence exist.
- F-06 CONFIRMED. D-1 is not an end-to-end journey: AOS-023 workflow absent, search deferred, no live authorized brief retained; G2 0/24 registered.
- F-07 CONFIRMED. Build with a subscription worker is PUBLIC-synthetic only; B-1 on a real personal repo is unavailable except via local models; no recorded decision.
- F-08 CONFIRMED. Mission Control does not meet AOS-028/029 acceptance (no fleet, trace, cost, exposure UI; no keyboard/contrast test; phone unverified on device; not bundled).
- F-09 CONFIRMED. Documentation is unmaintainable (483 files in docs, 106 testing runbooks, 1,061-line progress log of "Current" sections with corrupted spacing; 7 status surfaces).
- F-10 CONFIRMED. Evidence not bound to cases: 82/171 evidence dirs referenced by manifests; 9/150 reports cite a case ID; catalog cannot represent "observed on older commit" (5 R1 cases with retained live pass remain NOT_RUN).
- F-11 CONFIRMED. MVP-X14 (REA/reuse/comparative corpus) has no deliverable beyond ADR 0005; MVP-X13 lacks predeclared host budgets and PSI usage; X13 storage notifications "partial" by the spec's own text.

P2
- F-12 CONFIRMED. Schema duplication: `docs/schemas` (stale, "AgentOS v1") vs generated `docs/contracts`; unguarded by tests; only 3 of ~65 contract models exported.
- F-13 CONFIRMED. Intermittent native-worker stop unexplained (IMPLEMENTATION_PROGRESS.md ~7, ~232); quota "urgency as reset approaches" only reports seconds-to-reset (PLAUSIBLE gap); AOS-029 spec/test conflict on Phoenix; owner conflict resolution/replanning "not implemented".
- F-14 CONFIRMED. CLI surface of 122 commands/17 sub-apps and multi-terminal setup; A-1 first run needs two terminals, UUIDs, manual model cache and Node build.
- F-15 CONFIRMED. A-1 live evidence is at `d1ee854`, not HEAD, and no hardware latency target is declared.
- F-16 CONFIRMED. Local git history grafted at PR #163 (329 commits); full provenance not auditable from this clone.
- F-17 CONFIRMED (environment). `required-version = "0.12.3"` for uv not documented; default `make`/`uv run` and 3 `tests/contract/test_aos_001_toolchain.py` tests fail on uv 0.11.32.

P3
- F-18 Formatting corruption (missing spaces) in progress docs; "Current" headings on 50 sections; historical checkpoint kept at top level.
- F-19 Positive: no R4-R7 creep; conservative `NOT_ASSESSED` labels everywhere; 85/85 registered nodes collect; schemas that exist match code; AGENTS.md workflow honored.

---------------------------------------------------------------------------------------------------

## 6. Scores (1-10, anchored)

| Dimension | Score | Justification |
|---|---|---|
| Requirements fidelity / drift | **5** | No R4-R7 scope creep in code and no weakened acceptance language; honesty labels are exemplary. But AOS-024 is absent with no decision record, "two vendors" quietly became "two Claude workers", Build is PUBLIC-only, Phoenix/Delegate-workflow reinterpretations are undocumented, and three schema trees coexist. |
| Traceability and evidence discipline | **4** | Evidence is voluminous, hash-pinned, with original failures preserved. But only 58/157 cases are bound (R2 0/24, R3 0/39, extensions 1/33), 21/45 planned test files missing, no gate evaluator, 89/171 evidence dirs unlinked, requirement-traceability says 227 NOT_IMPLEMENTED including accepted R0, and binding stalled while feature work ran. |
| Product/UX completeness of MVP journeys | **4** | A-1 works on the author's hardware; B-1 works on PUBLIC synthetic repos with Claude only; D-1 is manual stages with search deferred. Mission Control is a thin observer without trace/cost/exposure views; setup is multi-terminal CLI with UUIDs and a Node build. |
| Production readiness (product view) | **3** | Only G0 passed; G1-G3 NOT_RUN with no evaluator; no operator backup/restore/rollback/service; 0/6 fault drills run as drills; no trial instrumentation; live prerequisites deferred; one unexplained intermittent native-worker stop. Safety design is strong (fail-closed, fenced, no auto-spend) and is why this is not a 2. |
| Documentation clarity / maintainability | **3** | Accurate in detail, but 483 docs files, 106 per-PR runbooks, a 1,061-line "Current" progress log with garbled spacing, seven overlapping status surfaces and verified contradictions (SETUP, docs/README, GOAL_PROGRESS, RUNBOOK, traceability). A new owner cannot learn the true state without running the readiness tool. |

## 7. Recommended order of work (product owner view)
1. Build the gate evaluator (AOS-030-S1) and bind case IDs: add `gate_case_id` to existing research/phone/plan/quota/storage/profile tests and update `planned_nodeid`; re-baseline the catalog with a third state "OBSERVED_ON_OLDER_COMMIT". Target: registered 157/157 before any new feature.
2. Decide AOS-024 explicitly: implement the Codex adapter, or record an ADR that B-1 is Claude-plus-local and amend the checklist/gates (owner decision; do not leave silently unmet).
3. Collapse status docs to one generated page (from tracker/catalog/evidence); archive MVP_EXECUTION_CHECKPOINT, GOAL_PROGRESS and the per-PR testing runbooks under `docs/archive/`; fix SETUP/docs-README/RUNBOOK/requirement-traceability now.
4. Ship operator basics: documented uv version, one `panestria backup/restore` and upgrade/rollback procedure covering Postgres + DBOS + vault key custody + artifact store, a systemd user unit, bundled Mission Control assets.
5. Write the six-drill harness and trial logger, then run the real-phone, search and SDK live items the owner has deferred, on a frozen candidate.
