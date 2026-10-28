# Panestria - Staff QA test-effectiveness audit (read-only)

Repo HEAD 33e61dc (clean tree before/after; nothing written inside the repo).
Method: static inspection of all of tests/ + tools/ci_tests.py + tools/ci_merge_proof.py + .github/workflows;
AST statistics; pytest --collect-only; coverage of tests/unit + tests/contract (hermetic) via
`uv run --frozen --with coverage coverage run --branch --source=src/panestria -m pytest tests/unit tests/contract -m "not live"`.
Integration/e2e were NOT run (per instructions), so integration coverage is UNMEASURED, not "low".
Labels: CONFIRMED = reproduced by command/file read; PLAUSIBLE = inferred.

---------------------------------------------------------------------------------------------------
## 1. Inventory

| Layer | files | def test_ | collected cases (not live) | LOC | notes |
|---|---|---|---|---|---|
| unit | 43 | 287 | 859 (+1 live deselected) | 6.5k | pure logic + fake transports + real OS pipes/sockets |
| contract | 7 | 48 | 92 | 1.5k | toolchain, verifiers, readiness inventory |
| integration | 186 | 891 | 1451 (+67 live deselected) | 41.5k | real Postgres (docker), subprocess, sandbox, Chromium |
| e2e | 2 | 12 | 12 | 1.6k | CLI-over-TCP, approval journey |
| **total** | **238** | **1238** | **2414 (+68 live) = 2482** | 51k vs 55k src LOC | pyramid is inverted by case count: 61% integration |

Command evidence: `pytest tests --collect-only -q` -> "2482 tests collected"; `-m live` -> "68/2482"; per-lane
(`tools/ci_tests.py` partition + `-m "not live"`): fast 951, kernel 364, platform 811, research 288 = 2414.

Markers (CONFIRMED, pyproject.toml:50-58 + grep): `unit` used 25x, `contract` 1x (layers are by directory, not marker -
the markers are decorative); `live` used 56x (68 cases) and is the ONLY marker that changes behaviour (`-m "not live"` in
tools/ci_tests.py:187 and Makefile:25). No skip/xfail except two `skipif(sys.platform != "linux")`.

"Tests run exactly once" - CONFIRMED at file level: `partition()` gives 238 files, 238 unique, equal to the 238 `test_*.py`
files on disk; per-lane case counts sum to 2414 = all non-live cases. No test function is imported into a second module
(only one module-level `import test_research_synthesis as synthesis_support` in tests/integration/test_research_runtime_metrics.py:8,
which does not re-collect functions). The same *behaviour* is however exercised at several layers on purpose
(e.g. egress address rules in unit + aos_008; Host/Origin in 10+ integration files).
Caveat: on a PR that merges to main, the PR run is *reused* instead of re-run (see F6), so "once" can become "never on main".

What "live" excludes from every CI run (CONFIRMED, `-m live` listing, 68 cases): real Claude subscription, local-model, real
hardware AND the Docker OS-boundary suite: tests/integration/test_aos_008.py:52,117,183,206,285
(uid/mounts/egress/limits, resource pressure, read-only profile/private paths, failure cleanup), test_aos_017
(network-disabled), test_sandboxed_verifier.py (verifier_os_boundary), test_sandbox_cancellation.py x3, test_model_runtime.py
(model_os_boundary), test_native_tool_gateway.py x3, test_aos_027a (worker cannot weaken checks). CI nevertheless builds the
pinned worker image for the three non-fast lanes (ci.yml "Prepare pinned worker image"), so the capability to run them exists.

Required vs full profile (tools/ci_tests.py fully read):
* PR => `required`: defers 46 named functions in 2 groups (docs/testing/ci-regression-policy.json):
  21 "legacy-synthetic-journeys" (tests/integration/test_aos_004.py x11, tests/e2e/test_aos_005.py x2, test_r0_loopback.py x2,
  test_r0_admission.py x2, test_r0_effects.py x1, test_r0_checks.py x3) and 25 "domain-restore-matrix" (pg_dump/restore/downgrade).
* push (non-task branches) / workflow_dispatch default / policy, migrations, conftest, `*_support.py`, pyproject, uv.lock changes /
  unknown or unfetchable base => `full`.
* Deferral is fail-closed: stale/duplicate/ambiguous selectors raise, mutation-witness nodes cannot be deferred, git failure => full.
  Mechanism is sound. Residuals are F6 and F7 below.
* Safety-critical content among the deferred: test_aos_004 `test_latest_approval_request_wins`,
  `test_old_effect_does_not_stand_in_for_the_current_approval`, `test_stored_pass_does_not_merge_a_different_commit`,
  `test_global_scope_denies_a_commit_without_a_path_check`, `test_stale_snapshot_does_not_complete_a_different_approval`,
  r0_effects `test_reconcile_applied_ref_and_refuse_stale_authorization`. They target the legacy SyntheticJourney code, and
  native-Build equivalents remain required (CI_REQUIRED_COVERAGE.md), so this is a bounded risk, not a hole.

---------------------------------------------------------------------------------------------------
## 2. Assertion quality

