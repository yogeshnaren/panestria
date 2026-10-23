# CI test audit and execution lanes

## Active policy — 2026-10-22 owner-requested reduction

The [required/full policy](CI_REQUIRED_COVERAGE.md) supersedes the historical
always-full execution description below. PRs keep all unit/contract checks,
current functional/security/approval journeys, mutation witnesses and real restore
coverage. Only 46 explicitly reviewed old synthetic-demo/domain restore functions
become conditional regressions. Relevant source/test/helper changes restore them;
CI policy changes, unknown bases and unverified pushes use full coverage. No test
body, release requirement or original evidence is removed.

Unrelated required coverage collects 2,253 cases; full collects 2,299 (65 live
cases remain separately excluded). The 46 deferred cases consumed 167.862 seconds
in original run39842217044, not a guaranteed future saving. Ledger/activity families
rebalance the same four runners. The old case timings project roughly237/250
seconds for required kernel/platform, excluding setup and quality serialization.
Actual workflow timings must establish the result.

Main is currently unprotected. A direct/unverified push still runs full CI.
Only a main merge with an existing passing PR run, all six successful jobs,
four nonexpired same-preview artifacts, exact merge parents and identical tree
can reuse that result. Unavailable metadata runs checks; this optional proof is
bounded to twenty seconds. The retained JSON identifies the upstream source/run.
Reuse is not fresh execution or release evidence. See the
[implementation report](../../evidence/ci-required-coverage-2026-10-22/report.json).

## Historical full-suite audit

This change reviews the existing suite rather than replacing it with a smoke
allowlist. The baseline is main `723153849ae3c9982fdc2df9f1d70285a8420831`:
161 test files, 998 statically discovered test definitions and 2,101 selected
non-live pytest cases. Definition counts differ from parametrized-case counts; pytest collection
is the authoritative executed-case inventory.

## Findings

Successful run [39203960738](https://github.com/yogeshnaren/panestria/actions/runs/39203960738)
took 12m38s for its job, including 11m59s in the serial Tests step (pytest reported
716.56s). Ruff, lock and dependency synchronization together took about a second;
Mypy took 16s. This was mostly real runtime work, not a large lint bottleneck.

An AST/import/fixture inventory covered every test file. Detailed review focused
on bootstrap/toolchain self-tests, static text assertions, custom verification
tests, shared fixture imports and the slowest runtime files. There were no
imported `test_*` functions being recollected under additional test modules.
Shared imports are fixtures/helpers; removing them would remove functionality.

The slowest completion-line deltas in that log were worker/recovery tests
(AOS-004 about 47s), approval/CLI E2E (AOS-005 about 42s), research source records
(36s), isolated PDF extraction (31s) and search admission (29s). These are
approximate **file completion deltas**, not per-test profiler measurements.
They exercise real database, subprocess, sandbox or HTTP behavior and remain.

## Removed or consolidated

| Previous check | Decision / replacement |
| --- | --- |
| Installed-package import subprocess | Remove duplicate: package install/version/license and API/CLI behavior remain tested. |
| Run production import boundaries inside pytest | Remove duplicate: dedicated quality job runs Import Linter once. |
| Synthetic allowed/forbidden Import Linter projects | Remove third-party tool self-tests; production boundary configuration is still enforced. |
| Run `uv lock --check` inside pytest | Remove duplicate: dedicated quality job checks the real lock. |
| Deliberately stale temporary lockfile | Remove uv self-test; frozen dependency installation remains mandatory. |
| Run production Ruff/Mypy again inside pytest | Remove duplicate full-repository scans. |
| Deliberately unused import/type mismatch | Remove third-party Ruff/Mypy self-tests. |
| Start nested pytest to prove `assert False` fails | Remove test-runner self-test. |
| Compare CI commands with a copied exact tuple | Remove brittle implementation-text assertion. New CI is exercised by actual jobs. |
| Run `make bootstrap` inside pytest | Remove redundant dependency installation during the suite. |
| Inspect dry-run `make test` command spelling | Remove command-text check; each actual CI suite explicitly excludes live cases. |
| Assert contributor/security docs contain specific phrases | Remove stale text policing; secret scan still covers tracked documents. |
| Production secret scan inside pytest | Run once in quality. Keep the custom scanner's real sentinel/redaction behavior test. |
| Package-name migration strings, source-wide `pip install` search and exact internal function signatures | Remove shallow implementation assertions. Keep actual installation, original license, settings validation, health API and CLI behavior. |

This removes 13 selected cases (2,101 → 2,088), plus redundant assertions and
whole-tool invocations. It is deliberately not a percentage-based deletion
target. Most cases are inexpensive contract/security parameters with distinct
failure modes; deleting them would save little time and weaken detection.

Custom verifier/readiness tests are retained: their synthetic passing/failing
inputs test **Panestria's own production verifier/evidence code**, including
false-done and mock-for-live rejection. They are not merely tests of pytest.
Older R0 recovery, ownership and approval tests still protect current code.
Live tests, original evidence and release requirements are unchanged.
One invalid-version UUID parameter is now a fixed UUIDv1 with a descriptive ID;
its former collection-time `uuid1()` changed the node ID on every collection.
The rejection behavior remains covered, with reproducible rerun/evidence IDs.
Two adversarial-frame groups also use concise parameter IDs instead of printing
thousands of payload bytes in failure/duration names; all original payloads stay.

## CI structure

`quality` runs lock, frozen install, Ruff, Mypy, import boundaries and secret scan
once. Four isolated behavioral jobs run concurrently:

| Suite | Content | Approximate serial baseline weight |
| --- | --- | --- |
| `fast` | All unit and contract files | 16s |
| `kernel` | E2E plus R0/kernel integration files | 223s |
| `platform` | Remaining integration, including new files by default | 207s |
| `research` | Research, search/fetch/reader/PDF/provenance integration | 260s |

Weights come from old log completion lines and help choose balanced lanes; they
are **not** promised new runtimes. Each worker gets its own hosted VM. Fixed
synthetic database ports and Docker fixtures therefore cannot collide across
lanes, and no pytest-xdist/shared-database concurrency is introduced. The fast
lane does not prepare a Docker image. No additional Python dependency is needed.

`tools/ci_tests.py` uses pytest's configured file patterns (both default forms,
`test_*.py` and `*_test.py`, when unspecified), assigns each file once and
rejects unknown test directories or empty lanes. New integration files default
to platform; no changed-files guess or manually maintained test allowlist can
silently omit them. Local `make test` still runs the complete non-live suite.

