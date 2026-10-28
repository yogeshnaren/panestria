# Panestria R3 remediation plan: from the 2026-10-28 review to a 9-10 candidate

## Context

The 2026-10-28 multi-lens review (`docs/reviews/R3-READINESS-REVIEW-2026-10-28.md`, at `main` `33e61dc`) found R3 not production-ready.
- **Score profile:** minimum 3; 11 of 12 dimensions below 7.
- **What is sound:** the safety kernel (digest-bound approvals, epoch fencing, egress, sandbox).
- **What is weak:**
  - gate/evidence machinery: 58/157 cases bound, no evaluator;
  - durability: Build and Research run in threads; no outbox sweeper; state machine enforced by convention only;
  - AI grounding: exact-byte quote matching only;
  - privacy: RESTRICTED memory is stored in plaintext with full-text search;
  - operator lifecycle;
  - CI integrity: `main` reuses PR runs that deferred 46 tests;
  - leanness: about 4k LOC of demo code in the runtime, sprawl;
  - docs: 483 files, contradictory status pages, a developer-grade README.

The owner wants every rubric dimension pushed toward 9-10, code and tests fixed, everything re-tested with no breaking changes, docs cleaned up, and a README fit for production users.

**Owner decisions recorded** (2026-10-28):
- **OD-1** Implement the AOS-024 Codex adapter.
- **OD-2** Full DBOS durability for Build and Research.
- **OD-3** OS-sandbox the native Claude and Codex CLIs, with SNI enforcement.
- **OD-4** Allow private-repo Build via explicit grants: INTERNAL may use cloud workers; CONFIDENTIAL and RESTRICTED stay on local models.

**Defaults I chose:**
- AOS-029 keeps local OTel, with an ADR amending TC04.
- AOS-023 Delegate workflow is implemented.
- X11 reset pacing is implemented.
- X14 is delivered as REA reuse records.

## Ground rules

- **Repo rules (AGENTS.md):**
  - One `task/<name>` branch and PR per cohesive task, from `main` or a named prerequisite.
  - Implementation, tests and fixes in separate clear commits; no squash or history rewrite.
  - Draft PRs while unfinished.
  - No relabelled evidence; specs and evidence are append-only.
  - Disposable DB projects and ports.
  - No R4-R7 code. Never start the trial or record acceptance for the owner.
- **Branches:** approving this plan authorises pushing the `task/*` branches and opening PRs. This plan and the review stay on `claude/epic-davinci-7xkfbz`. Step 1 commits this plan as `docs/project/R3-REMEDIATION-PLAN.md`.
- **Safety net first:** no structural refactor merges before Phase 0 is green on `main`.
- **Characterise before moving:** golden or characterisation tests go in before any move or split.
- **Regression test per finding:** every finding gets a test named after its ID (e.g. `test_sec_l2_casefold_denylist`).
- **Behaviour-preserving PRs must show zero diff** against the Phase-0 baseline (`tools/compat_check.py`) in:
  - `docs/api/openapi.json`;
  - the CLI surface snapshot;
  - the schema fingerprint and snapshot;
  - the deny-code set;
  - the digest golden vectors;
  - the JUnit node set (pass count never drops).

  Feature PRs declare intended diffs in `docs/testing/compat-exceptions.json`.
- **CI profile:** each PR is green under the **full** profile, which includes the new boundary lane.
- **Additive contracts:** new enum values only; old values stay readable. New profile fields are omitted when default so historical digests are preserved.
- **No silent fallback:** a missing second vendor gives WAIT; an unavailable verifier gives UNKNOWN; missing PSI gives `psi_unavailable`.
- **Migration train:** one migration-bearing PR in final review at a time. Its number is assigned at rebase. Each regenerates `migrations/schema_fingerprint.txt` and `docs/contracts/schema-snapshot.txt` and adds an N-1 upgrade test.
- **Native re-qualification:** `runtime_versions()` hashes all of `src/`, so the native runtimes are re-qualified once, on the frozen candidate.

## Phase 0: safety net (about 2 weeks, 10 PRs)

