# Code Quality Review: src/panestria and tests

Scope: `src/panestria` (359 files, 55,281 physical LOC, 49,270 SLOC) and `tests` (262 files, 52,336 LOC). Read-only; no repo files changed.

Tools: Python `ast` scripts (`scratchpad/quality/analyze.py`, `dup2.py`, `agg.py`), radon 6.x via `uv tool run` (cc -j, cc -s -a, mi -s), vulture via `uvx` (80% and 60%), ruff from `.venv`. Raw outputs are in `scratchpad/quality/`.

Notes on method:
- `ops/` (1 file) is included as its own package. Top-level `config_*.py` are grouped.
- Function counts from AST include nested functions. Radon counts (1,866 functions/methods) exclude class entries.
- Duplication uses normalized node-type shingles (6-grams, Jaccard) over functions with >=8 statements (320 functions). An exact normalized-hash pass (identifiers and literals abstracted) found 0 clusters.
- Dead-code and private-access numbers are heuristic. Each one is qualified below.

## 1. Per-package structure and complexity

| Package | Files | LOC | Fns | Cls | Mean fn len | Max fn len | >50 | >100 | Max nest | Mean CC | Max CC | CC>10 | Pub fn doc | Pub cls doc |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| execution | 56 | 13,071 | 435 | 72 | 25.5 | 235 | 60 | 27 | 6 | 5.93 | 54 | 63 | 16% | 3% |
| kernel | 58 | 10,610 | 323 | 88 | 27.2 | 225 | 56 | 8 | 7 | 6.97 | 79 | 66 | 8% | 2% |
| cli | 33 | 6,403 | 284 | 21 | 18.5 | 228 | 21 | 2 | 13 | 4.85 | 104 | 28 | 53% | 5% |
| api | 38 | 5,190 | 232 | 47 | 16.6 | 207 | 12 | 4 | 6 | 4.42 | 60 | 13 | 5% | 7% |
| contracts | 61 | 4,349 | 149 | 202 | 7.5 | 41 | 0 | 0 | 5 | 4.33 | 26 | 16 | 10% | 4% |
| brokers | 22 | 4,333 | 143 | 50 | 24.0 | 271 | 18 | 5 | 10 | 8.36 | 106 | 35 | 26% | 9% |
| sandbox | 13 | 2,322 | 92 | 34 | 19.8 | 163 | 7 | 3 | 7 | 7.92 | 49 | 20 | 19% | 23% |
| verification | 17 | 2,109 | 62 | 33 | 24.7 | 143 | 9 | 1 | 6 | 8.48 | 46 | 14 | 14% | 0% |
| memory | 13 | 1,728 | 70 | 22 | 18.1 | 94 | 2 | 0 | 4 | 4.57 | 20 | 7 | 2% | 10% |
| inference | 8 | 1,084 | 43 | 8 | 20.5 | 133 | 5 | 2 | 5 | 7.38 | 47 | 8 | 16% | 0% |
| resources | 9 | 1,062 | 40 | 17 | 18.5 | 95 | 4 | 0 | 6 | 7.10 | 29 | 10 | 8% | 19% |
| telemetry | 5 | 815 | 25 | 7 | 23.5 | 142 | 4 | 1 | 5 | 8.42 | 39 | 5 | 25% | 0% |
| top-level config_*.py | 12 | 783 | 36 | 14 | 10.6 | 31 | 0 | 0 | 3 | 6.17 | 22 | 5 | 10% | 7% |
| learning | 3 | 672 | 24 | 3 | 24.3 | 89 | 2 | 0 | 4 | 6.17 | 29 | 4 | 0% | 0% |
| top-level other (demo, review, __init__) | 3 | 435 | 13 | 1 | 29.5 | 165 | 2 | 1 | 4 | 6.30 | 29 | 1 | 0% | 0% |
| policy | 7 | 274 | 6 | 7 | 29.8 | 52 | 1 | 0 | 3 | 15.67 | 27 | 4 | 0% | 0% |
| ops | 1 | 41 | 2 | 1 | 11.5 | 20 | 0 | 0 | 2 | 4.50 | 8 | 0 | 100% | 100% |
| **Total** | **359** | **55,281** | **1,979** | **627** | **21.2** | **271** | **203** | **54** | **13** | **6.11** | **106** | **300** | **19%** | **6%** |

