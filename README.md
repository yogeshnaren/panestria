# panestria

Local synthetic kernel for R0. The scaffold, domain tables, DBOS admission, and loopback goal flow are present. R0 is complete and owner-accepted; G0 passed on the recorded candidate. R1 implementation is authorized, and the complete MVP remains the R3 milestone. This tree is not a release.

The design guide is [docs/START_HERE.md](docs/START_HERE.md). Setup is [docs/SETUP.md](docs/SETUP.md). Local limits are in [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).

## Requirements

Python 3.12 or newer, and [uv](https://docs.astral.sh/uv/). The checked-out interpreter used for the hermetic lane was CPython 3.12.4. That observation is not a support-matrix certification.

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

The package, `SYNTHETIC_DEV` settings, and typed `/healthz` and `/readyz` routes are in place. Ruff, Mypy, Import Linter, and provider-free CI are the toolchain. Compose publishes disposable PostgreSQL on `127.0.0.1:55432`. Alembic head is `0004_check_candidate`. Goal submit, events, approvals, artifact reads, and cancellation are mounted on the loopback API. Their generated description is [docs/api/openapi.json](docs/api/openapi.json). The fresh-host live case passed in a separate Ubuntu VM; see [technical completion](docs/reviews/R0-TECHNICAL-COMPLETION.md). R1 has not started. The license file is the repository MIT license.