| PR | Scope (key files) | Acceptance |
|---|---|---|
| 0.1 `task/adr-owner-decisions` | ADRs 0008-0015 for OD-1..4, D3 (local OTel), D4 (Delegate), D5 (pacing) and D9 (X14). Each records decision, alternatives and residual risk. | Every drift row D1-D9 maps to an ADR. |
| 0.2 `task/ci-main-full-regression` | `tools/ci_merge_proof.py` downloads the lane `selection.json` and reuses a run only if `profile=="full"` or `deferred==[]`, **and** `ci.yml` is unchanged. Fix the `workflow_dispatch` base bug: empty `CI_BASE` falls back to full. New `.github/workflows/nightly.yml` runs the full profile on main plus boundary, mutation, Hypothesis-nightly and the history secret scan. | `tests/unit/test_ci_merge_proof.py`: required+deferred → run; full → reuse; expired artifact → run; ci.yml changed → run. |
| 0.3 `task/format-baseline` | `ruff format` on the 74 files; CI `ruff format --check src tests tools`; `.git-blame-ignore-revs`. | `tools/ast_equal.py` proves the AST is unchanged. |
| 0.4 `task/test-hermeticity` | A `tests/conftest.py` plugin with: `requires_nonroot`/`requires_platform` (skip locally, **fail** under `PANESTRIA_CI=1`); `unit`/`contract` markers applied by directory; a `uv_bin` fixture (venv sibling, version-checked); a `free_port()` fixture. Dynamic ports for `tests/stack_support.py` (55440) and `tests/integration/conftest.py` (55439), dropping the `:55440` assert. Replace the 8765-8769 literals. Add `pytest-timeout`. Inject a clock at `test_invocations.py:153`. | Fast lane fully green as root (reasoned skips) and as non-root. `tools/junit_guard.py` fails CI on unexpected skip or xfail. |
| 0.5 `task/coverage-hypothesis-infra` | Dev deps: `hypothesis`, `pytest-cov`, `pytest-timeout`. `[tool.coverage]` with branch coverage. Per-lane `.coverage` files plus a combine job. `tools/coverage_floor.py` with `docs/testing/coverage-floors.json` (ratchet up only). Hypothesis profiles `ci` and `nightly`. | A floor regression fails CI. |
| 0.6 `task/regression-baseline-tooling` | `tools/regression_snapshot.py` and `tools/compat_check.py`. They capture JUnit node sets, the openapi hash, the CLI help tree (`docs/api/cli-surface.json`), `KernelDenied` literals, schema fingerprint and snapshot, contract-schema hashes, digest vectors and the import graph. Record new evidence `evidence/regression-baseline-<date>-<sha>/`. | `tests/contract/test_cli_surface.py` golden. compat_check blocks from Wave 2. |
| 0.7 `task/docker-boundary-lane` | New `docker_boundary` marker and `boundary` suite in `tools/ci_tests.py`; the other lanes run `-m "not live and not docker_boundary"`. Add a 5th CI matrix lane, and update `ci_merge_proof.REQUIRED` to match. Re-mark `test_aos_008` (:52,117,183,206), `test_sandbox_cancellation` (:71,111,127), `test_sandboxed_verifier:13`, `test_native_tool_gateway` (:381,431,459) and `test_aos_027a:172`. **Split** (not downgrade) any case that the catalog requires as live. | Boundary lane green; the readiness live-annotation guards still pass. |
| 0.8 `task/secret-scan-rules` | `tools/secret_scan.py` gains: all `BEGIN .*PRIVATE KEY` headers; `sk-ant-`, `sk-proj-`, `ghp_`, `github_pat_` and `xox*` tokens; JWTs; entropy-gated `*_KEY=`; and a `--history` mode (nightly). Move the rules to `platform/secret_rules.py` for runtime reuse. Add `.gitignore` entries for `*.pem`, `*.key` and `*.token`. | One sentinel per rule, generated at runtime. |
| 0.9 `task/supply-chain-scan` | Nightly `pip-audit` or `osv-scanner`; a CycloneDX SBOM script; `actionlint` and `zizmor` (replacing the text grep at `test_aos_001_toolchain.py:58`); major-version upper bounds in `pyproject.toml`. | Workflow lint green. |
| 0.10 `task/status-truth` | Truth fixes only: `docs/SETUP.md:3`, `docs/README.md:5`, `GOAL_PROGRESS.md:41`, the RUNBOOK migration head (0040), `SECURITY.md:17` (phone exists), and tracker rows AOS-026, AOS-027b and AOS-029 set to IN_PROGRESS with evidence. README and SETUP state uv 0.12.3, Docker and Node `^20.19 \|\| >=22.12`. | — |

**Exit:** Phase 0 merged, nightly full run green twice, baseline recorded.

**The standard no-break command**, exposed as `make ci-full`:

```bash
uv run --frozen python tools/ci_tests.py <fast|kernel|platform|research|boundary> --profile full && uv run --frozen python tools/compat_check.py --baseline evidence/regression-baseline-<sha>
```

## Wave 1: correctness, privacy and security blockers (parallel after Phase 0)

- **1.1 `task/digest-golden-and-properties`** (QA-4/5/9)
  - Golden vectors in `tests/fixtures/golden/digests-v1.json` for `effect_digest`, `contract_sha256`, `canonical_sha256` and `SandboxProfile.sha256`.
  - Hypothesis properties:
    - digest injectivity and key-order invariance;
    - `parse_cursor` round-trip;
    - `decode_frame`;
    - `validate_dag` against a reference implementation;
    - `_public_unicast` against IANA special ranges;
    - NFC offsets;
    - an HTTP smuggling corpus.
  - New `tests/unit/test_browser_security.py` for the five untested `api/security.py` branches.
- **1.2 `task/memory-restricted-fts`** (F-AI2, AI-P2b, D6)
  - **Migration:**
    - replace the generated `search_document` with a trigger-populated one, NULL for RESTRICTED/PRIVATE/UNKNOWN (the label lives on `memory_source`);
    - backfill with `immutable_memory` disabled inside the migration transaction;
    - partial GIN index;
    - trigger rejecting new RESTRICTED/PRIVATE `memory_source` rows.
  - **Code:**
    - `memory/service.py` `add` denies `memory_restricted_requires_vault`;
    - `correct()` (:147) refuses SUPPRESSED items, and an explicit `unsuppress` is added;
    - `conflict_key` is latest-wins in `memory/context.py`;
    - purge goes through one SECURITY DEFINER function plus a tombstone;
    - the routes at `api/routes/memory.py:37` and `memory_v2.py:73` return a typed deny.
