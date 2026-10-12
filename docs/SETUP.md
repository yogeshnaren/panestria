# Setup

R0 is not accepted. These steps start the synthetic kernel on a local Ubuntu machine. They do not record the fresh-host case.

## Support

The documented host is Ubuntu 22.04 with Python 3.12 and uv. Docker is used only for the disposable PostgreSQL service. macOS is not part of this setup. A fresh Ubuntu bootstrap, including startup time and idle RSS, is `AOS-001-TC04` and remains unrun.

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

Export the names in `.env.example`. Panestria reads the process environment and does not load that file. The password there is a placeholder.

```bash
make dev-api
make r0-demo
```

`make dev-api` listens on `127.0.0.1`. A non-loopback bind is rejected. `make r0-demo` needs the migrated database. It submits one synthetic goal, approves it, and prints the completed status. Each run uses a new idempotency key. That command is not `AOS-001-TC04`.

## Checks

```bash
make lint
make typecheck
make test
```

`make test` excludes the live fresh-host test. Provider credentials are not required.
