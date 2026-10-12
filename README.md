# panestria

Local synthetic kernel for R0. The scaffold, domain tables, DBOS admission, and loopback goal flow are present. R0 is not accepted, G0 is incomplete, and the R3 MVP has not started. This tree is not a release.

The design guide is [docs/START_HERE.md](docs/START_HERE.md).

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

The loopback server is `python -m panestria.api.serve`. It binds `127.0.0.1`, probes PostgreSQL from `/readyz`, and continues an accepted goal on the DBOS queue. `make r0-demo` starts that server and drives submit, approval, evidence, and completion with the `panestria` CLI. It needs the migrated database from the runbook and `PANESTRIA_TOKEN`. It is not the fresh-host case.

Provider credentials are not required for these commands. CI uses the same frozen commands and does not inject provider keys.

## Scope

The package, `SYNTHETIC_DEV` settings, and typed `/healthz` and `/readyz` routes are in place. Ruff, Mypy, Import Linter, and provider-free CI are the toolchain. Compose publishes disposable PostgreSQL on `127.0.0.1:55432`. Alembic head is `0004_check_candidate`. Goal submit, events, approvals, artifact reads, and cancellation are mounted on the loopback API. The fresh-host live case has not been run. R1 has not started. The license file is the repository MIT license.