- **1.3 `task/reader-visible-text`** (AI-P2a)
  - `reader_worker.py` `_Visible` drops:
    - the `hidden` attribute and `aria-hidden`;
    - inline `display:none`, `visibility:hidden`, `opacity:0` and `font-size:0`;
    - off-screen and clip positioning;
    - white-on-white text;
    - zero-width characters.
  - Add `hidden_bytes_dropped` to the receipt, plus `tests/fixtures/reader/hidden-*.html`.
- **1.4 `task/workspace-quota`** (SEC-M1)
  - `SandboxProfile.workspace_bytes` (omitted from the digest when default).
  - `sandbox/runner.py:165-197` adds `--ulimit fsize` plus a scandir watchdog raising `workspace_quota_exceeded`.
  - Streaming capped read in `artifact_ingress._read_source`.
  - Test: a boundary-lane `dd` fill is stopped.
- **1.5 `task/security-lows`** (SEC-L1/L2, S3)
  - **API:** `openapi_url=None` and a Host allow-list on all routes; validation errors only after auth.
  - **Path denylist** (`git_snapshot.py:114`, `runner.py:136`): casefold, NFKC and trailing-dot normalisation.
    - A review-required path set (`.github/workflows`, `.husky`, `.vscode`, `CLAUDE.md`, `AGENTS.md`, `.gitmodules`) is bound into the approval preview.
  - **`ActionPreview`:** a TTL bound on `expires_at`, an ASCII destination and a 40-hex base.
  - **Other lows:**
    - deny policy version 0;
    - phone cap counts active devices only, with a `prune` command;
    - pin the ollama binary hash;
    - IDNA UTS46;
    - assert SecurityOpt;
    - read timeouts in `serve.py`.
- **1.6 `task/background-live-caps`** (F-D4, ARCH-P1-4)
  - New state tables `background_queue_item` and `background_run`, backfilled.
  - Indexes `(task_id,kind,seq)` and `(kind,goal_id,seq)` on `task_event`.
  - Caps count live rows (`background.py:26-35,127`, `background_run.py:116-124,319`, `background_account.py:66-70`).
  - Replace the global anti-join at `background_run.py:312-314` and the N+1 at :89.
  - Tests: 300 enqueue/withdraw cycles never wedge the queue; EXPLAIN index-plan asserts.
- **1.7 `task/side-table-seq-order`** (ARCH-P2-5)
  - Drop the `nextval` default on the 9 side tables; insert the side row after `append_event`, using its seq.
  - Barrier concurrency test.
- **1.8 `task/quota-pacing`** (AI-P2e, D5)
  - X11 pacing rule in `kernel/background.py` and `background_run.py:68`: run only when remaining minus reserve is at least the projected use before reset, or inside the urgency window.
  - 6 h freshness cap, ±5 s clock-skew tolerance.
  - Additive confidence values `OWNER_REPORTED` and `PROVIDER_REPORTED`.
  - Hypothesis: UNKNOWN is never treated as plenty.
- **1.9 `task/curation-lineage`** (AI-P2d)
  - `learning/curation.py` denies any content whose sha matches a recorded model output.
  - Shingle near-duplicates go into the same fold; the secret scan runs on candidates.
- **1.10 `task/ask-eval-golden`** (AI-P2c)
  - ≥50-case `tests/fixtures/ask/golden-v1.json`.
  - Grader `verification/ask_eval.py`: cited IDs must be a subset of the context-pack IDs; refusal checks.
  - Remove the hard-coded `quality_pass` at `test_aos_017.py:150-165`.
  - `panestria metrics ask-eval --k 5` reports pass@1, pass^k and p95.

## Wave 2: lean structure (behaviour-preserving; zero compat diff)

- **2.1 `task/platform-fsutil`** (L1a): public `platform/fsutil.py` with `lock_file`, `private_dir`, `atomic_write`, `run_git` and `PlatformUnavailable`. Repoint the 11 importers of `proposal_demo` private helpers (`owner_build:26`, `native_plan:32`, …).
- **2.2 `task/packaged-assets`**:
  - Package the skills zip as `panestria/_assets` via hatch `force-include`; the original stays where it is.
  - `platform/assets.py` uses `importlib.resources` and verifies `ARCHIVE_SHA256`. This replaces `parents[3]` at `api/local_server.py:92`, `execution/local_plan.py:49` and `execution/research_synthesis.py:158`.
  - A `hatch_build.py` hook bundles `apps/mission-control/dist`; `mount_mission_control` defaults to the packaged copy.
  - New `tests/contract/test_wheel_contents.py`: `uv build`, non-root install, `panestria --help`.
