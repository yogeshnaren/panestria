# Architecture delta

This file records the implementation on `b0f47cf14383b328f70536454c9f851587bea677`. R0 is not accepted. The design in `docs/design/01-ARCHITECTURE-AND-CONTRACTS.md` still describes later releases. Those releases are not implemented here.

## What runs

One Python 3.12 package, `src/panestria`, with a frozen `uv.lock`. PostgreSQL 16 is the only database, published on `127.0.0.1:55432` by Compose project `panestria-s3`. Alembic head is `0004_check_candidate`. The schema diagram is `docs/design/schema-erd.md`.

`python -m panestria.api.serve` listens on loopback, checks the database when `PANESTRIA_DATABASE_URL` is set, and runs the synthetic journey on a daemon thread. `make r0-demo` starts that server and drives submit, approval, evidence, and completion through the CLI. The API is FastAPI mounted by a stdlib asyncio HTTP server. The CLI is Typer and urllib, and it accepts a success body only when that body matches the response model published in `docs/api/openapi.json`.

## Packages present

| Package | Role in this tree |
|---|---|
| `contracts` | Goal and approval models. `effect_digest` is the only approval fingerprint. `docs/contracts/` is the JSON Schema rendered from those models, plus the database snapshot. |
| `kernel` | Goal, task, approval, artifact, and cancellation services. Repositories append events under the global sequence lock. |
| `execution` | Admission enqueues `run_task_workflow` on the DBOS queue `panestria-synthetic`. Crash gates stop a process before commit, worker start, verification, effect dispatch, or effect confirmation. |
| `verification` | Per-node command, path, policy, artifact, and human-review checks. The diff is between the pinned base and the candidate tree. |
| `sandbox` | Disposable Git worktrees and artifact publication checked against the current owner, project, and epoch. |
| `brokers` | The mock worker only. Modes include `success`, `bad-test`, `bad-path`, `timeout`, `crash`, and `artifact-corrupt`. |
| `api` / `cli` | Loopback routes and commands for goals, events, artifacts, approvals, and cancellation. |
| `ops` | Refuses to delete any volume other than `panestria_s3_pgdata`. |

Import Linter checks these boundaries. The kernel does not import the API, CLI, or execution packages.

## Durable path

An accepted goal becomes a task and a contract-consent approval. After that approval, admission stores a workflow link and enqueues the attempt. The workflow leases the attempt, the mock worker writes the candidate, and the verifiers record check runs and artifact hashes. A merge approval is consumed once. Before a new Git update, the journey rechecks expiry, epoch, candidate, and evidence. If the protected ref already names the approved commit, recovery records success. If the ref is unchanged, recovery uses a compare-and-swap. Any other ref is a conflict.

Event `seq` is a global identity allocated under `pg_advisory_xact_lock(106971, 1)`. ADR 0002 records that rule. A process started with `PANESTRIA_MODE=recover` prints one `recovery_instance` for that process and the pinned workflow id. DBOS is pinned at 3.2.0. A serializable workflow transaction raises `serialization_retry_limit` after five conflicting attempts. The task and effect workflows record that task FAILED and re-raise, so the workflow stays ERROR.