- Functions over 50 lines: 203 (10.3%). Over 100 lines: 54 (2.7%). Those 54 functions hold 7,900 lines, or 14.3% of src LOC.
- Radon cyclomatic complexity over 1,866 functions and methods: mean 6.11. CC>10: 300 (16%). CC>20: 104 (5.6%).
- Radon maintainability index: 342 files grade A, 11 grade B, 6 grade C. Grade C files: `brokers/harness/event_parser.py`, `cli/tui.py`, `execution/synthetic_journey.py` (MI 0.00), `execution/proposal_demo.py` (6.79), `sandbox/runner.py` (7.77), `brokers/harness/mock.py` (7.86).
- Mean CC for `policy` (15.67) rests on 6 functions and is not comparable.
- Deepest nesting: `cli/build_tui.py:263 run` (13), `cli/research_review_terminal.py:76 key` (12), `brokers/harness/command_stdio.py:71 _pump` (10), `cli/tui.py:306 run` (9), `brokers/harness/command_protocol.py:209 prepare` (9).

### Top 25 most complex functions (radon CC)

| # | CC | file:line | function | length |
|---|---|---|---|---|
| 1 | 106 | `src/panestria/brokers/harness/event_parser.py:168` | `_frame` | 271 |
| 2 | 104 | `src/panestria/cli/tui.py:306` | `run` | 228 |
| 3 | 79 | `src/panestria/kernel/plan_returns.py:55` | `release` | 225 |
| 4 | 78 | `src/panestria/kernel/build_progress.py:31` | `inspect` | 220 |
| 5 | 74 | `src/panestria/brokers/research/reader.py:54` | `extract` | 199 |
| 6 | 60 | `src/panestria/api/mission_web.py:21` | `mount_mission_control` | 207 |
| 7 | 54 | `src/panestria/execution/native_build.py:214` | `run` | 235 |
| 8 | 53 | `src/panestria/execution/offline_build.py:36` | `capture_reference` | 190 |
| 9 | 49 | `src/panestria/sandbox/gitcmd.py:16` | `allow_git` | 58 |
| 10 | 48 | `src/panestria/kernel/plan_revisions.py:25` | `propose` | 197 |
| 11 | 47 | `src/panestria/inference/runtime.py:141` | `_start` | 133 |
| 12 | 46 | `src/panestria/verification/readiness.py:164` | `build_inventory` | 72 |
| 13 | 46 | `src/panestria/brokers/harness/command_stdio.py:71` | `_pump` | 80 |
| 14 | 45 | `src/panestria/brokers/harness/event_parser.py:440` | `_mcp_metadata` | 90 |
| 15 | 44 | `src/panestria/sandbox/runner.py:413` | `_execute` | 163 |
| 16 | 43 | `src/panestria/sandbox/runner.py:107` | `run` | 139 |
| 17 | 40 | `src/panestria/execution/local_repair.py:58` | `_basis_in` | 103 |
| 18 | 39 | `src/panestria/telemetry/performance.py:110` | `collect_performance` | 142 |
| 19 | 39 | `src/panestria/sandbox/runner.py:352` | `_validate_effective` | 60 |
| 20 | 39 | `src/panestria/kernel/plan_lifecycle.py:80` | `cancel` | 127 |
| 21 | 38 | `src/panestria/execution/offline_build.py:228` | `read_reference` | 100 |
| 22 | 38 | `src/panestria/execution/local_plan.py:208` | `propose` | 136 |
| 23 | 37 | `src/panestria/verification/candidate.py:22` | `capture_candidate` | 100 |
| 24 | 37 | `src/panestria/execution/build_metrics.py:25` | `capture_build_metrics` | 147 |
| 25 | 37 | `src/panestria/cli/tui.py:103` | `drain` | 87 |

Columns: radon CC, then AST span (lines from `def` to end of body). All spans were measured.

### Longest functions (AST span)

Longest: `execution/native_build.py:214 run` (235 lines), `cli/tui.py:306 run` (228), `kernel/plan_returns.py:55 release` (225), `kernel/build_progress.py:31 inspect` (220), `api/mission_web.py:21 mount_mission_control` (207 lines, 13 parameters), `execution/research_sources.py:105 commit_fetch` (208), `brokers/research/reader.py:54 extract` (199).

## 2. Docstring coverage (Google style)