- **2.3 `task/devkit-split`** (L1b): move these into `devkit/panestria_devkit/`, outside the wheel:
  - `synthetic_journey`, `proposal_demo`, `api/proposal_demo`, `cli/review_demo`, `demo.py`, `review.py`, `harness/mock.py`, `api/serve.py`.

  Then:
  - pytest `pythonpath` and the Makefile `r0-demo`/`dev-api` targets point at the devkit;
  - `prepare_worker_image` becomes `sandbox/images.py` plus `panestria sandbox prepare-image` (update `ci.yml:140`);
  - remove the hard-coded `/home/yogesh` path (`cli/review_demo.py:28`);
  - `task_workflow.py:351` uses a registry hook;
  - import-linter forbids `panestria` → `panestria_devkit`.

  The R0 node set stays identical and R0 evidence is untouched.
- **2.4 `task/config-package`** (L4): one `config/` package.
  - `files.py`: `read_private`, a single `TOKEN_RE` (replacing the 4 copies), `require_absolute`, `require_private_dir`.
  - `ConfigRejected(ValueError)`, with `LocalApplicationRejected` kept as a subclass.
  - `ports.py`: a documented table that keeps the current defaults.
  - Fold in `config_model` and `config_storage`.
- **2.5 `task/db-module`** (L5, P2-7): `platform/db.py`.
  - `connect(role)` with one timeout table, plus a `psycopg_pool` for the API.
  - One `append_event`; the SQLAlchemy path becomes an adapter with the same lock tuple.
  - `platform/locks.py` plus a lock-order test.
  - No per-call `create_engine` (`task_workflow.py:162`, `recovery.py`).
  - Event-cursor stress test.
- **2.6 `task/sse-listen-notify`** (P2-6):
  - Transactional `pg_notify` in `append_event`.
  - `api/event_bus.py` uses one listener; SSE waits on a notify or a 5 s heartbeat (`api/event_stream.py:56-77`).
  - Phone revocation is still checked per batch.
- **2.7 `task/layers-contract`** (L6):
  - Add an import-linter `layers` contract: `api|cli > execution > brokers|verification|memory|learning|inference > kernel > sandbox|policy|resources|telemetry > platform > contracts`.
  - Move `artifact_ingress` and the `kernel/ask` orchestration into `execution`; add `api/deps.py`; make the egress predicates public.
  - Break the 8-package SCC.
  - `tools/private_imports.py` ratchets private imports from 96 to 0.
- **2.8 `task/feature-folders`** (L7): feature sub-packages in kernel, execution and contracts, with a scripted import rewrite. Run in a freeze window.
- **2.9 `task/app-factory`** (L8): `api/app.py create_app(profile)` replaces the 4 builders, plus an `execution/services.py` composition root. Golden route, header and openapi snapshot per profile.
- **2.10 `task/dedupe-and-dead-code`** (L9/L11):
  - `contracts/canonical.py` replaces the 7 `_sha` helpers.
  - Merge `activity` and `review_inbox`; delete the dead `database_now`.
  - Fold `ops`; one `policy/` package.
  - Keep `SearchProvider`, which AOS-023 uses.
- **2.11 `task/deny-codes`**: generate `platform/errors.py DenyCode(StrEnum)` from the 1,143 literals; the wire format is unchanged. Ratchet the literal count to 0 and generate `docs/api/deny-codes.json`.
- **2.12 `task/structured-logging`**:
  - `platform/logging.py`: JSON output reusing the `telemetry/tracing.py` redaction, with trace, goal and task IDs.
  - Audit the 112 `except Exception` blocks; `cli/plan.py` returns typed reasons.
  - Ruff `BLE001` baseline; a sentinel test proves no secret or path leaks.
- **2.13 Long-function refactors** (L10), each preceded by characterisation goldens:
  - **`task/refactor-native-parser`:** `event_parser._frame` (168-438, CC 106) becomes table-driven, with golden JSONL fixtures.
  - **`task/refactor-sandbox-execute`:** `DockerSandbox._execute` splits into launch, attach and settle.
  - **`task/refactor-kernel-long-functions`:** `native_build.run`, `plan_returns.release`, `build_progress.inspect`, `plan_revisions.propose`, `research_sources.commit_fetch`, `offline_build.capture_reference`, `reader.extract`, `mission_web.mount_mission_control`.
  - **`task/refactor-cli-tui`:** `AskTerminal.run`.

  The mutation score must not drop.
- **2.14 `task/complexity-ratchet` + `task/google-docstrings`**:
  - Ruff `C901` (15, ratcheting to 10), `PLR0913` and `PLR0915`.
  - Ruff `D` with the Google convention on the public API; target ≥90% docstrings in the scoped packages.
  - `tools/quality_budget.py` writes a PR artifact; `docs/developer/quality-budget.json` may only improve.

## Wave 3: durable kernel (OD-2; critical path)

- **3.1 `task/task-state-machine`** (F-D3, L3):
  - `kernel/core/task_machine.py` provides `TaskMachine.transition(uow, task_id, target, cause, expected_row_version)`: table check, CAS, event.
  - It replaces all 27 raw `UPDATE … SET state` sites; `build.py:536-537` becomes two transitions.
  - A trigger generated from `ALLOWED_TRANSITIONS` (`tools/gen_transition_trigger.py`) starts in **warn** mode.
  - Follow-up PR `task/task-state-machine-enforce` after 2 weeks with zero violations.
  - Tests: exhaustive transition table, Hypothesis `RuleBasedStateMachine`, mutation.
