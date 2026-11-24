# Contributing

Panestria has an accepted R0 synthetic kernel; R1 is in progress and the complete R3 MVP is not accepted. Consult the source-bound status and evidence in [the phase tracker](docs/phase-tracker.json). A merged change or default CI pass does not establish release acceptance, a fresh-host pass or an owner review. Use [the active build plan](docs/PANESTRIA_PHASED_IMPLEMENTATION_PLAN.md) for current scope and sequencing.

## Setup

Python 3.12 or newer and uv are required. Docker is required only for the disposable PostgreSQL tests. The command sequence and the Ubuntu support note are in [docs/SETUP.md](docs/SETUP.md).

```bash
make bootstrap
```

`make bootstrap` checks the lock and syncs the frozen dev group. It can use the local uv cache. Runtime code does not install packages.

Settings come from the process environment. The names are in `.env.example`. Panestria does not load that file. The database URL there points at the Compose port `127.0.0.1:55432`. The password is the documented placeholder.

## Checks

```bash
make lint
make typecheck
make test
```

`make test` runs `pytest -m "not live"`. That command deselects live checks, including `AOS-001-TC04`. A failed, missing or deselected live check is not a pass; collect the exact required host/provider evidence separately.

### Browser tests

The physical Mission Control journeys are marked `requires_browser`. They run `apps/mission-control/tests/*.mjs` under Node with `@playwright/test` and Playwright's Chromium. They need a Node that satisfies `engines.node` in `apps/mission-control/package.json` (currently `^20.19.0 || >=22.12.0`). Prepare the frontend with that Node first on `PATH`:

```bash
cd apps/mission-control
npm ci --ignore-scripts --no-audit --no-fund
npm run build
npx --no-install playwright install chromium
```

The tests use `PANESTRIA_TEST_NODE` when it is set, as an absolute path or a command looked up on `PATH`. Otherwise they use the first `node` on `PATH`. Set it when an older Node comes first, for example `PANESTRIA_TEST_NODE="$(nvm which 22)" make test`. `PLAYWRIGHT_BROWSERS_PATH` selects a task-owned browser directory.

If the Node version, `@playwright/test` or Chromium is missing, these tests skip locally with the reason; `pytest -rs` prints it. When `CI` is set they fail instead. CI installs Node and Chromium for the platform lane and does not set `PANESTRIA_TEST_NODE`. Its hermeticity lanes also run the kernel and platform lanes on a group-writable checkout under umask 0002 with Node 20.19.0; to reproduce one locally, clone under `umask 0002` and set `PANESTRIA_TEST_NODE` to a Node 20.19 binary.

`make db-up`, `make db-migrate`, and `make reset-synthetic-data` act only on the `panestria-s3` Compose project. Reset removes that named volume and accepts no filesystem path.

## Changes

Keep commits small. Do not commit `.env`, credentials, or provider keys. Do not rewrite published evidence to claim a result for a different source commit. The repository license is the MIT license in `LICENSE`.
