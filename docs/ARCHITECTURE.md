# Architecture delta

This file records the implementation on `91cadf8052ef4249d25e2df017b582f6ba55af09`. R0 is not accepted. The design in `docs/design/01-ARCHITECTURE-AND-CONTRACTS.md` still describes later releases. Those releases are not implemented here.

## What runs

One Python 3.12 package, `src/panestria`, with a frozen `uv.lock`. PostgreSQL 16 is the only database, published on `127.0.0.1:55432` by Compose project `panestria-s3`. Alembic head is `0004_check_candidate`. The schema diagram is `docs/design/schema-erd.md`.

`python -m panestria.api.serve` listens on loopback, checks the database when `PANESTRIA_DATABASE_URL` is set, and runs the synthetic journey on a daemon thread. `make r0-demo` starts that server and drives submit, approval, evidence, and completion through the CLI. The API is FastAPI mounted by a stdlib asyncio HTTP server. The CLI is Typer and urllib, and it accepts a success body only when that body matches the response model published in `docs/api/openapi.json`. Every API denial returns `code`, `message`, `correlation_id`, and `retryable`. The correlation id is generated for that response and is not copied from the request. When the API process is down, the CLI exits nonzero with `api_unavailable` and `retryable` true, and it does not print the address or a success body.

## Packages present

| Package | Role in this tree |
|---|---|
| `contracts` | Goal and approval models. `effect_digest` is the only approval fingerprint. `docs/contracts/` is the JSON Schema rendered from those models, plus the database snapshot. |
| `kernel` | Goal, task, approval, artifact, and cancellation services. Repositories append events under the global sequence lock. |
| `execution` | Admission enqueues `run_task_workflow` on the DBOS queue `panestria-synthetic`. Crash gates stop a process before commit, worker start, verification, effect dispatch, or effect confirmation. |
| `verification` | Per-node command, path, policy, artifact, and human-review checks. The diff is between the pinned base and the candidate tree. An executable mode on an otherwise allowed path is denied. The stored check report keeps the bounded command output and the changed paths. A merge is not prepared, and a new Git update does not run, unless each required report file still matches its stored hash and retained output. |
| `sandbox` | Disposable Git worktrees and artifact publication checked against the current owner, project, and epoch. Each worktree record stores owner, TTL, and disk use under `protected/`. Cleanup removes an expired or unrecorded attempt and unlinks a directory symlink without deleting its target. When a store is configured, regular files are copied and rechecked there before the worktree is removed. Git runs only for the synthetic command list, and a push or a hook path other than `/dev/null` does not start. |
| `brokers` | The mock worker only. Modes include `success`, `bad-test`, `bad-path`, `timeout`, `crash`, and `artifact-corrupt`. A collected run records `started`, `progress`, `artifact.created`, `verifying`, and `finished`, each bound to the attempt and epoch. Those events do not accept the candidate. An unknown mode starts no process. |
| `api` / `cli` | Loopback routes and commands for goals, events, artifacts, approvals, and cancellation. |
| `ops` | Refuses to delete any volume other than `panestria_s3_pgdata`. |

Import Linter checks these boundaries. The kernel does not import the API, CLI, or execution packages.

## Durable path

An accepted goal becomes a task and a contract-consent approval. After that approval, admission stores a workflow link and enqueues the attempt. The workflow leases the attempt, the mock worker writes the candidate, and the verifiers record check runs and artifact hashes. A merge approval is consumed once. Before a new Git update, the journey rechecks expiry, epoch, candidate, and evidence. If the protected ref already names the approved commit, recovery records success. If the ref is unchanged, recovery uses a compare-and-swap. Any other ref is a conflict.

Event `seq` is a global identity allocated under `pg_advisory_xact_lock(106971, 1)`. ADR 0002 records that rule. A process started with `PANESTRIA_MODE=recover` prints one line with `recovery_instance`, the goal id, the task id, the pinned workflow id, `recovery_attempts`, `latency_ms`, and the status. `unfinished_audits` lists `PENDING` and `ENQUEUED` workflows with those ids and does not include the database URL. A workflow that is still pending prints `PENDING` and the command exits 2. DBOS is pinned at 3.2.0. Git commands used by the worktree, the diff, and the journey are limited to 30 seconds. A serializable workflow transaction raises `serialization_retry_limit` after five conflicting attempts. The task and effect workflows record that task FAILED and re-raise, so the workflow stays ERROR. Any other terminal workflow error is recorded the same way. A lost version race, an illegal transition, and a contract mismatch are re-raised without that receipt. The task, effect, and failing workflows are registered with `max_recovery_attempts` 2. When recovery reports `MAX_RECOVERY_ATTEMPTS_EXCEEDED`, the linked task is recorded FAILED with cause `recovery-attempt-limit`. Goal, event, and task lookups are the repository statements. With sequential scans disabled they use `goal_pkey` or `goal_id_project_id_owner_id_key`, `ix_event_goal_seq`, and `ix_task_goal`. The `panestria` relation footprint is measured from `pg_total_relation_size` and must stay under 64 MiB and under the current database size.