- **3.2 `task/effect-ledger`** (F-D2, L2):
  - `EffectLedger` (create, claim, finish, reconcile, `list_stuck`) always writes the outbox row.
  - `repositories/approvals.py:256`, `task_workflow._record_effect:160` and the devkit `_effect_state` route through it.
  - Migration backfills the missing outbox rows.
  - The stuck report appears in `panestria health`, Mission Control and `GET /v1/effects/stuck`.
  - Mutation ≥80% on `kernel/effects.py` and `kernel/approvals.py`.
- **3.3 `task/dbos-worker-runtime`**:
  - One DBOS config with queues `panestria-build` (2), `panestria-research` (1) and `panestria-background` (1); the R0 queue is kept.
  - `panestria worker serve` runs workflows and reports a `/readyz` heartbeat; the API never runs workflows.
  - Extend the determinism lint.
- **3.4 `task/durable-build-workflow`**:
  - `run_build_plan` is enqueued in the same transaction as the claim, following the admission pattern (`execution/admission.py:119-171`). It replaces the thread at `mission_run.py:49-54` and the pool at `native_plan.py:351`.
  - Steps:
    - `claim_ready`;
    - `record_launch_intent`;
    - `launch_native` (`retries_allowed=False`);
    - `capture_and_verify`;
    - `integrate`;
    - the approval wait via `DBOS.recv`.
  - An intent with no outcome goes to RECONCILING. Native work is never auto-resumed (AOS-024-TC03).
  - Test: SIGKILL at every `crash_gate`; no lost task, duplicate effect or stuck RUNNING.
- **3.5 `task/durable-research-workflow`**: research stages become DBOS steps; fetches are idempotent by request ID; the CLI gains `--wait`.
- **3.6 `task/background-durable`**: background runs become a workflow with a pacing step.
- **3.7 `task/stuck-effect-sweeper`**: a scheduled workflow that applies only proven-safe transitions and posts a review-inbox notice. It never re-dispatches native work.

## Wave 4: native workers (OD-3, OD-1, OD-4)

- **4.1 `task/egress-sni-enforcement`** (SEC-M2):
  - `sandbox/tls_clienthello.py`: a bounded parser.
  - Gateway (`egress.py:117-168`): SNI must equal the CONNECT host; deny ECH and missing SNI.
  - Per-vendor allow-lists bound into the manifest digest.
  - An `egress_observation` table.
  - Fuzz the parser; mutation ≥90%.
- **4.2 `task/native-cli-sandbox`** (OD-3, SEC-M3):
  - New `native-cli` container profile (reuses 2.13 launch/attach/settle):
    - network none, read-only rootfs, cap-drop ALL, no-new-privileges;
    - tmpfs HOME;
    - the owner's non-root uid;
    - a ro **copy** of the hash-verified binary;
    - `native_proxy_relay.py` (already built, now wired) → 4.1 gateway;
    - a dedicated config directory;
    - only the task workspace.
  - MCP peer checks add pid ancestry.
  - `ProcessReceipt` records signal, last frame and OOMKilled, to diagnose the unexplained stop.
  - The launch path in `brokers/harness/process_runner.py`, `claude_check.py:280` and `claude_proposal.py:134` switches to the container.
  - Boundary test with a hash-pinned **stub CLI**: reading `$HOME/.ssh`, a raw connection, a mismatched SNI, hostile hooks, `.mcp.json` and `CLAUDE.md` are all denied.
- **4.3 `task/worker-adapter-contract`**:
  - `brokers/harness/contract.py` defines the `WorkerAdapter` Protocol, `NormalizedEvent` and `NativeResult`, with `supports_resume=False`.
  - Claude code moves to `harness/claude/`.
  - A registry-driven `worker_declarations`.
- **4.4 `task/codex-rea-investigation`**: REA investigation of a pinned `openai/codex` release, producing `docs/project/reuse/codex-cli.md`. It establishes:
  - license;
  - the `exec --json` schema;
  - sandbox and config isolation;
  - MCP behaviour;
  - auth;
  - hosts contacted;
  - terms.
- **4.5 `task/codex-adapter`** (AOS-024 TC01-03):
  - `brokers/harness/codex/` with profile, parser and adapter, running in the `native-cli` sandbox.
  - Additive values: `PrivacyDestination` `openai-subscription` and a quota provider lane.
  - Two-worker plans default to Claude plus Codex; WAIT with `second_vendor_unqualified` otherwise.
  - New `tests/integration/test_aos_024.py`, seeded from `docs/fixtures/codex-synthetic.jsonl` plus sanitised recordings.
- **4.6 `task/private-repo-build-grants`** (OD-4, D2):
  - One `policy.build_export_decision` replaces about 20 scattered `!= "PUBLIC"` checks (`owner_build.py:178`, `native_build.py:86`, `native_plan.py:182`, …).
  - INTERNAL needs a per-repo grant, `allow_private_cloud` and a per-run approval bound to the export manifest. CONFIDENTIAL and RESTRICTED stay local only.
  - The export snapshot excludes `.git`, `.env`, `.ssh` and `.aws`; a secret-scan hit blocks it.
  - New `panestria connections grant-repo`.
  - Tests: exhaustive matrix plus Hypothesis; mutation ≥90%.