- Public modules with a module docstring: 339/339 (100%).
- Public functions with any docstring: 244/1,269 (19.2%). Public classes with any docstring: 35/610 (5.7%).
- Functions with parameters, a docstring, and an `Args:` section: 0 of 237 (0%). Functions returning a value and carrying a `Returns:` section: 0. Functions raising and carrying a `Raises:` section: 0. The grep for `Args:`, `Returns:`, `Raises:` across `src/` returns 0 matches.
- ruff pydocstyle (google convention, `src` only): 1,620 errors. D103 298, D102 599, D101 571, D107 140, D105 12, D100 0.
- Worst files by missing public docstrings:
  `contracts/connections.py` (20), `execution/proposal_demo.py` (19), `cli/build_tui.py` (19), `cli/tui.py` (18), `kernel/repositories/approvals.py` (17), `contracts/research.py` (17), `contracts/plan.py` (17), `api/proposal_demo.py` (17), `sandbox/native_tool_gateway.py` (14), `api/health.py` (14).

Assessment: docstrings exist where they exist, and prose quality was not reviewed. The Google-style structured sections are absent entirely.

## 3. Type hints

- Functions fully annotated (all parameters and return; `__init__` exempt on return): 1,979/1,979 (100%).
- `Any` tokens in `src`: 373 textual occurrences (including imports). ruff ANN401 flags 24 explicit `Any` annotations.
- `cast(`: 13. `# type: ignore`: 10. `# noqa`: 1 (no bare `noqa`).
- mypy strict was not re-run by me. CI runs `uv run --frozen mypy src/panestria` (`.github/workflows/ci.yml:71`), so it is covered by CI.

## 4. Pythonic smells

| Smell | Count | Notes / examples |
|---|---|---|
| Bare `except:` | 0 | |
| `except Exception` swallowed (body only pass / continue / const return) | 16 | `brokers/research/pdf_worker.py:168`, `execution/build_plan.py:262`, `execution/local_repair.py:317`, `execution/mission_run.py:63`, `:101`, `:114` |
| `except <type>: pass` (all types) | 50 | Exception 15, OSError 8, curses.error 8, ProcessLookupError 6, other 13. Examples: `api/health.py:325`, `api/health.py:240`, `api/routes/ask.py:278` |
| Mutable default arguments | 0 | |
| `global` statements | 1 | `execution/task_workflow.py:40` (`_datasource`) |
| `assert` in production code (ruff S101) | 141 | Stripped under `python -O`; these are invariant checks, not tests |
| String `+=` in loops | 0 | |
| `== None` / `!= None` | 0 | |
| `len(x) == 0` style | 0 | |
| `for i in range(len(...))` | 0 | |
| Functions with >6 parameters | 74 | execution 21, kernel 20, cli 12, verification 9. Worst: `verification/nodes.py:355 _report` (15), `verification/build.py:30 verify_build` (14), `api/mission_web.py:21 mount_mission_control` (13), `kernel/repositories/approvals.py:65 insert_request` (12), `verification/nodes.py:76 evaluate_checks` (12) |
| Modules >1000 lines | 2 | `execution/synthetic_journey.py` (1,082), `execution/proposal_demo.py` (1,006) |
| Classes >500 lines | 2 | `execution/proposal_demo.py:175 ProposalDemo` (832), `execution/synthetic_journey.py:75 SyntheticJourney` (765). Also 20 classes >300 lines. |
| `print()` in library code (outside `cli/`) | 12 | api 3, brokers 3, verification 2, execution 2, inference 1, sandbox 1 (cli has 5, which is acceptable) |
| Private member access on non-self objects (`x._y`) | 70 | kernel 35, execution 29, cli 3, api 2, memory 1 (heuristic; includes some false positives) |
| Private names imported across modules (`from m import _x`) | 96 in 65 statements | `execution.proposal_demo` 21, `cli.build` 12, `api.routes.ask` 12, `api.routes.goals` 10, `cli.research` 7 |
| Duplicated magic strings (>=3 sites) | several | `UNAVAILABLE` 71, `NOT_ASSESSED` 57, `schema_version` 53, `^[0-9a-f]{64}$` regex 48, `RESTRICTED` 45, `database_unavailable` 36, `version_conflict` 36, `PANESTRIA_DATABASE_URL` 32, `effect_digest` 30 |
| Duplicated magic numbers | several | `1024` (247), `3` (176), `5` (115), `4` (115), `16` (95), `128` (79), `200` (75), `256` (61). Many are likely limits; no named-constant audit done. |

Note on the private-access and private-import counts: the first is an AST attribute heuristic, the second is exact for `from ... import _name`. The second surfaces coupling that the first misses.

### ruff (project config E,F,I,B)

- `ruff check src tests`: All checks passed.

### ruff stricter sets (`--select ALL`, src, `--exit-zero`), top categories

