# Contributing

Panestria is a local synthetic kernel. R0 is not accepted, G0 is incomplete, and R1 has not started. Do not describe a change as a release, a fresh-host pass, or an owner review.

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

`make test` runs `pytest -m "not live"`. That command deselects `AOS-001-TC04`. A failure of that live test on this machine is not a pass, and a missing fresh Ubuntu host is not a result you should invent.

`make db-up`, `make db-migrate`, and `make reset-synthetic-data` act only on the `panestria-s3` Compose project. Reset removes that named volume and accepts no filesystem path.

## Changes

Keep commits small. Do not commit `.env`, credentials, or provider keys. Do not rewrite published evidence to claim a result for a different source commit. The repository license is the MIT license in `LICENSE`.