- **4.7 `task/native-stop-diagnosis`**: k=20 live runs on the owner host, then fix the stop or record it as a bounded known issue.

## Wave 5: AI quality and Delegate

- **5.1 `task/semantic-citation-verifier`** (F-AI1):
  - `verification/claim_support.py` runs in two stages:
    1. deterministic guards (number, unit, date, negation, quantifier, entity);
    2. `SupportJudge` plug-ins (Claude subscription reusing the `native_entailment_probe` infrastructure, k=3, judge ≠ generator; or a pinned local model). An unavailable judge gives UNKNOWN.
  - The `semantic_support` Literals widen additively (`contracts/research_*.py`).
  - Wire it in at `kernel/research_collection.py:274`, `cli/research.py:294,365`, `execution/research_synthesis.py:139,365` and `execution/research_collection.py:43`.
  - Labelled set `tests/fixtures/citation-eval/research-v1/`: ≥30 per class plus hard negatives, two annotators with kappa. CI uses recorded cassettes.
  - `panestria metrics citation-eval` reports false-support rate with Wilson CIs and pass^k.
- **5.2 `task/verifier-calibration-report`**: dev and holdout folds, an abstention threshold, ECE and selective risk, written to a new evidence directory.
- **5.3 `task/delegate-workflow`** (AOS-023, F-P2):
  - `execution/delegate/`:
    - immutable budgets;
    - local planner;
    - SearXNG `SearchProvider` with a disclosure log;
    - fetch → reader → claims → verify → brief.
  - Runs as a DBOS workflow, exposed as `POST /v1/research` and `panestria delegate`.
  - New `tests/e2e/test_aos_023.py` TC01-03; TC04 runs live.

## Wave 6: gates, evidence, drills, trial, operations

- **6.1 `task/gate-case-binding`** (F-G1):
  - `@pytest.mark.gate_case("…")` marker, parsed by `readiness.py:109-129`.
  - Convert the dynamic IDs (`test_aos_003:74`, `test_aos_004:53`, `test_aos_002_services:50`, `test_r0_loopback:43`, `test_aos_005:619`).
  - Bind existing tests after case-by-case review, with rationale in `docs/testing/case-bindings.json`.
  - New catalog state `OBSERVED_ON_OLDER_COMMIT`.
  - CI ratchets: registration floor, marker-to-catalog check, and every planned node exists or is owned.
- **6.2 `task/gate-evaluator`** (AOS-030-S1):
  - `verification/gate.py`: `GateRunner`, `ReleaseEvidenceManifest` and a `CaseResult` model that generates `docs/contracts/case-result.schema.json` (the load-bearing schema leaves `docs/schemas`).
  - Verdicts follow `TEST_EXECUTION.md:28-48`: PASS, FAIL or INCOMPLETE.
  - `panestria gate evaluate --gate G3 [--pretrial]` writes `evidence/gate-*`; it never edits the catalog.
  - New `tests/e2e/test_aos_030.py::test_gate_missing_skip_unknown`, plus Hypothesis and mutation ≥90%.
- **6.3 `task/traceability-enforcement`**:
  - `tools/trace_check.py` checks requirement → case → node → evidence in both directions.
  - Generated `requirement-traceability.json` and `evidence/INDEX.json`.
  - Nightly `tools/gate_mutation_probe.py`: every bound case must kill at least one mutant.
- **6.4 `task/fault-drill-harness`** (AOS-030-TC02):
  - `verification/drills.py`: `ChaosScenario` plus SQL invariant checkers and a history checker against `ALLOWED_TRANSITIONS`.
  - The six drills are built on the existing component tests. Extra faults: crash at every step boundary, Postgres restart, disk full, clock skew, network loss.
  - Nightly k=5 with pass^k; `test_six_required_fault_drills`.
- **6.5 `task/trial-instrumentation`**:
  - Tables `trial`, `trial_day` and `trial_incident`.
  - Auto-captures approvals, corrections and use.
  - `panestria trial start|log|incident|status|report`, with a reset rule and `DogfoodRecord`. Only the owner runs `start`.
- **6.6a `task/first-run-setup-and-service`**:
  - `panestria setup`: doctor checks, a production Compose project with a generated DB password, migrations, image preparation and init.
  - `panestria service install --user` installs systemd user units for db, api, worker and local.
  - `panestria doctor` produces a redacted diagnostics bundle.
- **6.6b `task/backup-restore`**:
  - `backup create|verify|list`: pg_dump of the panestria, dbos and checkpoint schemas; artifacts, evidence and config; a sha manifest; vault key-ID custody.
  - `restore` checks the fingerprint, then applies a **restore fence**: bump epochs, EXECUTING → RECONCILING, and hold DBOS work until resume.
  - Test: restore into a new DB, run the smoke test, and confirm no effect is re-run.
- **6.6c `task/upgrade-rollback`**:
  - `upgrade` (backup → wheel → migrate → doctor) and `rollback --to BACKUP`.
  - ADR-0016 records forward-only migrations with snapshot rollback.
  - Tests: upgrade from an N-1 dump; rollback rehearsal.
