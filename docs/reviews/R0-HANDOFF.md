# R0 review handoff

The 2026-10-12 review did not accept R0. This file keeps that review record and the later correction. It is not an owner acceptance, a G0 pass, or permission to start R1.

**Reviewed source:** `af3d431e775c2f3f23722d272dd00f2863689d5b`. Its report remains `evidence/AOS-005-S3.xml`.  
**Corrected source:** `31f1568b57944dbc536d3f5a2f7e7bb978b8429c` on `r0-kernel`.  
**Correction report:** `evidence/R0-corrections.xml`, SHA-256 `9667c55e1bd77480ddf34bdebf8a9dd1d944be78a6e03c278dc10bf6e88c78c1`. 135 tests, 0 failures, 0 errors, 0 skips. The live fresh-host test was deselected.  
**Gate:** `evidence/G0/evaluation.json` records G0 as `INCOMPLETE`. Nineteen of twenty required cases were collected. `AOS-001-TC04` is `NOT_RUN`. A case-group PASS does not prove every source clause and is not owner acceptance.

The original handoff commit recorded `af3d431`. This report's source parent is `31f1568b57944dbc536d3f5a2f7e7bb978b8429c`. Older receipts are not rewritten.

## Ordered commits

Commits are newest first, from the approved contract through the journey. Evidence commits name the preceding source commit inside their case results.

| Commit | Reason |
|---|---|
| `31f1568` | Keep the off-scope path and test exit code in one failure report. |
| `91cadf8` | Reject Git commands outside the synthetic sandbox list. |
| `8d6554b` | Copy worktree files into the store before cleanup deletes them. |
| `a692020` | Check listed acceptance denials without scanning the correlation id. |
| `b473cab` | Return a retryable CLI error when the API process is down. |
| `b4c6606` | Reject an executable mode on an otherwise allowed path. |
| `c02fc1c` | Record scripted worker events that do not accept the candidate. |
| `9a8ab69` | Check denial codes for echoed contract values, not the correlation id. |
| `ed41fd9` | Give every API denial a generated correlation id. |
| `f17a3e2` | Give the unfinished-workflow fixture ids that the shared database does not already use. |
| `8f51457` | Name the goal and task on recovery logs and list unfinished workflows. |
| `5d4606b` | Keep worktree records inside the reserved sandbox directory. |
| `04511d5` | Record worktree owner, TTL, and disk use, and refuse symlink cleanup escapes. |
| `26e0d6e` | Prove goal and task lookups use their indexes and record the schema footprint. |
| `b20c6b4` | Stop workflow recovery after two attempts and mark the task failed. |
| `b96d1d3` | Reject a merge when the stored check report file has been rewritten. |
| `a0871a3` | Refuse an effect when a stored check report does not match its file. |
| `e3009a7` | Keep bounded test output and changed paths in the check report. |
| `a27bf76` | Record recovery attempts and latency, and bound Git command time. |
| `fc9c29e` | Record FAILED when a terminal workflow error is not a lost version race. |
| `b0f47cf` | Export the executable contract schemas and the checked database snapshot. |
| `a9bbc00` | Record FAILED when a serialization storm stops a workflow transaction. |
| `0c7ff34` | Stop a serializable workflow transaction after five conflicting attempts. |
| `0eb6cef` | Log one recovery identity for each restarted workflow process. |
| `47352ba` | Reject CLI success bodies that omit the published response fields. |
| `53785d5` | Give each synthetic demo run its own idempotency key. |
| `9a1b773` | Start the synthetic demo with the loopback database defaults. |
| `08d7610` | Reject a worker hash recorded before the artifact bytes change. |
| `7098ba7` | Stop the health probe child after generating the OpenAPI document. |
| `175e7d9` | Commit the generated OpenAPI document for the mounted routes. |
| `453b999` | Reject a worker that claims tests passed when the required check fails. |
| `d53c892` | Add contributor and security notes with placeholder-only settings. |
| `a8c9fd3` | Fail the migration check when the database schema drifts. |
| `fba684a` | Add the documented bootstrap, database, and loopback make targets. |
| `ae4e142` | Prove the loopback smoke measurement on the disposable database. |
| `36ccf6b` | Attribute smoke sockets to the server process and still fail closed here. |
| `d6fb08f` | Measure fresh-host listeners in the test and still fail closed here. |
| `fc359b0` | Map the correction regressions onto the cases they exercise. |
| `6439c42` | Loopback server, artifact read, approval list, cancellation, and `make r0-demo`. |
| `de42383` | Reject stored dependency cycles, raced goal submits, and bad envelopes. |
| `001d56f` | Reconcile an applied Git ref and recheck approval before dispatch. |
| `60b1d15` | Run the admitted task on the DBOS queue consumer. |
| `db27430` | Reject artifact publication that does not match the current attempt. |
| `3de385e` | Evaluate each acceptance node and authorize only its latest run. |
| `6899104` | Historical evidence and handoff for `af3d431`. The review did not accept it. |
| `af3d431` | Synthetic consent, one mock candidate, independent checks, and one CAS completion. |
| `68592b6` | Evidence for the locked approval decisions. |
| `eb5d6c3` | Migration regression follows the Alembic head and denies digest rebinding. |
| `8f1feee` | Locked approval preview, decision, and continuation. |
| `744bbce` | Evidence for the loopback routes. |
| `44d30f0` | Keep the health factory signature and mount goal routes separately. |
| `fc4827c` | Loopback goal submit, status, events, and CLI replay. |
| `c616747` | Evidence for the watchdog. |
| `c0ae53c` | Wall-clock timeout, cancellation, and orphan artifact cleanup. |
| `50624b4` | Evidence for independent checks. |
| `9f4b764` | Reviewed command bundle, diff inspection, and artifact ingress. |
| `a39039f` | Evidence for the scripted worker. |
| `abf45f8` | Seeded git worktree and mock worker. |
| `effd7e9` | Evidence for crash restore. |
| `cd2b6b4` | Lost external step, terminal failure, and schema restore. |
| `971ded5` | Evidence for replay. |
| `9a652c1` | Replay-deterministic task transition and step checkpoint. |
| `915f85b` | Evidence for atomic admission. |
| `655a0c5` | DBOS enqueue inside the caller transaction. |
| `684ead8` | Evidence for scoped mutations. |
| `5793500` | Scoped transitions, DAG checks, and cursor concurrency. |
| `3bcbcd7` | Evidence for the kernel schema. |
| `dee9dc2` | Kernel tables, immutability trigger, and constraint tests. |
| `b518abb` | Evidence for strict contracts. |
| `834ae35` | Canonical goal-contract hash and rejected legacy verifiers. |
| `cd866cd` | Evidence for the PostgreSQL scaffold. |
| `61d9e47` | Loopback Compose project and empty Alembic schema. |
| `398dd04` | Evidence for the toolchain. |
| `99afb1a` | Keep the synthetic key out of the scanner test source. |
| `d2cca26` | Ruff, Mypy, Import Linter, CI pins, and boundary failures. |
| `fba17d4` | Approved phase contract, stored separately from its approval record. |