EM101 2,302 (raw string in exception), COM812 551, PLR2004 472 (magic value), CPY001 359 (copyright notice; not applicable), TRY301 334, D103/D102/D101 about 1,470 combined, TC001 185, S101 141, C901 122, BLE001 121 (blind except), PLR0913 120, TC003 98, PLR0917 80, PLR0912 71, SLF001 69 (private member access), FBT003 66, TRY003 63, PLR0915 49.

Remaining categories are minor. Of note: `ruff format --check src tests` reports 74 files would be reformatted (548 already formatted). CI does not enforce formatting: `.github/workflows/ci.yml:66-71` runs `ruff check .` and `mypy`, and the Makefile `lint` target runs `ruff check` only.

## 5. Duplication

- Exact normalized-AST clusters (identifiers and literals abstracted, functions >=8 statements): 0.
- Shingle Jaccard >= 0.6: 5 pairs. Jaccard 0.4 to 0.6: 14 more pairs.

| J | Function A | Function B | Lines (A / B) | Assessment |
|---|---|---|---|---|
| 0.90 | `kernel/activity.py:12 project_activity` | `kernel/review_inbox.py:12 review_inbox` | 86 / 71 | Strong near-clone. Merge candidate. |
| 0.72 | `api/routes/approvals.py:93 decide_approval` | `api/routes/goals.py:39 submit_goal` | 19 / 22 | Route boilerplate. Shared helper candidate. |
| 0.63 | `brokers/harness/account_profile.py:32 inspect` | `:43 collect` | 69 / 45 | `collect` is nested inside `inspect` (lines 43 onward). Self-similarity, not a true duplicate. Not a merge candidate. |
| 0.62 | `kernel/effects.py:227 finish` | `:282 reconciled` | 28 / 24 | Merge candidate. |
| 0.62 | `execution/task_workflow.py:103 _transition_body` | `:199 _mark_failed_body` | 44 / 32 | Merge candidate. `_lease_body` (:298) is at 0.48 to `_mark_failed_body`. |
| 0.57 | `config_plan.py:28 load_plan_settings` | `config_synthesis.py:23 load_synthesis_settings` | 17 / 17 | Template loader. Shared helper candidate. |
| 0.53 | `api/main.py:111 mount_browser_api` | `:125 mount_ask_api` | 12 / 13 | Shared mount helper candidate. |
| 0.51 | `execution/research_query_plan.py:63 _current` | `execution/research_synthesis.py:186 _current` | 46 / 30 | Same name, similar body. Shared helper candidate. |

## 6. Dead code

Vulture, `src/panestria` at 80% confidence: 6 findings, all "unused variable" at 100%. Each is a parameter of an overridden or protocol method (OpenTelemetry span processor, `HTMLParser` override, a Protocol signature, a signal callback). All are false positives for deletion:
- `telemetry/tracing.py:59` `parent_context`, `:92` `timeout_millis`
- `brokers/research/reader_worker.py:47` and `:56` `attrs`
- `contracts/inference.py:71` `upper_cash_microusd`
- `inference/runtime_bridge.py:133` `signum`

Vulture at 60% (src and tests): 394 lines. Mostly FastAPI and Typer handlers registered by decorator. Not dead.

AST estimate (undecorated functions and classes whose name appears only at its definition across `src` and `tests`): 6 functions, 47 lines, plus 2 classes.
- Not dead, interface overrides: `telemetry/tracing.py:59 on_start`, `:62 on_end` (26 lines), `:92 force_flush`; `brokers/research/reader_worker.py:56 handle_startendtag`, `:62 handle_endtag`.
- Genuinely unreferenced:
  - `kernel/repositories/approvals.py:147 database_now` (5 lines)
  - `brokers/research/search.py:37 SearchProvider` (Protocol, 8 lines)
  - `brokers/harness/mock.py:54 WorkerAdapter` (Protocol, 21 lines). `MockWorkerAdapter` at `:88` is a different, used class.

Confirmed dead: about 34 lines. Decorated definitions (364) were excluded from the AST estimate, so route-level dead code is not assessed.

## 7. Naming

- Non-snake_case functions: 3, all `do_GET` / `do_POST` (`BaseHTTPRequestHandler` overrides, stdlib-mandated). `inference/runtime_bridge.py:30, :33`, `review.py:94`.
- Non-CapWords classes: 0. Names longer than 40 characters (functions, classes, variables): 0.
- Single-letter variables outside comprehensions: 203, mostly `c` (162; e.g. `with self.connect() as c:`).
- Single-letter arguments: 94, mostly `u` (38) and `c` (32).