- **6.7 `task/x13-budgets-psi`**:
  - Host budget schema and `resources/pressure.py` (PSI, with `psi_unavailable`).
  - Admission uses PSI; a mid-generation re-check; idle `unload()`; `on_ac_power=None` handled.
  - `panestria metrics budgets --measure`.
- **6.8 `task/adversarial-regression-suite`**: a `tests/security/` corpus (repo, page and memory injections; API and phone attacks) plus nightly Schemathesis. Reports ASR with n and k.
- **6.9 `task/perf-load-budgets`**: a 2× load test (two-worker Build + 10 SSE + Ask) against the budgets, with token and cost tracking per task.

## Wave 7: Mission Control and UX (AOS-028/029, X12, X14)

- **7.1 `task/mission-read-models`**: read-only `/v1/fleet`, `/v1/traces/{goal}` (redacted `trace_span`), `/v1/cost` (known/estimated/unknown) and `/v1/exposure` (authorized/accessible/observed). Regenerate openapi and `schema.d.ts`.
- **7.2 `task/mission-views`**: Fleet, Trace waterfall, Cost, Exposure and Trial views plus the phone subset. New `tests/e2e/test_aos_028.py` and `tests/integration/test_aos_029.py`.
- **7.3 `task/mission-a11y`**: axe-core in Playwright, keyboard and focus order, contrast (AOS-028-TC04).
- **7.4 `task/aos-029-local-otel`**: apply the ADR-0012 TC04 amendment (`amended_by`, original text kept), plus footprint measurement.
- **7.5 `task/cli-task-oriented`**: top-level `panestria ask|delegate|build|status`; expert sub-apps hidden but kept; generated `docs/user/reference/cli.md`.
- **7.6 `task/x12-device-kit`**: hermetic X12 TC05-07, plus `panestria phone verify-device` for the live TC08.
- **7.7 `task/x14-reuse-records`**: `docs/project/reuse/*` plus `reuse-records.json` for DBOS, OTel, pypdf, SearXNG, Ollama, Claude Code, Codex, Playwright and axe. New `tests/e2e/test_mvp_x14.py`.

**Migration train order:**
1. 1.2 memory FTS
2. 1.6 background state + indexes
3. 1.7 side-table seq
4. 1.5 phone cap
5. 3.1 transition trigger (warn)
6. 3.2 outbox backfill
7. 3.3-3.6 workflow links
8. 3.1b enforce
9. 4.1 egress observation
10. 4.5 vendor lane
11. 4.6 repo grants
12. 5.3 delegate
13. 6.5 trial
14. 7.1 trace_span

## Documentation cleanup and production README (PRs 8.x)

**Must stay at their current paths** (machine-read):
- `docs/specification/**` (frozen), including the skills zip;
- `docs/fixtures/synthetic-goal-contract.json`, `docs/api/openapi.json`;
- `docs/contracts/*`;
- `docs/testing/{test-catalog,release-gates,ci-regression-policy,mutation-critical}.json`;
- `README.md`.

**Target layout** (`git mv` only; archived files are not edited):
- **`docs/user/`:**
  - `install.md`;
  - quickstarts for Ask, Delegate, Build, Build on a private repo, Phone and Background;
  - generated `configuration.md`;
  - `operations/{service,backup-restore,upgrade-rollback,drills,trial}.md`;
  - `troubleshooting.md` (generated deny-code table), `security-model.md`, `privacy-and-data.md`, `faq.md`;
  - `reference/cli.md` (generated).
- **`docs/developer/`:** generated `ARCHITECTURE.md`, `contributing-workflow.md`, `testing.md`, `release-gates.md`, `threat-model.md`, `quality-budget.json`, `spec-originals.sha256`.
- **`docs/project/`:** generated `STATUS.md` (the **single** status page), `roadmap.md`, `reuse/`, and this plan.
- **`docs/archive/`:**
  - status pages: GOAL_PROGRESS, MVP_EXECUTION_CHECKPOINT, IMPLEMENTATION_PROGRESS, START_HERE, CURSOR_START_HERE;
  - `cursor/`, `phases/`, `plans/`, `design/`, and the 106 testing runbooks;
  - `docs/schemas`, plus `docs/CHECKSUMS.sha256` with a drift note.
  - One-line stubs only at the paths the 4 immutable evidence reports cite.
- **`docs/testing/`:** keeps only the machine-read JSON plus `TEST_EXECUTION.md` and the CI/mutation docs.
- `PANESTRIA_PHASED_IMPLEMENTATION_PLAN.md` stays where it is, because AGENTS.md points to it.

**Docs PRs:**

