# Setup

R0 was accepted on 2026-10-13 (G0 PASS). These steps start the synthetic R0 kernel on a local Ubuntu machine. They do not record the fresh-host case. Setup for the R1-R3 surfaces (Ask, Build, research, phone, background) is in the runbooks under [docs/testing](testing/); a consolidated operator guide is planned in the [remediation plan](project/R3-REMEDIATION-PLAN.md).

## Support

The documented host is Ubuntu 22.04 with Python 3.12 and uv **0.12.3 exactly** (`[tool.uv] required-version` in `pyproject.toml`; other uv versions refuse to run `uv run`/`make`). Building Mission Control from source also needs Node `^20.19.0 || >=22.12.0`. Docker is used only for the disposable PostgreSQL service. macOS is not part of this setup. AOS-001-TC04 passed in a fresh Ubuntu 22.04 VM; measured startup and RSS plus frozen/offline bootstrap evidence are linked in [technical completion](reviews/R0-TECHNICAL-COMPLETION.md).

## Install

From a clean checkout:

```bash
make bootstrap
```

That checks `uv.lock` and syncs the frozen dev group. The runtime does not install packages on its own.

## Database

```bash
make db-up
make db-migrate
```

Compose project `panestria-s3` publishes PostgreSQL on `127.0.0.1:55432`. The volume name is `panestria_s3_pgdata`. `make db-down` stops the container and leaves the volume. If the local database is broken, `make reset-synthetic-data` removes that volume and nothing else. It accepts no filesystem path.

## Run

For the automatic CLI walkthrough:

```bash
make r0-demo
```

For a browser review of a completed walkthrough:

```bash
make r0-review
```

Open **http://127.0.0.1:8870/** when the review link is printed. The page shows the observed goal, check verdicts, evidence hash, synthetic CLI approval receipts, and event history. It is a read-only snapshot; it does not perform new work or record owner acceptance. `make r0-review` stays in the foreground until Ctrl+C. An occupied review port is reported clearly; `python -m panestria.demo --review --review-port 8871` selects another port with the same environment configuration.

Both walkthrough commands need the migrated database. They authenticate and reuse an API already running on port 8765, or start a temporary API when that port is free. They stop only the API they started. An unrelated listener or a different bearer token is refused before a goal is submitted. Each run has a fresh goal and idempotency keys. These commands are not `AOS-001-TC04`.

`make dev-api` is optional: use it to keep the API running for direct CLI calls. It remains in the foreground until Ctrl+C; use a second terminal for the walkthrough. It binds only to loopback. The Make targets provide the synthetic database URL and token defaults. For direct Python invocations, export the names in `.env.example`; Panestria reads the process environment and does not load `.env` automatically.

## Checks

```bash
make lint
make typecheck
make test
```

`make test` excludes the live fresh-host test. Provider credentials are not required.

Regression tests use `tests/fixtures/compose.r0-tests.yaml`, a process-specific
`panestria-r0-tests-<pid>` Compose project, PostgreSQL on `127.0.0.1:55440`, and
a project-scoped disposable volume. The suite cleans up that test project even
after a failed test. These fixtures are separate from the review database on
port 55432. Run one regression test process at a time; concurrent runs share
the test port and fail if it is occupied.

A killed workflow process is resumed with `PANESTRIA_MODE=recover` and `PANESTRIA_WORKFLOW_ID` set to the pinned id. It prints one JSON line containing `recovery_instance`, `goal_id`, `task_id`, `workflow_id`, `recovery_attempts`, `latency_ms`, and `status`. Success exits 0. A still-pending or failed workflow prints that line and exits 2. When the status is `MAX_RECOVERY_ATTEMPTS_EXCEEDED`, the linked task is recorded FAILED before that exit. DBOS is pinned at 3.2.0. That command is not a fresh-host result.