## 8. Tests

- Test LOC to src LOC overall: 52,336 / 55,281 = 0.95.
- Test LOC by package (test files attributed to the `panestria.<pkg>` modules they import, split evenly; approximate):

| Package | src LOC | test LOC (approx) | ratio |
|---|---|---|---|
| execution | 13,071 | ~5,062 | 0.39 |
| kernel | 10,610 | ~11,172 | 1.05 |
| cli | 6,403 | ~4,717 | 0.74 |
| api | 5,190 | ~3,202 | 0.62 |
| contracts | 4,349 | ~8,567 | 1.97 |
| brokers | 4,333 | ~4,325 | 1.00 |
| sandbox | 2,322 | ~3,790 | 1.63 |
| verification | 2,109 | ~1,644 | 0.78 |
| memory | 1,728 | ~1,211 | 0.70 |
| inference | 1,084 | ~1,834 | 1.69 |
| resources | 1,062 | ~1,398 | 1.32 |
| telemetry | 815 | ~484 | 0.59 |
| config_*.py | 783 | ~2,953 | 3.77 |
| learning | 672 | ~128 | 0.19 |
| policy | 274 | ~1,297 | 4.73 |

Attribution is approximate; 416 test LOC import no `panestria` package. `execution` (0.39) and `learning` (0.19) are the least-tested by this measure.

- Test functions: 1,236. Without any assertion (no `assert`, `pytest.raises`, `assert*` call, or `approx`): 3.
  - `tests/integration/test_owner_build_cli.py:254`, `:260`
  - `tests/unit/test_egress_addresses.py:85`
  These may assert through helpers. Not inspected.

## 9. Scores (1-10)

| Dimension | Score | Justification |
|---|---|---|
| Pythonic idiom | **6** | Clean on the classic traps: 0 bare excepts, 0 mutable defaults, 0 `== None`, 0 `range(len)`, 0 string `+=` in loops. Deductions: 74 functions with >6 params; 16 swallowed `except Exception` and 50 `except ...: pass`; 141 `assert` in production; 96 cross-module private imports and 70 private attribute accesses. |
| Google style conformance (docstrings / naming / typing) | **4** | 0 of 237 documented functions use Google `Args:`/`Returns:`/`Raises:` sections. Public functions 19% documented, public classes 6%. ruff D: 1,620 src errors. Strengths: 100% fully annotated, 100% module docstrings, naming essentially clean. |
| Minimalism / complexity | **4** | 54 functions >100 lines (14.3% of src LOC); 104 functions with CC>20; max CC 106; 20 classes >300 lines; 3 files at MI 0.00. Offsets: mean function length 21 lines; 342 of 359 files grade A. |
| Duplication / dead code | **7** | No exact clones; 5 pairs at J>=0.6; ~34 lines confirmed dead. Dead-code scan has high false-positive rate, and interface overrides and decorated handlers were excluded. Deduction: ~2,100 lines of demo/synthetic harness live in the runtime package, and production modules import private helpers from them. |
| Readability | **5** | Module docs 100%, mean function 21 lines, tests 0.95x src. Offset by 3 functions with CC>100, two modules >1,000 lines, inconsistent formatting (74 files would reformat, not enforced in CI), and 0 structured docstring sections for callers. |

## 10. Lean-up candidates (ranked)

Ranked by expected benefit to size and navigability. LOC savings are estimates from the measured spans. Items 1 and 2 are the highest value.