The existing required `test` check is an aggregate: it fails if quality or any
behavioral lane fails, is cancelled or is skipped. All jobs are required for
success. Obsolete PR runs are still cancelled. Actions stay SHA-pinned, workflow
permissions are read-only, and no provider credentials or live calls are added.

Each behavioral lane prints its 25 slowest durations and retains its JUnit file
as a seven-day GitHub artifact, including on failure. This makes the next audit
data-driven instead of guessing which assertions cost time. Parallel jobs may
use slightly more setup runner-minutes; the measured wall-time result is reported
on the PR. Release G1/G2/G3 remain separate from passing default CI.

## Existing failure kept visible

Main run [39205167510](https://github.com/yogeshnaren/panestria/actions/runs/39205167510)
failed on concurrent owner research-policy preparation. A duplicate scoped
project key escaped `ON CONFLICT(id)` because the table also has `(id,owner_id)`
uniqueness. That test remains in the research lane. Its separate prerequisite
fix handles either unique conflict and still checks the current owner/project
scope; it is not skipped, retried or relabeled stale.

## 2026-10-22 measured lane rebalance

PR182 run [39812335253](https://github.com/yogeshnaren/panestria/actions/runs/39812335253)
was cancelled at the unchanged 15-minute platform job limit. Its browser consent
recovery cases both passed; setup consumed over six minutes, and pytest reached
90% before cancellation. The missing platform XML is **not a pass**. The original
three available reports and full job log remain in the private CI archive.

The preceding successful run
[39805028940](https://github.com/yogeshnaren/panestria/actions/runs/39805028940)
recorded 582.296 seconds of platform test durations, against 225.298 for kernel.
Move the durable Build/plan/queue file families into kernel, which already runs
recovery and approval E2E. Physical browser, native and profile tests stay in
platform. The same original timings then project 395.249 seconds for kernel and
412.345 for platform; these exclude setup and are **not a measured speedup**.
Research and fast are unchanged. The complete [inventory](../../evidence/ci-lane-balance-2026-10-22/inventory.json)
accounts for all 211 discovered files exactly once, including live-only files
whose live cases remain excluded from default CI. No test, assertion, mark,
timeout or required check is removed or weakened. Full exact-head CI remains
required; this adjustment does not qualify a release gate.

## Hosted Ubuntu mirror stall

The next exact-head run
[39825157362](https://github.com/yogeshnaren/panestria/actions/runs/39825157362)
on PR182 head ca30b02 reached the unchanged job deadline after browser dependency
setup. Its original platform log reports **22.3 MB in 12min 3s (30.8 kB/s)** from
`http://azure.archive.ubuntu.com/ubuntu`; browser downloads then finished in
seconds. The four other lanes passed. Original available reports/logs are
preserved separately as TIMED_OUT_NOT_PROMOTED. A single failed-job retry was
started, without repeating passing lanes or changing source.

The platform runner now substitutes `https://archive.ubuntu.com/ubuntu` for that
specific HTTP mirror endpoint in its ephemeral `/etc/apt/apt-mirrors.txt`. Other
entries, APT signed repository checks, package selection, Playwright `--with-deps`,
all tests, six checks and the 15-minute job deadline remain intact. An image
without that endpoint keeps its existing entries; a missing mirror-list file
fails visibly. This changes no owner workstation/backup/driver configuration.
The actual hosted workflow must validate this change before any speed claim.
Ubuntu documents [APT repository configuration](https://ubuntu.com/server/docs/how-to/software/package-management/).
No third-party source code is copied; this is one official repository-origin
configuration change, based on the actual download log.

## Reproduce

```bash
uv run --frozen python tools/ci_tests.py fast
uv run --frozen python tools/ci_tests.py kernel
uv run --frozen python tools/ci_tests.py platform
uv run --frozen python tools/ci_tests.py research
```

Run lanes sequentially on one workstation because fixtures use fixed disposable
ports. `--list` prints the full partition; `--collect-only` checks a lane without
starting its fixtures. Required live tests must still run separately under their
existing authorization and environment requirements.

## Framed-input SIGKILL observation correction (2026-10-23)

PR189's original platform run39876295510 exposed a default-test assumption:
Docker retained ExitCode137/OOMKilled=false after bounded metadata settlement,
and production truthfully returned process_failed. The existing pressure case
now requires stopped exit137, daemon-consistent reason/flag, bounded output/time
and exact cleanup for both confirmed and unconfirmed OOM observations. No test
is added, deferred or removed. It cannot turn an unconfirmed cause into a proven
memory-limit result. The separate live AOS-008-TC03 memory assertion still
requires memory_limit unchanged; neither default CI nor injected metadata passes
that gate. [Original failure and affected checks](../../evidence/sandbox-oom-observation-2026-10-23/report.json)
retain their source hashes. Production behavior and settlement bounds are unchanged.