| PR | Scope |
|---|---|
| 8.1 | The same PR as 0.10. |
| 8.2 `task/docs-checker` | `tools/doc_check.py` in CI checks: relative links and anchors (excluding `originals`, `archive` and `evidence`); glued-number typos (61 files); freshness (ARCHITECTURE head = `migrations` head; README prerequisites match `pyproject`, `package.json` engines and the native pins); and that generated docs are up to date. |
| 8.3 `task/docs-restructure` | Scripted rewrite of the 254 inbound links. `docs/CHECKSUMS.sha256` is retired to the archive; `docs/specification/CHECKSUMS.sha256` is left untouched. New `tests/contract/test_specification_integrity.py` verifies `originals/` and `attachments/` plus the skills-zip sha. Fix glued numbers in live docs. |
| 8.4 `task/generated-status` | `tools/status_report.py` builds STATUS.md from the tracker, catalog and evaluator, replacing 7 status surfaces. |
| 8.5 `task/architecture-regenerated` | `tools/gen_architecture.py` generates the layer diagram, package table, migration head, DBOS queues and trust boundaries. |
| 8.6 `task/user-docs` | Written after each feature lands. Fenced `ci-run` blocks are executed by `tools/doc_commands.py`. |
| 8.7 `task/developer-docs` | CONTRIBUTING covers the task-PR workflow, `make ci-full`, the migration train, compat_check, `gate_case` and the non-root Docker requirement. `SECURITY.md` is updated. |
| 8.8 `task/readme-production` | Merged last, after 6.6 and 5.3. |

**README outline:**
1. Purpose in one paragraph (Ask, Delegate, Build; owner approves effects).
2. **Honest maturity status**, generated from STATUS.md. No claim of production or MVP acceptance until the owner records it.
3. What it guarantees and what it does not.
4. System requirements, verified by doc_check:
   - Linux x86-64 and Docker as a non-root user;
   - Python 3.12, uv 0.12.3;
   - host budgets, optional GPU;
   - Ollama with the pinned model;
   - Claude Code 2.1.273 and the pinned Codex;
   - SearXNG.
5. Install: wheel or `uv tool install`, then `panestria setup`, then `panestria service install --user`.
6. Quickstarts for each journey.
7. Mission Control.
8. Data and privacy (what leaves the machine, key custody).
9. Operations: backup, restore, upgrade, rollback, doctor, logs.
10. Troubleshooting: the top deny codes.
11. Security reporting and license.
12. A link for contributors.

## Verification protocol ("no breaking changes; everything runs as intended")

**Per PR:**
- `make ci-full` covering all 5 lanes, full profile, with zero deferred tests and zero unexpected skips (`junit_guard`).
- `compat_check` against the Phase-0 baseline.
- Coverage floors.
- Ruff, format, mypy strict and the import-linter layers contract.
- Secret scan, `doc_check` and `trace_check`.
- Mutation on touched safety modules.
- Mission Control build plus browser tests.
- I also run the integration lanes on a **non-root** Docker host before each handoff. Here that means a CI run; a non-root local user needs your permission in this environment.

**Nightly on `main`:**
- full profile;
- Hypothesis nightly profile;
- Schemathesis;
- mutation, with targets ≥80% on critical modules and ≥90% on safety modules (policy, egress, ClientHello, approvals, EffectLedger, TaskMachine, merge, gate, API security, quota math, claim guards, export decision);
- six drills k=5;
- crash-at-every-step;
- history secret scan, pip-audit and the gate mutation probe.

**Candidate freeze, by the owner:**
1. Environment manifest.
2. All automated lanes.
3. Wheel install as non-root, plus `setup`.
4. `panestria gate evaluate --gate G3 --pretrial`, which must PASS 156/156 on evidence bound to the candidate.

**Live lane on your qualified host:**
- Claude and Codex re-qualification.
- A-1 golden set at k=5.
- A live D-1 brief.
- B-1 two-vendor on a PUBLIC repo and on an INTERNAL repo.
- Background with real quota.
- A real phone.
- GPU pressure.
- X13 budgets.
- A backup → restore → upgrade → rollback rehearsal.

**Independent re-score:** fresh lens agents (not the PR authors), two scorers per dimension, rubric caps applied, written to `docs/reviews/R3-READINESS-REREVIEW-<date>.md`. Exit: no S0 or S1 open and every dimension ≥7 before the trial.

**Expected ceiling:**
- About 9 on architecture, simplicity, code quality, security, durability, tests, traceability and requirements.
- 8-9 on AI, operations and efficiency after your host measurements.
- Production readiness about 7 before the trial, 8-9 after the trial plus an independent PRR.
- 10 is reserved for an external audit.

**Owner-only, kept separate:**
- Trial start and the 14 days of use.
- AOS-030-TC04.
- The acceptance record and final G3 (157 cases).

## Sequencing and dependencies

**Critical path:** Phase 0 → 2.1/2.3 → 2.5 → 3.1/3.2 → 3.3/3.4 → 4.2 → 4.5 → 6.4 → 6.2 → freeze.

**Parallel tracks after Phase 0:**
- Wave 1, subject to the migration train;
- Wave 2, with 2.8 in a freeze window;
- 4.1, 4.3 and 4.4 early;
- 5.1 labelled-set preparation;
- docs 8.2-8.5.

**Size and timeline:** about 80 PRs, roughly 14-18 weeks to candidate freeze, then the 14-day trial.

**What I need from you along the way:**
- **Accounts and credentials:** Claude login; Codex/ChatGPT sign-in plus background-use terms.
- **Infrastructure:** a SearXNG instance; a GPU host with Ollama and PSI; a real phone with private TLS.
- **People:** a second annotator for the citation set.
- **Approvals and authorisations:**
  - ADR approvals and the TC04 amendment;
  - GitHub branch protection and CODEOWNERS;
  - paid-SDK smoke authorisation;
  - candidate freeze and trial start.
