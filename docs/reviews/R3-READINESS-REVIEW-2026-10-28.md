# R3 production-readiness review: findings, scores and improvement inputs

**Date:** 2026-10-28. **Inspected source:** `main` at `33e61dc0bb254c158bed94f3677701d92d213a1e` (clean tree).
**Release verdict:** NOT_EVALUATED. This is a review, not a gate evaluation. It does not change any tracker,
catalog, gate or evidence state, and it does not relabel existing evidence.

**Review team (one lens each):** distinguished AI architect, staff QA engineer, adversarial security reviewer,
AI research engineer (process research plus AI-component review), product owner, and a code-quality metrics pass.
The lead reviewer verified the highest-impact claims, settled disagreements and set the final scores below.
The raw lens reports and the adopted process are retained in [r3-readiness-2026-10-28/](r3-readiness-2026-10-28/README.md).

Use this document as the input for a remediation plan. Section 9 already orders the work into task PRs.
The PR breakdown follows [AGENTS.md](../../AGENTS.md) and [the task PR workflow](../TASK_PR_WORKFLOW.md).

---

## 1. Verdict

**R3 is not ready for owner MVP acceptance or production use.** The repository's own records agree:
- G0 PASS; G1, G2 and G3 NOT_RUN.
- R3 is DRAFT and `mvp.candidate_commit` is null.
- No gate evaluator exists.

None of the headline status claims is false. The gap is real and measurable:

| Readiness question | Observed answer |
|---|---|
| Can G3 be evaluated mechanically? | **No.** 58/157 cases have a registered test node. R2 0/24, R3 0/39, revision-3 extensions 1/33. `verification/readiness.py` is an inventory and says it is "never a release gate evaluator". |
| Are the MVP journeys complete? | A-1 Ask works on the author's hardware, with a live 10/10 pass at an older commit. B-1 Build works with one or two **Claude** workers on PUBLIC synthetic repos only. D-1 Delegate consists of manual guided stages, with search deferred. |
| Were the six fault drills run? | 0/6 have been run as drills. Component tests exist for each. |
| Can an operator install, back up, restore, upgrade and roll back? | Not as an operator path. The runbook says the commands are "planned contracts". |
| Is the safety foundation sound? | **Yes, and it is the strongest part of the system.** In a time-boxed red-team pass, no egress/SSRF, approval-digest, phone write-path or sandbox-escape bypass was found. |

**Profile:** 12 dimensions. The lowest score is **3** (production readiness), and **11 of 12** dimensions are below the
release-grade anchor of 7. The rubric (section 2) judges readiness by the minimum and by the number of dimensions below 7,
never by an average.

**Open stop-ship (S0) findings: none.** No unauthorized effect, credential exposure, private-IP fetch, digest-mismatch
execution or false gate PASS was found.

**S1 findings:** 10. These must be fixed or explicitly decided by the owner before the 14-day trial (section 5).

---

## 2. Method and rubric

The AI research engineer surveyed how leading teams qualify agentic systems. Sources included the Google SRE PRR and launch
checklist, Google engineering-practices review, OWASP LLM Top 10 2025 and the OWASP Top 10 for Agentic Applications,
NIST AI RMF / AI 600-1, AgentDojo and InjecAgent, ALCE, RAGAS and AIS attribution, Anthropic's agent-eval guidance (pass^k),
mutation and property testing, and Jepsen-style fault injection. From that survey the team adopted this process:

0. **Prepare.** Freeze the commit, use disposable DB/ports, run default CI separately from live checks, and write a
   lethal-trifecta threat model.
1. **Map requirements.** Build the requirement → code → test → evidence matrix and script the drift checks.
2. **Adversarial break.** Attack in blast-radius order: approvals, sandbox, egress, citation verifier, durability,
   quota, phone, providers.
3. **Quality review.** Google review standard, complexity and docstring metrics, coverage, mutation and property gaps.
4. **Score.** Anchored 1-10. A score without evidence is capped at 4. An open Critical finding caps Security and
   Production readiness at 4. A PASS claim contradicted by evidence caps Requirements at 5.
5. **Triage.** S0 stop-ship, S1 before the owner trial, S2 before G3, S3 backlog. "Unverifiable here" is its own
   status and never rounds up to PASS.
6. **Plan.** One task PR per cohesive fix, with a regression test for every finding.

Rubric anchors (full table in [process-and-rubric.md](r3-readiness-2026-10-28/process-and-rubric.md)):

| Score | Anchor |
|---|---|
| 3 | Works on the happy path; failures unobserved; PASS claims without evidence. |
| 5 | Prototype-adequate: controls exist but are not enforced or independent; drills run by hand at most. |
| 7 | Release-grade for the owner trial: invariants enforced and tested, all drills automated, critical-module mutation ≥80%, known gaps bounded. |
| 9 | Independently verified: fault injection at every step, property and fuzz tests in CI, traceability enforced, independent PRR passed. |

