# panestria

Local agent orchestration kernel with a supported offline Ask application. R0 is complete and owner-accepted; G0 passed on the recorded candidate. R1 is in progress, and the complete MVP remains the R3 milestone. This tree is not a release.

The main build document is [the revision-3 phased plan](docs/PANESTRIA_PHASED_IMPLEMENTATION_PLAN.md), with [active specification/contracts](docs/specification/architecture/05-PERSONAL-PLATFORM-REVISION-3.md) and [build navigation](docs/START_HERE.md). Setup is [docs/SETUP.md](docs/SETUP.md). Local limits are in [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).

For local Ask, follow [explicit project setup](docs/testing/LOCAL_ASK_SETUP.md),
[server launch](docs/testing/LOCAL_ASK_SERVER.md) and
[keyboard terminal application](docs/testing/LOCAL_ASK_TUI.md). After setup,
run `panestria tui --config /absolute/private/local.json` in a second terminal
while the local server runs. The TUI supports Ask, readiness, receipts and
cancellation. The explicit `local init --offline-ask` command creates private
settings and stable IDs using an existing migrated database and model cache.

For an existing PUBLIC Build goal, the separate
[Build review terminal](docs/testing/BUILD_REVIEW_TUI.md) displays checks/diff
and confirms the frozen exact merge or cancellation:
`panestria build tui --config /absolute/private/build.json GOAL_UUID`.
It uses Build's separate owner configuration and grants. Research screens,
unified Mission Control and service provisioning remain pending.
[Browser pairing/testing](docs/testing/LOCAL_ASK_BROWSER.md) is also available. The local browser
uses the offline model and scoped memory; profiles and Build/tools are disabled
there. The R0 commands and native proposal demo below remain separate.

## Requirements

- Linux x86-64. Run Panestria as a normal (non-root) user; several runtimes refuse euid 0 by design.
- Python 3.12 or newer, and [uv](https://docs.astral.sh/uv/) **0.12.3 exactly**. `pyproject.toml` pins `[tool.uv] required-version`; other uv versions refuse `uv run` and the Make targets.
- Docker Engine with the Compose v2 plugin. It provides PostgreSQL and the worker/reader sandboxes; your user must be able to run `docker` without root.
- Optional, per feature:
  - Offline Ask: host Ollama (`/usr/local/bin/ollama`) and a dedicated model cache with `qwen2.5:1.5b-instruct`.
  - Build: Claude Code 2.1.273.
  - Mission Control from source: Node `^20.19.0 || >=22.12.0`.

The checked-out interpreter used for the hermetic lane was CPython 3.12.4. That observation is not a support-matrix certification.

## Setup

```bash
uv sync --frozen --group dev
```

Settings come from the process environment, using the names in [.env.example](.env.example). Panestria does not load that file. The password in the example is an accepted synthetic value. Copying it into the environment is enough for `panestria health` to parse settings. When `PANESTRIA_DATABASE_URL` is set, `health` opens PostgreSQL inside the readiness budget and does not print the URL or password. With no URL, the database check stays `not_probed`. The process stays not ready because no executor is configured.

```bash
set -a
source .env.example
set +a
```

`source` is a local shell convenience. The application still reads only the exported environment.

## Commands

```bash
uv lock --check
uv sync --frozen --group dev
uv run --frozen ruff check .
uv run --frozen mypy src/panestria
uv run --frozen lint-imports --config .importlinter
uv run --frozen pytest -m "not live"
uv run --frozen python tools/secret_scan.py
docker compose -f compose.yaml -p panestria-s3 up -d --wait
uv run --frozen panestria version
uv run --frozen panestria health
```

`version` exits 0. `health` exits 1 when the process is not ready and 2 when settings are rejected. A timed-out readiness probe is killed, and shutdown is bounded to one second.

The same commands are available as `make bootstrap`, `make lint`, `make typecheck`, and `make test`. `make test` excludes the live fresh-host case. `make db-up`, `make db-down`, and `make db-migrate` use only the `panestria-s3` Compose project. `make db-down` leaves the named volume in place. `make reset-synthetic-data` removes that volume and accepts no filesystem path. `make dev-api` is `python -m panestria.api.serve` on `127.0.0.1`. A non-loopback bind is rejected. `make r0-demo` reuses an authenticated running API or starts a temporary one, then drives submit, approval, evidence, and completion with the `panestria` CLI. `make r0-review` also opens a read-only snapshot at `http://127.0.0.1:8870/` and stays running until Ctrl+C. It needs the migrated database from the runbook. It is not the fresh-host case. `make` with no target prints the command list and does not start the demo.

Provider credentials are not required for these commands. CI uses the same frozen commands and does not inject provider keys.

## Scope

The package, `SYNTHETIC_DEV` settings, and typed `/healthz` and `/readyz` routes are in place. Ruff, Mypy, Import Linter, and provider-free CI are the toolchain. Compose publishes disposable PostgreSQL on `127.0.0.1:55432`. Inspect the current Alembic head before migration; applied R0 revisions are preserved and later R1 revisions are additive. Goal submit, events, approvals, artifact reads, and cancellation are mounted on the loopback API. Their generated description is [docs/api/openapi.json](docs/api/openapi.json). The fresh-host live case passed in a separate Ubuntu VM; see [technical completion](docs/reviews/R0-TECHNICAL-COMPLETION.md). R1 components and the fixed public native preview are integrated on main; G1/live acceptance remains pending. Revision-3 profile/quota/phone extensions and R2/R3 implementation remain unaccepted future work. The [tracker](docs/phase-tracker.json) separates code and release state. The license file is the repository MIT license.

Performance evidence can be saved and inspected without starting the backend:
`uv run --frozen panestria metrics capture` and `uv run --frozen panestria metrics show`.
See [saved performance measurements](docs/testing/PERFORMANCE_METRICS.md) for
source-bound latency/quality history, missing measurements and private storage.
