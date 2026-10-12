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
uv run --frozen panestria version
uv run --frozen panestria health
uv run --frozen pytest tests/integration/test_aos_001.py
```

`version` exits 0. `health` exits 1 when the process is not ready and 2 when settings are rejected. In this slice the database check is `not_probed`; there is no live database probe. A timed-out readiness probe is killed, and shutdown is bounded to one second.

## Scope

S1 installs the `panestria` package, validates the `SYNTHETIC_DEV` profile, and serves typed `/healthz` and `/readyz` routes. Later slices add lint, CI, PostgreSQL, and domain workflows. The license file is the repository MIT license.