1. **Move demo / synthetic harness out of the runtime package, and un-private the shared helpers.** `src/panestria/execution/synthetic_journey.py` (1,082 LOC; `SyntheticJourney` 765 lines) and `src/panestria/execution/proposal_demo.py` (1,006 LOC; `ProposalDemo` 832 lines), plus `api/proposal_demo.py` and `cli/review_demo.py`. Production modules import `_lock`, `_private`, `_atomic`, `_git` from `proposal_demo` (for example `execution/owner_build.py:26`, `execution/background_run.py:15`, `execution/native_plan.py:32`, `execution/local_plan.py:27`). `api/serve.py:70` and `execution/task_workflow.py:351` lazily import `SyntheticJourney`. Action: move the helpers to a neutral module (for example `execution/fs_locks.py`) and move the demo/journey code out of the shipped package. Estimated saving: ~2,100 LOC out of the runtime package (about 3.8% of src); no change in behaviour.
2. **Shared-helper merges for near-duplicates.** Estimated saving ~130 LOC in total:
   - `kernel/activity.py:12` `project_activity` and `kernel/review_inbox.py:12` `review_inbox` (J 0.90): ~55 LOC.
   - `execution/task_workflow.py:103` `_transition_body` and `:199` `_mark_failed_body` (J 0.62): ~20 LOC.
   - `kernel/effects.py:227` `finish` and `:282` `reconciled` (J 0.62): ~15 LOC.
   - `execution/research_query_plan.py:63` `_current` and `execution/research_synthesis.py:186` `_current` (J 0.51): ~15 LOC.
   - `api/routes/approvals.py:93` `decide_approval` and `api/routes/goals.py:39` `submit_goal` (J 0.72): ~12 LOC.
   - `config_plan.py:28` `load_plan_settings` and `config_synthesis.py:23` `load_synthesis_settings` (J 0.57): ~10 LOC.
   - `api/main.py:111` `mount_browser_api` and `:125` `mount_ask_api` (J 0.53): ~6 LOC.
   Not a merge: `brokers/harness/account_profile.py:32 inspect` / `:43 collect` (nested helper).
3. **Delete confirmed dead code.** ~34 LOC:
   - `brokers/harness/mock.py:54` `WorkerAdapter` (Protocol, 21 lines)
   - `brokers/research/search.py:37` `SearchProvider` (Protocol, 8 lines)
   - `kernel/repositories/approvals.py:147` `database_now` (5 lines)
   Do not delete: OTel overrides in `telemetry/tracing.py`, `HTMLParser` overrides in `brokers/research/reader_worker.py`, decorated handlers, and the Protocol parameter `contracts/inference.py:71`.
4. **Refactor the longest and most complex functions** by extracting helpers or dispatch tables. Estimated saving 15-25% of their length, roughly 300-500 LOC across the group. Ranked by length and CC:
   - `brokers/harness/event_parser.py:168 _frame`: 271 lines, CC 106 (repo maximum)
   - `execution/native_build.py:214 run`: 235 lines, CC 54
   - `cli/tui.py:306 run`: 228 lines, CC 104; nesting 9
   - `kernel/plan_returns.py:55 release`: 225 lines, CC 79
   - `kernel/build_progress.py:31 inspect`: 220 lines, CC 78
   - `brokers/research/reader.py:54 extract`: 199 lines, CC 74
   - `api/mission_web.py:21 mount_mission_control`: 207 lines, CC 60, 13 parameters
   - `execution/offline_build.py:36 capture_reference`: 190 lines, CC 53
   - `kernel/plan_revisions.py:25 propose`: 197 lines, CC 48, 8 parameters
   - `sandbox/runner.py:413 _execute`: 163 lines, CC 44
   Also `cli/build_tui.py:263 run` (nesting 13), `cli/research_review_terminal.py:76 key` (nesting 12).
5. **Split large modules for navigation** (0 LOC change). `cli/plan.py` (673), `sandbox/runner.py` (575; `DockerSandbox` 497 lines), `brokers/harness/event_parser.py` (563; `ClaudeEventParser` 449), `cli/tui.py` (561; `AskTerminal` 462), `kernel/build.py` (554; `BuildEvidenceService` 362).
6. **Consolidate repeated literals into named constants.** The 48 copies of the 64-hex regex `^[0-9a-f]{64}$`, plus 32 uses of `PANESTRIA_DATABASE_URL`. Estimated saving ~40 LOC of duplicated literals; mainly a consistency gain.
7. **Enforce formatting.** `ruff format --check src tests` reports 74 files to reformat. CI runs only `ruff check` and `mypy`. Add a format check or run `ruff format` once to baseline, to lock style.

## Summary of key findings

- CI: `ruff check` passes and `mypy` runs. Formatting is not enforced in CI (74 files would reformat).
- Docstrings: 0 Google `Args:` / `Returns:` / `Raises:` sections in `src`. 19% public functions and 6% public classes documented.
- Complexity: 54 functions over 100 lines (14% of src LOC); max CC 106 in `brokers/harness/event_parser.py:168 _frame`.
- Structure: `execution/proposal_demo.py` and `execution/synthetic_journey.py` both exceed 1,000 lines, and production modules depend on private helpers from `proposal_demo`.
- Duplication: no exact clones; 5 near-clone pairs at Jaccard >= 0.6, one at 0.90.
- Dead code: ~34 LOC confirmed; the vulture findings are false positives.
- Tests: 0.95x src LOC overall; `execution` (0.39) and `learning` (0.19) are the least covered by this measure.