AST statistics over 1236 test functions (scratchpad/stats.py): only **4** have no assert/raises, all delegating to helpers
(tests/integration/test_aos_001.py `test_fresh_host_loopback`, test_owner_build_cli.py x2, unit/test_egress_addresses.py
`test_equivalent_ipv6_spelling...`). Mean asserts/test: unit 2.3, contract 3.8, integration 4.8, e2e 13.8. 64 tests are >= 80 lines
(largest: test_aos_003.py `test_atomic_enqueue_and_duplicate` 216 lines/28 asserts; e2e test_aos_005.py
`test_approval_digest_actor_expiry` 209 lines/40 asserts).
`Mock/MagicMock` appears 34x vs 307 `monkeypatch.setattr` - the suite uses hand-written fakes / real services, not mock-verifying-mock.

Sample of 38 tests read in full (3 seeds, scratchpad/sample1/2.txt + targeted reads). Classification:

| # | test | verdict |
|---|---|---|
| 1 | unit/test_research_public_fetch.py:354 disclosure hook precedes each DNS & denial stops redirect | BEHAVIOR (ordered timeline) |
| 2 | unit/test_connection_contracts.py:184 scoped remote action does not invent roots/send | WEAK - asserts constructor echoes input; mirror |
| 3 | unit/test_connection_contracts.py:171 explicit root/cash still no other actions | WEAK - `"send" not in value.actions` + `expires_at > now` |
| 4 | unit/test_public_web_policy.py:149 destination grants closed | BEHAVIOR (negative, thin) |
| 5 | unit/test_native_command_transport.py:255 transport lifetime/single connection | BEHAVIOR, wall-clock (0.1 s lifetime + poll) |
| 6 | unit/test_quota_contracts.py:82 clock rollback does not make observation new | BEHAVIOR (but imports private `_view`) |
| 7 | unit/test_quota_contracts.py:48 UNKNOWN cannot claim 0/unlimited | BEHAVIOR |
| 8 | unit/test_native_command_transport.py:280 existing path never removed | BEHAVIOR (dir/file/symlink) |
| 9 | unit/test_bootstrap_pin_guards.py:96 replaced path denied with FD open | BEHAVIOR (TOCTOU race injected) - fails as root (F8) |
| 10 | unit/test_native_input_frame.py:89 invalid lengths rejected before body read | BEHAVIOR (asserts `source.tell()`) |
| 11 | unit/test_native_input_frame.py:29 round trip opaque | BEHAVIOR, includes repr redaction |
| 12 | unit/test_performance_history.py:71 budget & symlink never overwrite history | BEHAVIOR |
| 13 | unit/test_performance_history.py:12 "actual historical models..." | EVIDENCE CONFORMANCE - hard-codes commit SHAs/ratios of retained evidence/ JSON |
| 14 | unit/test_native_entailment_probe.py:204 rubric hash == evidence/local-entailment-2026-10-16 | EVIDENCE CONFORMANCE (hash pin) |
| 15 | unit/test_native_proxy_relay.py:148 socket concurrency & attempt caps | BEHAVIOR (real sockets, 5 ms polls) |
| 16 | unit/test_selected_native_model_contracts.py:150 qualification needs requested+reported model | BEHAVIOR (synthetic JUnit mutations) |
| 17 | unit/test_lossless_presentation.py:43 ambiguous output abstains | BEHAVIOR |
| 18 | unit/test_model_manifest_contract.py:43,80 provider rebind / config change after return | BEHAVIOR (httpx MockTransport fault injection) |
| 19 | unit/test_egress_addresses.py (32 unsafe addresses, scope ids, octal/decimal) | BEHAVIOR, excellent corpus |
| 20 | unit/test_research_text.py (NFC, half-open UTF-8 offsets, hash mismatch) | BEHAVIOR, adversarial |
| 21 | contract/test_aos_002.py:40 exported JSON schemas == docs/contracts/*.json | SNAPSHOT/drift guard (legit, generated artefact) |
| 22 | contract/test_aos_002.py:62 edited contract = new version | BEHAVIOR |
| 23 | contract/test_r0_verifiers.py:439 git allow-list rejects push/hooks | BEHAVIOR (negative corpus) |
| 24 | contract/test_r0_verifiers.py:458 false pass README | BEHAVIOR (real git/worktree) |
| 25 | contract/test_mvp_readiness.py (synthetic tmp manifests) | BEHAVIOR - fixtures are synthetic, not the repo's docs |
| 26 | contract/test_classification_compatibility.py:62 legacy denial dominates (itertools.product) | BEHAVIOR, exhaustive grid |
| 27 | integration/test_r0_http.py:117,189 oversized header / forged correlation id | BEHAVIOR |
| 28 | integration/test_aos_002_services.py:136 concurrent transition + cursor | BEHAVIOR but 147-line "god test" (DAG + deps + race in one) |
| 29 | integration/test_aos_003.py:618 before/after commit SIGKILL + recovery | BEHAVIOR, real crash injection (exemplary) |
| 30 | integration/test_aos_006.py:215 effect response loss | BEHAVIOR (fake target, real DB outbox) |
| 31 | integration/test_aos_006.py:259 approval consume + unknown effect | BEHAVIOR (exact error codes) |
| 32 | integration/test_aos_014.py:55 SSE decimal cursor > 2^53, invalid cursor spellings | BEHAVIOR, exemplary edge cases |
| 33 | integration/test_native_connection_grants.py:167 two scoped workers consume context | BEHAVIOR + partly MIRROR (recomputes context sha with same serialization) |
| 34 | integration/test_profile_vault.py:246 nonce reuse & immutable revisions | BEHAVIOR (DB trigger) |
| 35 | integration/test_canonical_plan_store.py:172 acceptance rollback | BEHAVIOR |
| 36 | integration/test_research_source_provenance.py:455 global event lock only after entity writes | IMPLEMENTATION-MIRROR - asserts SQL statement order via UnitOfWork subclass (guards a real deadlock design, but string-coupled) |
| 37 | integration/test_isolated_research_reader.py:54 HTML tokenizer ignores active markup | BEHAVIOR |
| 38 | e2e/test_r0_loopback.py:365 smoke records own loopback socket | WEAK/COUPLED - imports another test module via importlib, calls private `_measure_loopback_smoke`, hard-coded port 8767 |

Tally: 31 behavior-verifying, 3 weak/mirror (2, 3, 33-partial), 2 snapshot/evidence conformance (13, 14) + 1 legit drift guard (21),
1 implementation-coupled (36), 1 coupled-to-other-test (38). No tautologies of the `assert True` / mock-asserts-mock kind found.

Doc / evidence / hash conformance share (CONFIRMED by grep of every `docs/`/`evidence/` reference in tests/, 49 files, read individually):
* docs/fixtures/synthetic-goal-contract.json and docs/specification/attachments/agentos-skills-v0.1.0.zip are used as *inputs/fixtures*
  (HardwareProbe requires the zip, src/panestria/resources/hardware.py:49-54) - not conformance checks.
* True conformance tests: contract/test_aos_002.py:40 (schemas), e2e/test_aos_005.py:1158 (openapi.json byte-equality),
  integration/test_aos_002_migration.py:35 (schema-snapshot.txt), unit/test_performance_history.py x4 + test_native_entailment_probe.py:204
  (retained evidence/), contract/test_mvp_readiness.py:`test_revision_three_inventory_includes_all_extensions` (157/156 counts of the real
  manifest), contract/test_aos_001_toolchain.py:58 (greps ci.yml for "secrets."), integration/test_aos_001.py:166,187 (pyproject, .env.example, .gitignore).
* Estimate: **~12-15 of 1238 test functions (~1%)**; no test asserts on prose of docs/*.md. The CI_TEST_AUDIT.md already removed
  a larger set of text-policing tests. => Doc-conformance is NOT a problem here; the opposite problem (F1: gate manifests not mapped
  to tests) is.

---------------------------------------------------------------------------------------------------
## 3. Gaps in riskiest components

| Component | What exists (CONFIRMED) | Gaps |
|---|---|---|
| Kernel atomic commit & event cursor | SIGKILL before/after-commit recovery (test_aos_003.py:618), 2-thread barrier race w/ advisory-lock wait (test_aos_002_services.py:136), rollback-with-event (aos_006:97), lock ordering (5 files), cursor >2^53 & invalid spellings (aos_014:55), quota global-id race (quota_ledger:234) | Races are 2 threads x 1 iteration; no stress/soak (N writers, repeated), no property test for "cursor monotonic/no-skip under interleaved commit/rollback"; DAG validation (`validate_dag`) is pure logic but only tested inside a PG test; no unit test of the transition table |
| Approvals / effect digest | digest mismatch 409, wrong actor 403, expiry, foreign project 404 (e2e/test_aos_005.py:405); consume-once, stale_dispatch, dispatch_active (aos_006:259); revoke after claim (approval_revocation); effect lost-response reconcile | **No golden vector for `effect_digest`** (src/panestria/contracts/approval.py:61 hashes `model_dump_json()` - a pydantic upgrade/field-order change would silently change all digests; tests only compare `effect_digest()` to `effect_digest()` e.g. test_aos_005.py:436). No property test "any single-field change changes digest / key order doesn't". No concurrent double-approve/double-continue test found for same approval (PLAUSIBLE; consume uniqueness is tested only sequentially) |
| Sandbox / egress / policy engine | egress: 32-entry unsafe-IP corpus incl. v4-mapped, 6to4, Teredo, scoped v6, octal (unit/test_egress_addresses.py), DNS-once pinning, unix-socket gateway denial; policy engine 100% line/branch hermetic; mutation 92.45% on 5 functions | `tunnel()` byte cap/timeout, 8-slot admission semaphore, CONNECT header limit (8192) / slow-loris on the gateway have no direct test (egress.py hermetic 65.6% line / 52% branch); **the Docker OS-boundary suite is `live` and excluded from CI** (F2); probe: `_public_unicast("192.88.99.1")` (6to4 relay anycast) returns allowed - low impact since host allow-list is closed |
| Verification / entailment | 20-case-grid NFC/offset tests, corpus pin tests, metric-confusion tests, false-done tests with real git; entailment.py hermetic 90% | The entailment *decision* is a model; only scoring/plumbing is tested hermetically. Retained live evidence (unit/test_performance_history.py:12) records local model correct_fraction = 21/36 (58%) vs native 33/36 - a regression test for model quality does not exist; verifier/merge.py hermetic 0% (covered only by DB tests) |
| Quota scheduler | queue/reserve/withdraw/billing-unknown tests (background_queue, background_run), 8-claims-reserve-2 (plan_scheduler:40), stale/future/rollback observations, server-time expiry | Time-sensitive logic uses DB clock + `time.sleep(1.1)` (test_invocations.py:153); pure admission arithmetic not unit-tested; kernel/scheduler.py hermetic 18.5%, kernel/quota.py 30.6% |
| Phone pairing / auth | TLS+cookies+Secure/HttpOnly, replay 401, wrong Host/Origin/X-Forwarded-For 403, role=ADMIN DB constraint, revoke, foreign client IP 403 (test_private_phone.py:77-260), 429 on pair brute force (test_aos_009.py:174) | One 130-line mega-test; pairing-code entropy/expiry/lockout window, limiter window reset & the 128-bucket LRU eviction (src/panestria/api/security.py:30-43, uses `time.monotonic`, not injectable) are untested |
| API Host/Origin/CSRF envelope (src/panestria/api/security.py) | Host rebind 403 (aos_009:119), Origin evil 403 in ~8 files, CSRF missing/forged, credential-in-URL 400 in 3 files | By error code grep over tests/: `headers_too_large`/431, `ambiguous_headers` (duplicate Host/Origin/Content-Length), `invalid_query`, `request_deadline_exceeded`/408 (slow body), `invalid_body`/422 have **zero** hits. Module hermetic coverage 12.0% line / 0 of 36 branches; it is a pure ASGI middleware that can be unit-tested without a DB |
| Hand-rolled HTTP parser (R0 server) | test_r0_http.py:117 covers oversized header, negative/duplicate Content-Length, chunked | No fuzz / smuggling corpus (CL.TE, obs-fold, NUL, huge header count) |

Hypothesis / property-based / fuzz: **none** (`hypothesis` not installed in .venv, not in pyproject dev group, 0 `@given`; the only
"random" is `secrets.token_*` in fixtures). Randomised or generative input is replaced by hand-curated parametrize corpora
(good ones, e.g. the 32 unsafe IPs) and exhaustive splits (`for byte in wire` in aos_010:40). No fuzzing of: input-frame decoder,
cursor parser, HTTP parser, NFC passage offsets, BrowserSecurity header handling, bash/command protocol, SSE parser.
Crash injection: genuinely strong (SIGKILL/killpg in 24 files: durable_sandbox_crash, memory_gateway_crash, aos_003, r0_effects,
connection_roots, sandbox_framed_stdin...). Concurrency: threads/barriers in ~75 files but mostly 2-way.

---------------------------------------------------------------------------------------------------
## 4. Coverage (hermetic unit + contract only)

Run: 940 passed, 11 failed, 1 deselected in 29 s (the 11 failures are environmental, see F8). Branch coverage on.
**Total: 32.4 % lines (11,058 / 30,526), 18.9 % branches (1,664 / 8,790).** This is *not* a measure of the suite - the kernel,
API, execution and CLI are exercised by the Postgres-backed integration/e2e layer that I was told not to run. It does show
that ~two thirds of production code has **zero fast feedback** and that no coverage is measured anywhere in CI
(`grep -rn "coverage\|--cov" .github Makefile pyproject.toml tools` -> nothing; no pytest-cov/coverage in the dev group).

| package | stmts | line % | branch % |
|---|---|---|---|
| execution | 6476 | 17.7 | 6.3 |
| kernel | 4942 | 21.9 | 1.7 |
| cli | 3753 | 25.6 | 5.4 |
| api | 3255 | 20.2 | 0.2 |
| contracts | 2913 | 70.6 | 49.5 |
| brokers | 2550 | 66.5 | 51.6 |
| sandbox | 1473 | 54.4 | 41.3 |
| verification | 1190 | 63.8 | 48.2 |
| memory | 890 | 32.8 | 2.9 |
| (top-level) | 785 | 48.3 | 17.5 |
| resources | 699 | 70.4 | 54.0 |
| inference | 664 | 32.5 | 23.9 |
| telemetry | 446 | 81.8 | 65.1 |
| learning | 294 | 20.7 | 0.0 |
| policy | 170 | 55.3 | 37.1 |
| ops | 26 | 0.0 | 0.0 |

Critical modules, hermetic only (line %, branches covered/total):
policy/engine.py 100 (26/26) | verification/entailment.py 90.1 (17/24) | verification/runner.py 84 | verification/diff.py 82.6 |
sandbox/egress.py 65.6 (21/40) | api/phone.py 23.9 (0/26) | execution/protected_merge.py 24.2 | kernel/quota.py 30.6 |
kernel/scheduler.py 18.5 (0/52) | kernel/leases.py 19.6 | kernel/cancellation.py 19.1 | kernel/effects.py 16.0 (0/62) |
kernel/approvals.py 11.7 (0/86) | api/security.py 12.0 (0/36) | verification/merge.py 0.0 | kernel/transition.py 38 |
kernel/repositories/approvals.py 25 | policy/profiles.py 18.8 | policy/research_fetch.py 22.7.
Interpretation: the *pure-logic* safety kernels that the mutation pilot targets (policy engine, egress addresses, entailment scoring)
are well covered hermetically; every stateful kernel/API safety module depends exclusively on docker+Postgres. That is a
design choice (real DB, no mocks) that buys fidelity but costs feedback speed and makes coverage un-measurable without the
full stack. Recommend measuring combined coverage in one nightly full run (F3).

---------------------------------------------------------------------------------------------------
## 5. Flakiness / determinism

* Sleeps: 127 `sleep(` occurrences in tests; most are bounded poll loops with `time.monotonic()` deadlines (good). Fixed sleeps:
  tests/integration/test_invocations.py:153 `time.sleep(1.1)` (TTL expiry on real clock), test_r0_http.py:158 `time.sleep(0.6)`
  (timing assertion `elapsed` on health during submit), unit/test_native_command_transport.py:255 (0.1 s lifetime).
  Child fixtures sleep 60 s to be killed (fine). PLAUSIBLE flake: loaded 2-vCPU runner vs 1 s TTL / 0.6 s timing windows.
  CI evidence of load sensitivity: PR182 platform lane cancelled at the 15-min limit (CI_TEST_AUDIT.md "measured lane rebalance").
* Wall clock: 58 `datetime.now/time.time` uses; only 28 time-related monkeypatches; no freezegun-style abstraction. Mostly future-offset
  values (+1 h) so low risk. security.py limiter and tunnel deadlines read `time.monotonic()` directly -> untestable without sleeping.
* Ports: Docker publishes Postgres on fixed host ports - tests/integration/conftest.py:36 `--publish 127.0.0.1:55439:5432`,
  tests/stack_support.py:11 55440, e2e/loopback 8765-8769, aos_001 `_SMOKE_PORT = 8767`, test_aos_001 8757. Two concurrent runs
  (or the owner's review stack/another reviewer) collide; CI audit already admits a prior collision on 55440 and fixed the kernel
  fixture only ("Other historical fixtures retain their original default"). This conflicts with AGENTS.md "use disposable ports".
  CONFIRMED statically; CI is safe because each lane has its own VM.
* Ordering: session-scoped shared Postgres container (`r1_database`) with per-test uuid seeds; no pytest-randomly / xdist, so order
  independence is unverified (PLAUSIBLE risk for tests that `count(*)` global tables, e.g. `SELECT count(*) FROM panestria.task_event WHERE kind=...`).
* Network: none outside loopback in default tests (live excluded); good. No pytest-timeout plugin: hangs rely on per-call timeouts or the 15-min job limit.
* Retry/rerun masking: none configured (good).

---------------------------------------------------------------------------------------------------
## 6. Test-code quality / maintainability

* 10 `*_support.py` modules (~930 LOC) + 5 independently copy-pasted `_properties` helpers (e2e/test_r0_loopback.py:33, test_aos_005, aos_004,
  r0_*) + 44 test files that shell out to `git rev-parse HEAD` (+ `git status --porcelain` per test in autouse fixtures, e.g.
  contract/test_aos_002.py:21-29). Metadata plumbing (`record_property` in 204 test functions) is boilerplate that should live in one
  conftest hook. Identical-body helper clones: `migrate` x3, `_database` x3, `_wait_ready` x2 (scratchpad/dups.py).
* Fixtures: 95 `@pytest.fixture` in 76 files (3 conftests = 6 fixtures); sprawl is local, not global - acceptable.
* Cross-test coupling: 11 imports of private `_symbols` from src, ~50 `monkeypatch.setattr(..., "_private")`, one test loads another test module
  with importlib (e2e/test_r0_loopback.py:365-372), tests/conftest.py makes *unit* collection import `stack_support` (docker compose names).
* Size: 64 tests >= 80 lines with chained assertions (failure localisation poor); docs/testing has 100+ per-feature markdown files + 2 large JSON manifests
  that are updated by hand (test-catalog.json is already stale vs reality - F1).
* Runtime: fast lane 951 cases in ~19-30 s (good; slowest 2.0 s). Integration lanes: audit logs show ~4-10 min of test time per lane plus 1-6 min setup under a 15-min
  job timeout (CI_TEST_AUDIT.md) - little headroom (one lane already timed out once).
* Frontend: apps/mission-control has 4.4k LOC TypeScript and 546 lines of Playwright .mjs scripts driven from pytest; no unit/component tests, no a11y or visual checks (CONFIRMED by `ls`).

---------------------------------------------------------------------------------------------------
## 7. Findings (ranked)

### P1
**F1 [P1, CONFIRMED] Gate G3 (157 cases) cannot be evaluated from CI output; ~63% of required cases are unmapped.**
`python -m panestria.verification.readiness --gate G3` -> `required_count 157, registered_count 58, missing_case_ids 99, mapping_gap_case_ids 113,
live_required 25, live_mismatch 4, inventory_status GAPS`. 84 of 157 `planned_nodeid` files in docs/testing/test-catalog.json do not exist
(e.g. tests/integration/test_aos_013.py, test_aos_019.py ... test_aos_026.py, e2e/test_aos_023.py/028/030); whole families AOS-013, 019-026, 027b,
028-030 have 0 registered cases although ~1,400 research/Build/phone integration tests exist under other names with no `gate_case_id`
(only ~100 `record_property("gate_case_id"...)` calls). Catalog status: 137 NOT_RUN / 20 OBSERVED_PASS. The trusted gate evaluator
(AOS-030, docs/testing/TEST_EXECUTION.md "Gate evaluator contract") is not implemented (readiness.py is inventory only; verdict hard-wired NOT_EVALUATED).
Consequence: green CI says nothing about MVP gate coverage; tests exist but are not traceable to requirements.
Add: (a) a CI step `readiness --gate G3 --pretrial` that fails if `mapping_gap` grows (ratchet); (b) a conftest hook that stamps every
test with `gate_case_id`/candidate from a single mapping file instead of per-test `record_property`; (c) update catalog planned_nodeid to the real files.

**F2 [P1, CONFIRMED] Sandbox OS-boundary regression tests never run in CI.** `@pytest.mark.live` on test_aos_008.py:52 (uid/mounts/egress/limits), :117
(memory/output/time/pids pressure), :183 (read-only + private paths), :206 (failure cleanup); test_aos_017 (network none); test_sandboxed_verifier
(verifier_os_boundary); test_aos_027a (worker cannot weaken checks); test_native_tool_gateway x3; test_sandbox_cancellation x3. ci_tests.py:187 always passes `-m "not live"`,
yet ci.yml builds the pinned worker image on three lanes and the file header says "OS boundary tests use real pinned Docker containers; no mocked enforcement".
The only sandbox escape/limit evidence is therefore manual. Recommend: split `live` into `live` (needs subscription / hardware / model) and a new `docker_boundary`
marker that runs in the platform lane; keep only truly hardware/credential-dependent tests as `live`. Add a weekly scheduled CI job for `docker_boundary` if runtime is a concern.

**F3 [P1, CONFIRMED] No coverage measurement anywhere; fast feedback for stateful kernel/API logic is absent.** No coverage tool in dev group/CI (grep). Hermetic coverage 32.4 % line /
18.9 % branch; kernel/approvals.py 11.7 %, kernel/effects.py 16.0 %, kernel/scheduler.py 18.5 %, api/security.py 12.0 %, api/phone.py 23.9 %, verification/merge.py 0 %.
Mean fast lane 19 s, so there is room. Add: `uv run --with coverage` combined (unit+integration) coverage in a nightly full job with a published floor and per-module
floors for kernel/{approvals,effects,transition,leases,scheduler,quota}, api/{security,auth,phone}, sandbox/egress; plus pure-logic unit tests (below).

**F4 [P1, CONFIRMED] Parsers and canonicalisers on trust boundaries have no property-based or fuzz tests.** No Hypothesis (not installed; no `@given`). Candidates (ranked):
(1) `effect_digest` (key-order invariance, every-field sensitivity, golden vector), (2) `parse_cursor` (any str -> decimal-or-KernelDenied, round-trip < 2^63),
(3) `decode_frame` (never over-reads, never executes), (4) `BrowserSecurity` header handling (random duplicate/oversized/odd-case headers), (5) NFC passage offsets (half-open byte
spans round-trip), (6) `_public_unicast` vs a reference model built from `ipaddress` ranges (any address in a private/special range is denied),
(7) `validate_dag` (random graphs: accepted iff acyclic), (8) hand-rolled HTTP parser in R0 server (smuggling corpus).

**F5 [P1, CONFIRMED] BrowserSecurity envelope: five rejection branches with zero tests.** src/panestria/api/security.py:63-107 branches `headers_too_large` (431), `ambiguous_headers`
(duplicate Host/Origin/Authorization/Cookie/Content-Length/Content-Type/CSRF), `invalid_query`, `request_deadline_exceeded` (408 slow body), `invalid_body` (422) - grep of tests/ for these
codes/statuses: no hit (413/415/429 and credential-in-URL are covered in integration). Header smuggling/duplicate-Host is exactly the class that rebind/CSRF defences rely on.
Add a pure-ASGI unit test file `tests/unit/test_browser_security.py` (no DB): stub inner app, drive scope/receive/send; table of (headers, expected status/code) including
duplicate `Host`, `Host` with port/uppercase/trailing dot, `Origin: null`, 64+ query params, non-ASCII query, never-completing `receive()` (patch `asyncio.wait_for` timeout), invalid UTF-8 body,
limiter window rollover with monkeypatched `time.monotonic`, bucket eviction after 128 keys (assert an attacker cannot reset another client's bucket - see F9).

### P2
**F6 [P2, CONFIRMED logic / PLAUSIBLE impact] Verified-merge reuse ignores which profile the PR ran.** tools/ci_merge_proof.py:80-113 checks 6 successful jobs, 4 non-expired artifacts and identical
tree, but never reads `ci-*-selection.json` (profile / `deferred` list). A normal PR (profile `required`, 46 tests deferred) merged to main is then marked `already_tested`, behavioral jobs are skipped
(ci.yml test job) and the `full` profile does not run on main. So the 46 deferred tests only run when a PR touches their watch globs, or on direct pushes/manual dispatch. CI_REQUIRED_COVERAGE.md
presents "Direct/unverified push -> Full" as the safety net, but the usual path bypasses it. Fix: have the proof require `deferred == []` in all four selection artifacts, or schedule a nightly `ci.yml full` dispatch on main.

**F7 [P2, CONFIRMED] Watch-glob gaps for the legacy group.** `legacy-synthetic-journeys` watch (ci-regression-policy.json) lists specific kernel files but not `src/panestria/api/security.py`, `api/auth.py`,
`api/main.py`, `api/db.py`, `kernel/errors.py`, `kernel/policy.py`, `execution/protected_merge.py`, `execution/outbox.py`, `policy/**`. The deferred e2e journeys (test_aos_005.py `test_r0_positive_journey`,
`test_wait_restart_continuation`, test_r0_loopback.py) run through those modules, so a change there does not restore them. Fix: generate the watch list from an import-closure of the deferred test files (script
in scratchpad/closure.py shows the closure is ~217 modules wide because of package `__init__` imports - use `kernel/**`, `api/**`, `policy/**`, `execution/**` globs instead of enumerations).

**F8 [P2, CONFIRMED] "Hermetic" unit/contract tests are environment-dependent.** 11 of 951 fast cases fail outside the CI image: root user (production `HardwareProbe.collect` and native bootstrap refuse euid 0 - tests/unit/test_gpu_startup.py x2,
test_model_process_memory.py x3, test_bootstrap_pin_guards.py x2, test_native_proxy_relay.py:118 -> `native_*_platform_unavailable`/`nonroot_runtime_required`) and a different `uv` version
(contract/test_aos_001_toolchain.py x3 shell out to `uv run --frozen` / `make r0-demo`; pyproject `required-version = "0.12.3"` vs local 0.11.32). The same `ci-fast.xml` in evidence/ shows 951 tests / 11 failures.
Tests should skip with an explicit reason when the platform precondition is unmet (or be parametrised on a fake euid), otherwise a contributor on a different uv/root sandbox gets false reds and learns to ignore them.
Also tests/integration/test_connection_reviews.py:506+ hard-code `.venv/bin/alembic` while others use `uv run`.

**F9 [P2, PLAUSIBLE] Rate limiter robustness untested.** security.py:33-43: per-`client:route` bucket, `OrderedDict` capped at 128 with `popitem(last=False)`; an actor that can present >128 distinct
`scope["client"]` values (e.g. IPv6 /64 where allowed_clients is a prefix, or a proxy) evicts the pairing bucket and gets fresh attempts; 8-digit pairing code ("00000000" in test) at 5/min/client is the only brute-force control. No test
for eviction, window rollover or multi-client behaviour. Add the unit tests in F5 and a pairing-code lockout test (global, not per-IP, failure counter).

**F10 [P2, CONFIRMED] Mutation testing covers 3 files / 5 functions (~450 LOC of 55k).** pyproject [tool.mutmut] only_mutate = policy/engine.py, sandbox/egress.py, verification/entailment.py; manual `workflow_dispatch`
(mutation.yml). Result 294/318 detected (92.45 %); 22 of 24 survivors are error-message strings. Nothing on kernel/approvals, effects, transition, api/security, quota. Extend only_mutate to the pure-logic parts of those once unit tests exist (F3/F5), and run it
weekly rather than on demand.

**F11 [P2, CONFIRMED for effect_digest; PLAUSIBLE for other hashes] No golden/known-answer vector for effect digest or other canonical hashes.** approvals compare `effect_digest(preview)` against itself (e2e/test_aos_005.py:436); `contract_sha256` stability is tested for key-order but not against a stored constant. A serializer upgrade would
change every hash with all tests still green. Add one stored vector each for effect_digest, contract_sha256, quota observation hash, native connection reservation hash.

**F12 [P2, CONFIRMED] Fixed host ports for test infrastructure.** conftest.py:36 (55439), stack_support.py:11 (55440), 8765-8769 across ~20 files. Collides with parallel runs and the owner's review stack; conflicts with AGENTS.md ("disposable test database projects and ports").
Use `-p 127.0.0.1::5432` + `docker port`, and `bind_port=0` helpers. (Kernel fixture already migrated - CI_TEST_AUDIT.md.)

### P3
**F13 [P3, CONFIRMED]** `tests/contract/test_aos_001_toolchain.py:58 test_ci_does_not_inject_provider_credentials` text-polices ci.yml for the substring "secrets." - brittle (breaks the day any legitimate `secrets.GITHUB_TOKEN` is used; CI_TEST_AUDIT says such tests were removed). Replace with the existing secret-scan + workflow permissions linter (e.g. actionlint/zizmor) in the quality job.
**F14 [P3, CONFIRMED]** Evidence-pinned unit tests (`test_performance_history.py` x4, `test_native_entailment_probe.py:204`) fail if historical evidence under evidence/ is ever pruned; they test fixtures, not code. Move the small JSON subset into tests/fixtures.
**F15 [P3, CONFIRMED]** `record_property("aos_005_tc01", "NOT_RUN")` and similar cross-case NOT_RUN stamps in e2e helpers (test_aos_005.py:~54, test_r0_loopback.py:42) add noise to the evidence stream; 204 tests do manual metadata; 44 files spawn git per test. Centralise in a pytest plugin (`pytest_runtest_makereport` / session fixture; compute commit once).
**F16 [P3, CONFIRMED]** 64 tests >= 80 lines; split `test_concurrent_transition_and_cursor` (DAG validation / dependency persistence / race), `test_production_cli_tls_pairing_read_only_roles_revoke_and_desktop_scope`, `test_atomic_enqueue_and_duplicate` into focused tests sharing a fixture, so failures localise.
**F17 [P3, PLAUSIBLE]** Real-clock sleeps: test_invocations.py:153 (1.1 s TTL), test_r0_http.py:158 (0.6 s timing). Inject a clock or set TTL via DB `clock_timestamp()` offsets (already done in test_aos_009.py:304).
**F18 [P3, CONFIRMED]** `unit`/`contract` markers are decorative (26 uses) while layers are directory-based; either apply automatically in conftest (`pytest_collection_modifyitems`) so `pytest -m unit` works, or delete the markers and register `docker_boundary`.
**F19 [P3, CONFIRMED]** Frontend has no unit/a11y tests (4.4k LOC TS; 12 Playwright scripts only reachable through Python tests needing Chromium).
**F20 [P3, CONFIRMED]** 15-minute lane timeout with one recorded cancellation (PR182) and mirror stall; no `--timeout` per test; add pytest-timeout (e.g. 120 s default, explicit overrides) so a hang fails one test instead of a whole lane silently cancelled (a cancelled lane produces no XML).

---------------------------------------------------------------------------------------------------
## 8. Recommended tests to ADD (highest value first)

1. `tests/unit/test_browser_security.py` - pure ASGI table test (F5/F9). ~25 cases, no DB, < 1 s.
2. `tests/unit/test_effect_digest_properties.py` - Hypothesis: key order invariance, one-field-change => different digest, plus golden vector (F4/F11).
3. `tests/unit/test_cursor_properties.py` - Hypothesis over `parse_cursor`; round trip for 0..2^63-1; Unicode digits rejected.
4. `tests/unit/test_dag_properties.py` - Hypothesis random graphs vs networkx-free reference topological check.
5. `tests/unit/test_egress_reference_model.py` - for N random addresses from every IANA special-purpose registry block, `_public_unicast` must be None; and generated allowed addresses must pass; add `tunnel()` byte-cap/timeout and gateway admission (9th connection refused) tests with socketpair.
6. `tests/integration/test_approval_concurrency.py` - 8 threads x `decide`/`continue_after_approval` on the same approval: exactly one consumption, one effect, N-1 denials with stable codes; repeat 20 iterations.
7. `tests/integration/test_event_cursor_stress.py` - N writers committing/rolling back interleaved while a reader polls by cursor; assert no gap/dup and monotonic seq (guards the advisory-lock design).
8. `tests/integration/test_aos_008.py` (de-live the Docker boundary subset) - run in platform lane.
9. `tests/unit/test_pairing_lockout.py` - pairing code expiry, global failure counter, constant-time compare.
10. `tests/unit/test_http_parser_smuggling.py` - CL.CL, CL.TE, obs-fold, NUL, 10k headers against the R0 hand-rolled parser (tests/integration/test_r0_http.py `_parse` helper can be moved to unit).
11. Kernel transition-table unit test: for every (state, event) pair assert allowed/denied against the spec table (pure function), removing dependence on PG for 80 % of transition checks.

## 9. Tests to DELETE / convert (do not delete value, remove noise)

* Convert contract/test_aos_001_toolchain.py:58 (workflow text grep) to a linter step (F13).
* Move evidence-dependent assertions (unit/test_performance_history.py:12/:72/:93, test_native_entailment_probe.py:204) onto frozen tests/fixtures copies (F14).
* Fold unit/test_connection_contracts.py:171 and :184 (constructor echo) into a single parametrised "closed action set" test, or delete: they cannot fail unless the constructor is deleted.
* Replace e2e/test_r0_loopback.py:365 (loads another test module via importlib, port 8767) with a direct unit test of `owned_sockets`/`smoke_denial` (already unit-testable) and keep only the real-socket assertion.
* No wholesale deletions recommended: the suite has very little duplication-for-its-own-sake; the earlier audit (CI_TEST_AUDIT.md) already removed the worst offenders.

---------------------------------------------------------------------------------------------------
## 10. Scores (1-10; anchors: 1-2 absent, 3-4 major gaps, 5-6 works with significant gaps, 7-8 solid, 9-10 exemplary/evidence-verified)

| Dimension | Score | Justification |
|---|---|---|
| Test effectiveness | **7** | ~31 of 38 sampled tests clearly verify real behaviour and only 3 are weak (real Postgres, real git, real sockets, SIGKILL recovery); only 4 assert-free defs; mock-verifying-mock absent; doc-conformance ~1 %; mutation pilot 92.45 % detection (294/318). Deductions: 64 chained mega-tests, a few echo-constructor tests, private-symbol/SQL-order coupling. |
| Coverage of critical paths | **5** | Scenario breadth is excellent by inspection (approval digest/actor/expiry, effect loss, restore/downgrade, cursor >2^53, egress corpus) but nothing measures it: no coverage tool, hermetic 32 %/19 % branch, kernel approvals/effects/scheduler 12-19 %; sandbox OS-boundary tests are live-only; 99/157 G3 cases unregistered; 5 BrowserSecurity branches untested. |
| Adversarial / negative testing | **7** | Hostile-input culture is strong (32 unsafe IPs, scoped IPv6, TOCTOU path swap, symlink escapes, forged correlation ids, injected HTML, byte-wise stream splitting, SIGKILL at commit boundaries, wrong-actor/digest/expiry/foreign-project). Capped by zero Hypothesis/fuzzing, 2-thread-single-shot concurrency, and the untested envelope branches. |
| CI / release-gate integrity | **5** | Well engineered (SHA-pinned actions, exactly-once partition verified, fail-closed selector validation, aggregate check, mutation witnesses undeferrable) but: required profile reuse via merge-proof never verifies full profile (F6), watch-glob gaps (F7), live/boundary tests excluded (F2), no evaluator/mapping for G3 (F1), no coverage gate, 15-min lane with one recorded timeout. Green CI != gate evidence (the repo says so itself, which is honest). |
| Test maintainability | **5** | Clear naming and local fixtures, honest docs; but metadata boilerplate x204, five copied `_properties`, 44 git-spawning files, fixed ports, env-dependent "hermetic" tests (11 red outside CI image), 100+ hand-maintained docs/testing files and a stale catalog. |

Overall: a rare, behaviour-first suite with unusually good honesty about its limits; the remaining risk is mostly *visibility* (coverage, gate mapping, CI scope) rather than weak assertions.

## Appendix: commands / artefacts
* Coverage data: scratchpad/.coverage, cov.json, cov_run.log (11 env failures listed).
* AST/dup scripts: scratchpad/stats.py, dups.py, sample.py, closure.py.
* `python -m panestria.verification.readiness --gate G3` output summarised in F1.
* Port/sleep/time greps: see section 5.