**Sample-size honesty.** With zero failures in *n* trials, the 95% upper bound on the failure rate is about 3/*n*.
A single-owner 14-day trial can therefore expose usability failures and unknown unknowns. It cannot certify low-rate
safety properties; those must come from automated large-*n* adversarial and fault runs.

---

## 3. Final scorecard (lead-reviewer decision)

| # | Dimension | Team input | **Final** | Deciding evidence |
|---|---|---|---|---|
| 1 | Requirements fidelity / drift | PO 5 | **5** | No R4-R7 creep and no weakened acceptance text. AOS-024 is absent with no decision record. Four reinterpretations have no ADR (section 6). |
| 2 | Traceability and evidence discipline | PO 4 | **4** | 58/157 cases bound; 21/45 planned test files missing; 89/171 evidence directories unreferenced; `requirement-traceability.json` lists 227/228 as NOT_IMPLEMENTED, including accepted R0. |
| 3 | Architecture and system design | Arch 6 | **6** | The kernel primitives are excellent: caller-owned transactions, epoch fencing, one-shot digest approvals, transactional DBOS enqueue. But DBOS covers only the synthetic R0 workflow, and the task state machine is enforced only by convention. |
| 4 | Simplicity, minimalism and structure | Arch 4, CQ 4 | **4** | About 4k LOC of R0 demo code ships in the runtime package and 10 production modules import its private helpers. Other evidence: 12 `config_*` modules, 3 effect-lifecycle implementations, 3 DB access stacks, an 8-package import cycle, 483 docs files. |
| 5 | Code quality (pythonic, Google style, readability) | CQ 6/4/5 | **5** | 100% typed, mypy strict clean, ruff clean, no bare `except`. But 300 functions have cyclomatic complexity >10 (max 106), 0 of 237 eligible functions have Google `Args/Returns/Raises`, 74 files are unformatted, and 96 cross-module private imports. |
| 6 | Security and adversarial robustness | Sec 7.5 | **7** | Egress/SSRF/rebinding hold against 53 hostile addresses. No approval, phone or path bypass was found. Residuals are Medium: unbounded worker workspace, weak secret scanner, the native CLI is not an OS boundary, and the reader keeps hidden HTML text (from the AI lens). |
| 7 | Durability and reliability | Arch 6 | **5** | Crash-before/after-commit tests are real (SIGKILL). But Build and Research run in daemon threads without resume, nothing sweeps stuck effects, a permanent queue-history cap can wedge the queue, and 0/6 drills are automated (rubric caps this at 5). |
| 8 | Test effectiveness | QA 7/5/7/5/5 | **6** | Individual tests are behavioural (about 31 of 38 sampled). Negative and concurrency cases are strong. There is no Hypothesis or fuzzing, no coverage measurement in CI, mutation testing covers 3 files, and Docker boundary tests are `live`-only. |
| 9 | Efficiency and performance | Arch 5 | **5** | Fine for one user. Weak points: connection-per-call with no pool, SSE polls every 100 ms with a new connection each time, `task_event` is read by `kind`/`task_id` without indexes on an append-only table, and no predeclared host budgets (MVP-X13). |
| 10 | Operability and observability | Arch 5 | **4** | Strong typed denials, readiness probe and redacted spans. But `logging` is used in 1 module, there are 112 `except Exception`, and there is no operator backup/restore/upgrade/rollback, no service unit, and no stuck-effect report. |
| 11 | AI and eval quality (grounding, calibration) | AI 4/4/7/6/5 | **4** | The product verifies citations by exact bytes only (`semantic_support` is hard-wired to NOT_ASSESSED). Calibration rests on 36+36 SNLI caption items with 0 UNKNOWN predictions. Ask is a 10-prompt smoke test. Quota governance is the strong part (7). |
| 12 | Production readiness | PO 3 | **3** | Only G0 passed, there is no evaluator, 0/6 drills, no trial instrumentation, no operator lifecycle, the owner-deferred live items are still open, and one native-worker stop remains unexplained. |

**Where I overrode a team score:**
- **Durability, 6 → 5:** the rubric's drill cap applies because no fault drill is automated.
- **Security, 7.5 → 7:** the AI lens found that the HTML reader turns hidden text into citable passages. That is an
  indirect-injection surface the red team did not score.
- **Operability, 5 → 4:** the missing operator lifecycle (backup, restore, upgrade) is a product blocker, not only a
  design gap.

### 3.1 Per-lens sub-scores

| Lens | Sub-scores |
|---|---|
| AI architect | System design 6; modularity/boundaries 5; durability design 6; simplicity (strict) 4; efficiency design 5; operability design 5 |
| Staff QA | Test effectiveness 7; critical-path coverage 5; adversarial/negative testing 7; CI/release-gate integrity 5; test maintainability 5 |
| Security red team | Overall 7.5; sandbox/egress 8; authn/authz and API 7; secrets and privacy 7; supply chain 7 |
| AI research engineer | AI/eval 4; citation grounding 4; quota and resource governance 7; learning/data governance 6; memory and context 5 |
| Product owner | Requirements fidelity 5; traceability 4; journey completeness 4; production readiness 3; documentation 3 |
| Code quality metrics | Pythonic idiom 6; Google style 4; minimalism/complexity 4; duplication/dead code 7; readability 5 |

---

## 4. What was actually executed

Commands ran in a disposable container as root, using the pinned uv 0.12.3. The owner's review database and services
were not touched.

| Check | Result |
|---|---|
| `ruff check .` | PASS |
| `ruff format --check src tests` | **74 files would be reformatted.** The formatter is not a CI gate. |
| `mypy src/panestria` (strict) | PASS, 359 files |
| `lint-imports` | 11/11 contracts kept. There is no `layers` contract (see F-S6). |
| `tools/secret_scan.py` | PASS, but it has only 2 rules (see SEC-M4). |
| Fast lane (`ci_tests.py fast --profile full`) | 940 pass, 11 fail. 3 failures come from the host `uv` 0.11.32 on PATH and pass with 0.12.3. The other 8 come from running as root without the required platform features. The product refuses euid 0 by design, but these "unit" tests do not skip. |
| Kernel lane (Docker + PostgreSQL) | 331 pass, 32 fail, 1 error. **Environmental:** builds stop because the product refuses root and native-platform prerequisites are absent. |
| Research lane | 165 pass, 46 fail, 77 error. **Environmental:** the reader sandbox reports `reader_unavailable`, raised from a broad `except Exception` (brokers/research/reader.py:251). |
| Platform lane | 556 pass, 218 fail, 37 error. **Environmental:** the product refuses root (`root_user_denied`, `unprivileged_probe_required`), and the Mission Control dist was not built locally (`mission_build_required`). |
| Authoritative CI for this code | PR run [40066439918](https://github.com/yogeshnaren/panestria/actions/runs/40066439918) passed all four lanes for the merged content. It ran the **required** profile, which defers named regressions. |
| `main` CI for HEAD | Run [40067221126](https://github.com/yogeshnaren/panestria/actions/runs/40067221126) **skipped lint, typecheck and every behavioural lane**, reusing the PR's merge proof (see F-CI1). |
| Hermetic coverage (unit + contract only) | 32.4% line, 18.9% branch. Whole-suite coverage is measured nowhere. |
| Red-team PoCs (hermetic) | 53 hostile IPs and 6 fetch targets denied with zero `connect()`. Digest/TOCTOU, path, API Host/Origin probes run. |
| AI PoCs (hermetic) | Citation adversarial set run against `ClaimStore._assess`. Calibration fold scores recomputed (all matched the reports). Quota edge cases run. |

I could not run a non-root rerun of the integration lanes here: the environment did not permit adding a non-root user
to the Docker group. The local integration failures are therefore classified **environmental (unverifiable here)**, not
defects. The PR CI run above is the behavioural authority.

---

## 5. Consolidated findings

IDs are stable for planning. Status: **C** means confirmed by code reading or by reproduction; **P** means plausible
(inferred, not exercised).

### 5.1 S1: fix, or record an owner decision, before the 14-day trial

| ID | Finding | Evidence | Direction |
|---|---|---|---|
| **F-G1** (C) | No gate evaluator, and case binding has collapsed. 58/157 G3 cases are registered and 99 are missing. Only 85 of 2,482 collected tests carry a case ID. The count went from 56 to 58 over the 13 days in which the bulk of 329 commits landed. | `verification/readiness.py`, `docs/testing/test-catalog.json`, `release-gates.json`; readiness `--gate G3` output | Implement AOS-030-S1, the evaluator. Bind `gate_case_id` on the existing research, phone, plan, quota, storage and profile tests. Add catalog state `OBSERVED_ON_OLDER_COMMIT`. Add a CI ratchet: the registered count may never drop. |
| **F-R1** (C) | AOS-024 (the second vendor adapter) is absent and no ADR defers it. "Two-worker Build" is two Claude workers. B-1 "both pinned vendor adapters" and 4 live cases are unreachable. | `grep -ri codex src tests` finds nothing; `docs/testing/NATIVE_PLAN_EXECUTION.md` | **Owner decision:** implement it, or record an ADR that amends B-1 and the gates. |
| **F-AI1** (C) | No semantic citation verification in the product path. Exact-byte quote matching stops fabricated, wrong-quote and truncated cases. Negation flips, number changes, out-of-context quotes and off-topic claims all return EVIDENCE_PRESENT. `semantic_support` is hard-wired to NOT_ASSESSED. | `execution/research_sources.py:400`; `kernel/research_collection.py:274`; `cli/research.py:294,365` | Wire a calibrated verifier (local NLI or Sonnet behind a budget) that can output SUPPORTED/CONTRADICTED/INSUFFICIENT/UNKNOWN. Build a research-domain labeled set (≥30 per class, two annotators) with false-support rate and Wilson intervals. Keep UNKNOWN reachable. |
| **F-AI2** (C, code) | RESTRICTED/PRIVATE memory bodies are stored in plaintext with a generated `tsvector` and GIN index. This contradicts MVP-X07: "Restricted plaintext must not enter ordinary PostgreSQL FTS". | `migrations/versions/0010_memory.py:36-37,66`; `memory/service.py:59-68,186-209`; spec `05-PERSONAL-PLATFORM-REVISION-3.md:27` | Refuse RESTRICTED in `memory_source` (route it to the vault), or use encrypted storage with no FTS. Add a DB CHECK and a regression test. |
| **F-D1** (C) | MVP Build and Research are not durable workflows. They run as daemon threads or a ThreadPoolExecutor inside the API process. A restart leaves claims occupied until the owner reconciles them. DBOS covers only the synthetic queue. | `execution/mission_run.py:49-54`; `execution/native_plan.py:351`; `execution/dbos_runtime.py:14`; `kernel/scheduler.py:3-5` | **Owner decision** on the contract: Tier A DBOS-durable or Tier B owner-reconciled. At minimum, add a read-only orphan and stuck-effect report to `health` and `mission`. |
| **F-D2** (C) | `effect_outbox` has no reader or sweeper. Two of the three effect creators write no outbox row, and `SideEffectService._lock` INNER JOINs outbox, so those effects cannot be claimed or reconciled. | `kernel/effects.py:182-195`; `kernel/repositories/approvals.py:260-270`; `execution/task_workflow.py:162-185` | One `EffectLedger` (create, claim, finish, reconcile, `list_stuck`) that always writes the outbox row. |
| **F-D3** (C) | The task state machine is enforced by convention. There are 26 raw `UPDATE … SET state` sites in 15 files, `ALLOWED_TRANSITIONS` is checked in 8 places, and no DB trigger guards transitions. | `contracts/task.py:38`; `kernel/effects.py:236-272`; `kernel/build.py:535-540` | One `TaskMachine.transition()` with CAS on `row_version`, plus a `BEFORE UPDATE OF state` trigger generated from the same table. Roll out in warn mode first. |
| **F-D4** (C code, P impact) | The background queue can be permanently wedged. The cap counts all-time immutable `background.queued` events (>256 means deny forever), and the run history cap is 16. Nothing retires these events. | `kernel/background.py:28-35`; `kernel/background_run.py` | Count live rows from a state table, and move queue and run lifecycle out of event `kind` strings. |
| **F-O1** (C) | There is no operator lifecycle: no `backup`, `restore`, `upgrade`, `rollback` or service unit. The runbook says "planned contracts", and its migration list stops at 0004 while the head is 0040. | `docs/operations/RUNBOOK-AND-RELEASE.md:3,~40` | One `panestria backup/restore` covering Postgres (including DBOS tables), vault key custody, the artifact store and evidence. Add a documented upgrade/rollback, a systemd user unit and bundled Mission Control assets. |
| **F-CI1** (C) | CI integrity has three gaps. (1) `main` runs reuse the PR's merge proof without checking its profile, so the 46 regressions deferred under the `required` profile may never run on `main`. (2) Sandbox OS-boundary tests (Docker uid, mounts, egress, limits, cancellation) are `live` and never run in CI, even though CI builds the worker image. (3) No coverage is measured. | `tools/ci_merge_proof.py`; `tools/ci_tests.py:89-137`; run 40067221126; `tests/integration/test_aos_008.py` markers | Make merge-proof require `deferred == []` or add a nightly full run on `main`. Add a `docker_boundary` marker that runs in the platform lane. Report coverage and set a floor on critical packages. |

Two further items are S1 by the checklist but are capability gaps rather than defects:
- **F-P1:** fault drills are 0/6 and trial instrumentation does not exist.
- **F-P2:** D-1 is not an end-to-end journey (AOS-023 workflow absent, search deferred).

Both are scheduled in section 9.

### 5.2 S2: fix before G3

| ID | Finding | Evidence |
|---|---|---|
| SEC-M1 (C) | Worker RW `/workspace` has no size quota or `--ulimit fsize`; a 30 s `dd` can fill the host disk. `ArtifactIngress._read_source` does an unbounded `read_bytes()`. | `sandbox/runner.py:165-197` |
| SEC-M4 (C, PoC) | The secret scanner has only PKCS#8 and `AKIA` rules. It misses RSA/OpenSSH keys, `sk-ant-` and `ghp_`, and does not scan history. | `tools/secret_scan.py` |
| SEC-M2 (P) | The egress gateway is a raw CONNECT to Anthropic hosts with no SNI/Host enforcement. Not wired to `src/` callers yet; fix before wiring. | `sandbox/egress.py:117-168` |
| SEC-M3 (P, design) | The native Claude CLI runs as the owner uid with full filesystem and network. Containment relies on flags, a hash pin and post-hoc stream parsing. This needs an explicit owner-accepted residual-risk record, or an OS sandbox. | `brokers/harness/process_runner.py` docstring |
| AI-P2a (C, PoC) | The HTML reader keeps `display:none`, `hidden`, off-screen and white-on-white text as citable passages (indirect-injection and citation-laundering surface). | `brokers/research/reader_worker.py:37` |
| AI-P2b (C) | Memory `correct()` resets status to ACTIVE, which silently un-suppresses an item. `conflict_key` is never enforced. There is no physical purge path. | `memory/service.py:147` |
| AI-P2c (C) | Ask quality is a 10-prompt smoke test. The injection case has `expect: null`, `quality_pass: True` is hard-coded after the asserts, and cited source IDs are not validated. | Ask qualification fixture and report |
| AI-P2d (C) | Curated training-example origin is self-attested JSON with no cross-check against recorded model outputs, so a model answer can be relabelled OWNER_AUTHORED. | `learning/curation.py` |
| AI-P2e (C) | "40%-before-reset" is a static 20% reserve plus a tiebreak ordering. There is no pacing toward reset. | `kernel/background_run.py:68`; `kernel/background.py:273` |
| ARCH-P1-4 (C) | `task_event` has only `(goal_id, seq)` and `seq` indexes but is filtered by `kind`, `task_id` and payload, including a global anti-join on every background `start`. | `0002_kernel.py:238`; `kernel/background_run.py:312-316` |
| ARCH-P2-5 (C) | 9 side tables take `seq` from the event sequence outside the ADR-0002 lock, so those values are not commit-ordered. Harmless today; it breaks the cursor guarantee as soon as anyone replays by them. | `0023`–`0027`, `0039`; `kernel/research_requests.py:45-52` |
| ARCH-P2-6 (C) | SSE polls every 100 ms with a new DB connection per page and re-authorises per event, with no LISTEN/NOTIFY. | `api/event_stream.py:56-77` |
| QA-5 (C) | Five `BrowserSecurity` rejection branches have no test: 431 headers too large, ambiguous Host/Origin, invalid query, 408 deadline, 422 body. | `api/security.py` |
| QA-9 (C) | `effect_digest` hashes `model_dump_json()` with no golden vector, so a pydantic upgrade could change every digest with all tests green. | `contracts/approval.py:19-67` |
| QA-4 (C) | No Hypothesis or fuzz tests on trust-boundary parsers: digest canonicalisation, `parse_cursor`, `decode_frame`, the HTTP parser, NFC offsets, `validate_dag`, `_public_unicast`. | `pyproject.toml` dev group |
| SEC-L1 (C, PoC) | `/openapi.json`, `/healthz` and `/readyz` answer to any Host header, and the 422 response echoes input before auth. | `api/main.py:49` |
| SEC-L2 (C, PoC) | The candidate-tree path denylist is case-sensitive: `.GIT/config`, `.Claude/settings.json` and `.MCP.json` are accepted. `.github/workflows`, `.husky` and `CLAUDE.md` are not flagged. | `verification/git_snapshot.py:114` |
| PO-F05 (C) | Status documents contradict each other: GOAL_PROGRESS says "R2/R3 not begun", SETUP says "R0 is not accepted", and the tracker shows AOS-026/027b/029 NOT_STARTED although code and evidence exist. | `docs/GOAL_PROGRESS.md:41`, `docs/SETUP.md:3`, `docs/phase-tracker.json` |
| PO-F17 (C) | uv is pinned to exactly 0.12.3, but README and SETUP do not say so; `make` and `uv run` fail on other versions. | `pyproject.toml:48` |
| QA-8 (C) | "Unit" tests fail as root or with a different uv instead of skipping with a reason. | 8 + 3 fast-lane failures |
| QA-10 (C) | Fixed test ports (55439/55440, 8765-8769), contrary to the AGENTS.md disposable-port rule. Mutation testing covers 3 files and is manual-only. | `tests/stack_support.py`; `pyproject.toml [tool.mutmut]` |

### 5.3 S3: backlog

- Smaller security items:
  - `require_current_policy` skips the check when the version is 0.
  - `ActionPreview.expires_at` accepts year 9999.
  - Phone pairing is capped at 256 lifetime devices with no prune path.
  - The R0 `serve.py` has no read timeouts.
  - The host `ollama` binary is mounted unpinned.
- 1,143 stringly typed `KernelDenied("…")` codes. Proposed fix: a `DenyCode` StrEnum.
- 112 `except Exception` blocks with almost no logging. `cli/plan.py` has 18 that collapse to one message.
- 74 files are unformatted. Docstrings miss Google sections on every eligible function; public function and class
  docstring coverage is 19% and 6%.
- 54 functions are over 100 lines. Examples: `event_parser._frame` (CC 106), `cli/tui.run` (CC 104).
- Context budgeting treats UTF-8 bytes as tokens. Memory recall is lexical FTS only.
- `docs/schemas/` is stale (the "AgentOS v1" shape), unguarded and duplicates the generated `docs/contracts/`.

The full lists, with file:line, are in the lens reports.

---

## 6. Drift register (specification vs implementation)

Every row needs either a code change or an owner-recorded ADR. Silent drift is the finding.

| ID | Spec says | Implementation does | Required action |
|---|---|---|---|
| D1 | AOS-024: a second approved vendor adapter under the same worker contract; B-1 needs both | Two Claude workers | Owner decision plus ADR (F-R1) |
| D2 | Build on the owner's work, with trust/privacy/autonomy axes | Subscription-worker Build runs on PUBLIC synthetic repos only; private data only via local models | ADR stating the B-1 scope for the MVP |
| D3 | AOS-029-TC04: pinned local Phoenix | Bounded local OTel spans (`telemetry/tracing.py`) | ADR, and amend TC04 or add Phoenix |
| D4 | AOS-023: bounded Delegate planner/workflow | Manual guided stages; search owner-deferred | Implement, or narrow D-1 by ADR |
| D5 | MVP-X11: urgency increases as the reported reset approaches | Static reserve plus reported seconds-to-reset | Implement pacing (AI-P2e) |
| D6 | MVP-X07: no restricted plaintext in PostgreSQL FTS | Plaintext `tsvector` on all memory labels | Fix (F-AI2) |
| D7 | AOS-028: one Mission Control with status, approvals, evidence, traces, cost confidence and exposure | About 800 TSX lines: an observer plus intakes, no trace/cost/exposure/fleet views; 17 CLI sub-apps and 122 commands carry the real UX | Close the AOS-028/029 views; decide which CLI flows to retire |
| D8 | MVP-X13: predeclared host budgets, honest PSI use | No budgets document; no PSI | Declare budgets and measure them on the target host |
| D9 | MVP-X14: REA decisions, parity and rollback evidence, comparative corpus | ADR 0005 only | Owner decision on scope |

No R4-R7 scope creep exists in `src/` or Mission Control (grep for vllm, lora, tts, computer-use, forecast and
langgraph found nothing). `sota_implementation_authorized=false` is respected.

---

## 7. Lean-structure plan (owner priority: clean, lean, easy for anyone to work in)

The verdict is that the code is careful but carries scaffolding and duplication that make it harder than necessary to
navigate. Targets: about 10% less runtime code, one way to do each core thing, enforced layering, and guardrails so the
codebase stays lean.

| # | Move | Value | Risk | Est. runtime LOC |
|---|---|---|---|---|
| L1 | Move `_lock/_private/_atomic/_git` from `execution/proposal_demo.py` into a public `platform/fsutil.py`. Then move `synthetic_journey`, `proposal_demo`, `api/proposal_demo`, `cli/review_demo`, `demo.py`, `review.py` and `brokers/harness/mock.py` into a `devkit/` excluded from the wheel. Keep the R0 tests by pointing them at `devkit`, and preserve R0 evidence. | Very high | Low (helpers), then Medium (move) | about −3,800 |
| L2 | One `EffectLedger` (absorbs F-D2) | High | Medium | about −400 |
| L3 | One `TaskMachine.transition()` plus a generated DB trigger (absorbs F-D3) | High | Medium-high | about −300 |
| L4 | Turn the 12 `config_*.py` modules into a `config/` package (`files.py`, `env.py`, `local.py`, `build.py`, `research.py`, `phone.py`) with one exception type and one port table. Remove the 4 copies of the token regex and the conflicting 8766/8768 ports. | Medium-high | Low | about −350 |
| L5 | One `db.py`: pooled `connect(role)`, one `append_event` (replacing the psycopg and SQLAlchemy copies), and no per-call `create_engine` | Medium-high | Low-medium | about −250 |
| L6 | Add an import-linter `layers` contract and break the 8-package cycle. Move `sandbox/artifact_ingress` to `execution`, move `kernel/ask` orchestration to `execution/ask`, and make shared route helpers public in `api/deps.py`. | High | Low-medium | 0 |
| L7 | Organise by feature inside layers: `kernel/{core,build,research,background,ask}/`, with the same split in `execution/` and `contracts/`. Today's directories hold 56-61 files each. | High (onboarding) | Low (moves only) | 0 |
| L8 | One `create_app(profile)` factory replacing six FastAPI app builders, with golden tests for security headers | Medium | Medium | about −400 |
| L9 | Merge the near-duplicates: activity/review_inbox, the 7 `_sha` helpers, and the hashing helpers into `contracts/canonical.py`. Delete the confirmed dead code (about 34 LOC). | Low-medium | Low | about −330 |
| L10 | Refactor the 10 functions over 150 lines. Table-drive `ClaudeEventParser._frame`; split `DockerSandbox._execute` into launch, attach and settle. | Medium | Medium | about −300 to −500 |
| L11 | Fold micro-packages: `ops` (41 LOC) into `devkit`/`cli`; `policy`, `kernel/policy.py` and `kernel/repositories/policy.py` into one `policy` package | Low | Low | about −50 |
| L12 | Docs: generate one status page from tracker, catalog and evidence. Archive GOAL_PROGRESS, MVP_EXECUTION_CHECKPOINT, IMPLEMENTATION_PROGRESS narrative and the 106 per-PR testing runbooks under `docs/archive/`, unchanged. Regenerate ARCHITECTURE.md from the import graph and `alembic heads`. Remove or guard `docs/schemas/`. | High | None (docs; preserve originals) | docs only |

Target layout (layer rule enforced by `lint-imports`: `api|cli > execution > brokers|verification|memory|learning|inference > kernel > sandbox|policy > platform > contracts`):

```
src/panestria/
  contracts/   pure pydantic models grouped by domain
  platform/    config/, db.py, errors.py (KernelDenied, DenyCode, Actor), fsutil.py, locks.py, hashing.py, tracing.py
  policy/      engine, labels, profiles
  kernel/      core/ (goals, TaskMachine, approvals, leases, EffectLedger, events) + build/ research/ background/ ask/ plans/
  sandbox/  verification/  brokers/  inference/  memory/  learning/
  execution/   orchestration by feature: research/ build/ native/ background/ profile/ ask/ workflow/
  api/         deps.py, create_app(profile), routes/
  cli/         thin Typer wrappers over execution services
devkit/        (outside the wheel) R0 synthetic journey, proposal demo, mock worker
```

**Guardrails that keep it lean**, all added to CI:
- `ruff format --check`.
- Ruff `C901` with `max-complexity = 15`, ratcheted down. `PLR0913` for parameter count. `D` with the Google convention
  on public API only.
- The `layers` contract.
- A test that ARCHITECTURE.md's Alembic head matches `alembic heads`.
- A LOC/complexity budget report on every PR.

---

## 8. Test-strategy changes (tests that matter, not tests for their own sake)

Keep: real-Postgres concurrency with barriers, SIGKILL crash injection, the unsafe-IP corpus, and the approval
negative-case suite. Change:

1. **Bind before adding.** Add `gate_case_id` to existing tests before writing new ones (F-G1).
2. **Property and fuzz tests** with Hypothesis (dev dependency):
   - digest canonicalisation injectivity plus a **golden vector**;
   - `parse_cursor`, `validate_dag` and `_public_unicast`;
   - NFC offsets;
   - a stateful machine for the approval/effect lifecycle and the task transitions.
3. **Mutation.** Extend `mutmut` to `kernel/approvals.py`, `kernel/effects.py`, `kernel/leases.py`, `api/security.py`,
   `verification/merge.py` and the quota math. Target ≥80% before the trial and run it nightly.
4. **Docker boundary lane.** Run the `test_aos_008`, `test_sandboxed_verifier`, `test_native_tool_gateway` and
   `test_sandbox_cancellation` OS-boundary tests in CI's platform lane; CI already builds the image.
5. **Fault-drill harness (AOS-030).** Turn the six drills into automated, repeatable scenarios with invariant checkers:
   no lost task, no duplicate effect, no stuck RUNNING. Run them on the frozen candidate.
6. **AI evals.**
   - A versioned research-domain citation set with hard negatives (negation, number, scope, out-of-context, hidden text).
   - Report false-support rate with Wilson intervals and pass^k (k≥5) for model-judged paths.
   - Grow the Ask set beyond 10 prompts and assert cited source IDs.
7. **Hermeticity.**
   - "Unit" tests skip with a reason on root or an unsupported platform.
   - Tests resolve `uv` from the venv, not `PATH`.
   - Ports are allocated dynamically.
8. **Coverage as a floor, not a goal.** Measure whole-suite coverage in CI and fail on regression in critical packages
   only.
9. **Delete or fold weak tests.** Delete or fold the roughly 5 weak or implementation-mirroring tests found in the
   sample; the QA report lists them.

---

## 9. Remediation plan inputs (ordered waves; one task PR per row)

Each row is a cohesive `task/<name>` branch from current `main`. Stacked PRs name their prerequisite. Implementation and
tests go in separate, clear commits, and each PR ends with actual CI evidence. Effort: S ≈ ≤1 day, M ≈ 2-3 days,
L ≈ 1 week+.

**Wave 0: owner decisions (no code; unblock everything else)**
- OD-1: AOS-024 second vendor. Implement it, or amend B-1 and the gates by ADR. (F-R1, D1)
- OD-2: durability contract for Build and Research: Tier A (DBOS-durable) or Tier B (owner-reconciled with automatic
  stuck-work reporting). (F-D1)
- OD-3: B-1 privacy scope (D2), Phoenix vs OTel (D3), D-1 scope (D4), MVP-X14 scope (D9).
- OD-4: accept or mitigate the residual risk of the native CLI running unsandboxed. (SEC-M3)

**Wave 1: truth and guardrails (S/M; can run in parallel)**
1. `task/ci-main-full-regression`: merge-proof requires `deferred == []`, or a nightly full run on `main`.
   Add `ruff format` and coverage reporting. (F-CI1)
2. `task/format-baseline`: a format-only commit for the 74 files, with no logic change.
3. `task/docker-boundary-lane`: move the OS-boundary tests from `live` to a `docker_boundary` marker in the platform
   lane. (F-CI1)
4. `task/status-truth`: fix SETUP, docs/README, GOAL_PROGRESS, RUNBOOK, the tracker NOT_STARTED rows and the uv
   version note. Archive superseded status docs unchanged. (PO-F05, PO-F17, L12)
5. `task/test-hermeticity`: root and platform skips, venv `uv`, dynamic ports. (QA-8, QA-10)
6. `task/secret-scan-rules`: add RSA/OpenSSH, `sk-ant-` and `ghp_` rules, plus an optional history scan. (SEC-M4)

**Wave 2: correctness and privacy blockers (M)**
7. `task/memory-restricted-fts`: block RESTRICTED from FTS memory, fix `correct()` un-suppression and enforce
   `conflict_key`. (F-AI2, AI-P2b)
8. `task/task-state-machine`: `TaskMachine` plus a trigger in warn mode, then enforce. (F-D3, L3)
9. `task/effect-ledger`: a single creator that always writes the outbox row, plus `list_stuck` surfaced in health and
   mission. (F-D2, L2)
10. `task/background-live-caps`: state-table counts instead of all-time event counts, plus the `task_event` indexes.
    (F-D4, ARCH-P1-4)
11. `task/workspace-quota`: workspace size limit and bounded ingress read. (SEC-M1)
12. `task/reader-visible-text`: drop hidden and off-screen text from citable passages. (AI-P2a)
13. `task/security-lows`: Host check on openapi and health, case-insensitive path denylist, `expires_at` bound, policy
    version 0. (SEC-L1, SEC-L2, S3)
14. `task/digest-golden-and-properties`: golden vector plus Hypothesis tests on the trust-boundary parsers.
    (QA-4, QA-9, QA-5)

**Wave 3: lean structure (M/L; behaviour-preserving, each PR green on its own)**
15. `task/platform-fsutil` (L1a), then 16. `task/devkit-split` (L1b).
17. `task/config-package` (L4).
18. `task/db-module` (L5), with SSE LISTEN/NOTIFY as a follow-up PR. (ARCH-P2-6)
19. `task/layers-contract` (L6), then 20. `task/feature-folders` (L7).
21. `task/app-factory` (L8).
22. `task/dedupe-and-dead-code` (L9).
23. `task/complexity-ratchet` (L10 plus the C901/PLR/D gates).

**Wave 4: gate machinery and evidence (L)**
24. `task/gate-case-binding`: bind all existing tests and add the `OBSERVED_ON_OLDER_COMMIT` state. (F-G1)
25. `task/gate-evaluator`: AOS-030-S1. (F-G1)
26. `task/fault-drill-harness`: the six drills, automated. (F-P1)
27. `task/semantic-citation-verifier` with a labeled research set and calibration report. (F-AI1)
28. `task/trial-instrumentation`: daily-use, approval-burden, correction and incident log. (F-P1)
29. `task/operator-lifecycle`: backup, restore, upgrade, rollback, a systemd user unit and bundled Mission Control.
    (F-O1)

**Wave 5: capability completion (decided in wave 0)**
- AOS-024, the AOS-023 Delegate workflow, AOS-028/029 views, X11 reset pacing, X13 budgets and the X14 deliverables.
  (D-rows)
- Then freeze a candidate, run all 157 cases, run the six drills and start the 14-day trial.

**Re-score exit criteria:**
- No S0 or S1 open.
- Minimum dimension ≥7 under the rubric caps.
- G3 evaluator returns PASS on one frozen candidate whose evidence is bound to that commit.

---

## 10. Strengths to preserve

- **Honest status discipline.** Reports carry NOT_ASSESSED and "remaining" lists, original failures are preserved, and no
  relabelled evidence was found.
- **Safety kernel.**
  - One-shot, digest-bound approvals, re-checked at claim, with `update-ref` CAS.
  - Epoch-fenced leases and effects.
  - Atomic state/event/result commit.
  - A commit-ordered `task_event` cursor (ADR 0002).
  - Transactional DBOS enqueue.
- **Egress.** Single resolution, all-public answers, numeric connect, peer re-verified before and after TLS, every
  redirect re-validated.
- **Sandboxing.**
  - Network-none readers with a hash-pinned pypdf bundle and hard limits.
  - Digest-pinned images.
  - No `shell=True`, `pickle` or unsafe extraction.
- **Quota.** Distinct quota lanes and a fail-closed billing boundary. No paid-spillover or provider-switch path.
- **Typing and boundaries.** Strict typing throughout; leaf-clean `contracts/` and `policy/`; bounded SQL.

## 11. Limits of this review

- Integration lanes could not run as non-root here (section 4). Results rely on PR CI for behaviour.
- No live provider, search, phone device, GPU or paid call was used. Live cases remain unverifiable here by design.
- Some external standards pages could not be fetched; references are tagged `[F]` (fetched) or `[K]` (from knowledge)
  in the process document.
- Local git history is grafted at PR #163 (2026-10-21), so earlier provenance was not audited.
- Severity and score calls are the lead reviewer's. Lens reports keep each reviewer's original reasoning for audit.
