# panestria

S1 scaffold for a local, synthetic-first agent operating system. AOS-001, R0, and the R3 MVP are incomplete. This tree is not a release.

The design guide is [docs/START_HERE.md](docs/START_HERE.md).

## Requirements

Python 3.12 or newer, and [uv](https://docs.astral.sh/uv/). The checked-out interpreter used for the hermetic lane was CPython 3.12.4. That observation is not a support-matrix certification.

## Setup

```bash
uv sync --frozen --group dev
```

Settings come from the process environment, using the names in [.env.example](.env.example). Panestria does not load that file. The password in the example is an accepted synthetic value. Copying it into the environment is enough for `panestria health` to parse settings. Health does not open PostgreSQL, and it must not print the password.

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

`version` exits 0. `health` exits 1 when the process is not ready and 2 when settings are rejected. In this slice the database check is `not_probed`; there is no live database probe. A timed-out readiness probe is killed, and shutdown is bounded to one second.

Provider credentials are not required for these commands. CI uses the same frozen commands and does not inject provider keys.

## Scope

The package, `SYNTHETIC_DEV` settings, and typed `/healthz` and `/readyz` routes are in place. Ruff, Mypy, Import Linter, and provider-free CI are the S2 toolchain. S3 adds a loopback PostgreSQL Compose service and an empty Alembic schema. `/readyz` still does not open the database. Domain tables, the fresh-host live case, and domain workflows remain later work. The license file is the repository MIT license.