`main` remains at the AOS-001-S1 evidence commit `48e378ee2f03a98c2e637b1d4f3b6066a5d13eaf`. This branch has not been pushed.

## Evidence matrix

| Case | Integrated verdict on `af3d431` | Historical receipt |
|---|---|---|
| AOS-001-TC01 | PASS, hermetic | `evidence/AOS-001-S1/case-result.json` names `af6794e` |
| AOS-001-TC02 | PASS, hermetic | `evidence/AOS-001-S2/case-result.json` names `99afb1a` |
| AOS-001-TC03 | PASS, OS boundary | `evidence/AOS-001-S3/case-result.json` names `61d9e47` |
| AOS-001-TC04 | NOT_RUN | No fresh Ubuntu host. Excluded by `-m "not live"`. |
| AOS-002-TC01 | PASS, hermetic | `evidence/AOS-002-S1/case-result.json` names `834ae35` |
| AOS-002-TC02 | PASS, OS boundary | `evidence/AOS-002-S2/case-result.json` names `dee9dc2` |
| AOS-002-TC03 | PASS, OS boundary | `evidence/AOS-002-S3/case-result-TC03.json` names `5793500` |
| AOS-002-TC04 | PASS, OS boundary | `evidence/AOS-002-S3/case-result-TC04.json` names `5793500` |
| AOS-003-TC01 | PASS, OS boundary | `evidence/AOS-003-S1/case-result.json` names `655a0c5` |
| AOS-003-TC02 | PASS, OS boundary | `evidence/AOS-003-S2/case-result.json` names `9a652c1` |
| AOS-003-TC03 | PASS, OS boundary | `evidence/AOS-003-S3/case-result-TC03.json` names `cd2b6b4` |
| AOS-003-TC04 | PASS, OS boundary | `evidence/AOS-003-S3/case-result-TC04.json` names `cd2b6b4` |
| AOS-004-TC01 | PASS, OS boundary | `evidence/AOS-004-S1/case-result.json` names `abf45f8` |
| AOS-004-TC02 | PASS, OS boundary | `evidence/AOS-004-S2/case-result.json` names `9f4b764` |
| AOS-004-TC03 | PASS, OS boundary | `evidence/AOS-004-S3/case-result-TC03.json` names `c0ae53c` |
| AOS-004-TC04 | PASS, OS boundary | `evidence/AOS-004-S3/case-result-TC04.json` names `c0ae53c` |
| AOS-005-TC01 | PASS, OS boundary | `evidence/AOS-005-S3/case-result-TC01.json` |
| AOS-005-TC02 | PASS, OS boundary | `evidence/AOS-005-S3/case-result-TC02.json`; earlier receipt names `eb5d6c3` |
| AOS-005-TC03 | PASS, OS boundary | `evidence/AOS-005-S3/case-result-TC03.json` |
| AOS-005-TC04 | PASS, OS boundary | `evidence/AOS-005-S3/case-result-TC04.json` |

The integrated command was `uv run --frozen pytest -m "not live" --junitxml=evidence/AOS-005-S3.xml`. Exit 0. Suite totals: 93 tests, 0 failures, 0 errors, 0 skips. Static checks on the same source also exited 0: `uv lock --check --offline`, `uv run --frozen ruff check src tests`, `uv run --frozen mypy`, and `uv run --frozen lint-imports`.

Catalog status for an observed case is `OS_BOUNDARY_OBSERVED_NOT_RELEASE` or `HERMETIC_OBSERVED_NOT_RELEASE`. That is not a release pass. AOS-001 through AOS-005 stay `IN_PROGRESS`.

## Known issues

- AOS-001-TC04 is `tests/integration/test_aos_001.py::test_fresh_host_loopback` in `ae4e142`, marked `live`. It fails with `fresh_host_not_attested` on this machine before starting a server. The same measurement recorded a loopback socket, startup, and RSS against the disposable database here. That is not a fresh-host pass. G0 stays incomplete until a fresh Ubuntu host records a pass and an owner accepts the candidate.
- `adr/0002-event-seq-and-effect-digest.md` records the global sequence lock and the effect-digest binding. It is not a new suite run and it does not accept R0.
- `evidence/R0-dbos-crash-transcript.txt` records the admission restart test and the Git reconciliation test, 2 passed in 36.51s, on source `53785d5`. `docs/ARCHITECTURE.md` describes the later implementation. `docs/SETUP.md` records the local commands. The fresh-host startup time and idle RSS are still unrecorded.
- The DBOS 3.2.0 transaction loop still has no attempt-count field, and the wait between attempts stays at 2 seconds. The workflow callback raises `serialization_retry_limit` after five conflicting attempts. `run_task_workflow` and `run_effect_workflow` then record the task FAILED with cause `serialization-retry-limit` and re-raise, so the workflow stays ERROR. A unit test injects that denial and does not start PostgreSQL. That is not a fresh-host result.
- The review counterexamples are covered by new regressions on `fc359b0`. Their case-group PASS marks are not a statement that every source clause was asserted. `test_loopback_submit_scope_and_replay` still has no case id.
- `make r0-demo` starts `python -m panestria.api.serve` and the real CLI. On 2026-10-12 it completed one synthetic goal on the disposable database at source `fc359b0`. The same day, `make db-up` and `make db-migrate` reached Alembic head `0004_check_candidate`, `make db-down` left `panestria_s3_pgdata`, and `make reset-synthetic-data` removed that volume. Those observations are not AOS-001-TC04.
- `GET /v1/artifacts/{id}`, `panestria artifact show`, `panestria approvals`, and `panestria goal cancel` are implemented. A corrupted artifact hash and a foreign owner are denied. A prepared effect stays `CANCELLING` and is not merged.
- The CLI talks to a separate loopback TCP process in `tests/e2e/test_r0_loopback.py`. Older tests still forward urllib through FastAPI TestClient. uvicorn is not installed; the server is the packaged asyncio listener.
- `/readyz` opens PostgreSQL when `PANESTRIA_DATABASE_URL` is set. The database check is `ready` or `database_unavailable`. The process stays not ready because the executor is not configured. With no URL, the check remains `not_probed`.
- Hardware was not probed. Its verdict is `UNKNOWN`.
- Contract approval in `contracts/phase/r0-phase.approval.json` authorizes this development phase. It is not this review and it does not authorize a product effect.
- Two-worker proof, MVP-X01 through X06, and the six fault drills belong to later phases. R4 through R7 and SOTA are out of scope.

## Setup, start, and stop

From `/home/yogesh/Personal/panestria` on `r0-kernel`:

```bash
uv sync --frozen --group dev
docker compose -f compose.yaml -p panestria-s3 up -d --wait
export PANESTRIA_DATABASE_URL='postgresql://panestria_synthetic:placeholder-not-a-secret@127.0.0.1:55432/panestria_synthetic'
uv run --frozen alembic -c migrations/alembic.ini upgrade head
```

The image is pinned in `compose.yaml` and is published only on `127.0.0.1:55432`. This machine used Docker 29.1.3 and Compose v5.6.0. The password is the documented placeholder.

Stop and remove the disposable volume:

```bash
docker compose -f compose.yaml -p panestria-s3 down -v
```

`down -v` removes only `panestria_s3_pgdata`.

## Rollback and backup

Leave history intact. To inspect an earlier source, check out that commit without resetting the branch. Returning to `main` leaves this branch available. The phase contract hash stays `fbafb4171c4494228b23de00924b0ac882ab8404e4ff11a1ef0bd43dd83b608f`.

The disposable database is rebuilt by `down -v` followed by `up -d --wait` and `upgrade head`. AOS-003-S3 already recorded `pg_dump` and `pg_restore` of the `panestria`, `dbos`, and `panestria_checkpoint` schemas on its own source commit. That drill is not a production backup, and this handoff does not run it again.

## Walkthrough

Expected integrated result, from a clean tree at the tested source:

```bash
uv run --frozen pytest -m "not live" --junitxml=/tmp/panestria-r0.xml -q
```

On `31f1568b57944dbc536d3f5a2f7e7bb978b8429c` the same command collected 135 passed tests, 0 failures, and 0 skips, and deselected the live fresh-host case. `make r0-demo` then completed two goals on the disposable database; the audit is `evidence/R0-demo-transcript.json`. `docs/design/schema-erd.md` was generated from that database. The historical `af3d431` report remains 93 passed and is not a result for the corrected tree.

Positive journey:

```bash
uv run --frozen pytest tests/e2e/test_aos_005.py::test_r0_positive_journey -q
```

Expect one passed test. The CLI submits `docs/fixtures/synthetic-goal-contract.json`, consent does not start a worker, the approved consent starts one mock worker, independent diff and command checks record one PASS artifact, the merge approval performs one `git update-ref` compare-and-swap, and the goal and task become `COMPLETED` with effect state `SUCCEEDED` and attempt count 1. A second resume does not add an attempt.

Deliberate failures in `tests/e2e/test_aos_005.py::test_wait_restart_continuation`:

- Resume before consent leaves the attempt count at 0 and the task at `WAITING_APPROVAL` with continuation `DISPATCH`.
- Resume again at the merge wait leaves the attempt count at 1 and does not complete the goal.
- A denied consent leaves the goal incomplete and the attempt count at 0.
- Moving `refs/heads/main` in `sandbox/protected/dest.git` before finalize makes the compare-and-swap fail. The effect becomes `FAILED`, the goal stays incomplete, and the attempt count stays 1.

Deliberate conflicts in `tests/e2e/test_aos_005.py::test_decision_race_idempotency`: concurrent approve and deny leave one terminal decision and one `approval.decided` event. Concurrent continuation leaves one prepared effect. The same idempotency key with the opposite decision raises `idempotency_conflict`.

Deliberate denials in `tests/e2e/test_aos_005.py::test_approval_digest_actor_expiry`: a wrong digest, wrong actor, expired request, foreign owner, or `UNKNOWN` check prepares no effect. A non-loopback CLI base URL exits 2.

## Stopping condition

Review this package before any R1 work. A G0 pass requires the missing fresh-host case and your recorded review of an exact candidate. Neither is present.
