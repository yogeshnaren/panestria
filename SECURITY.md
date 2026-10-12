# Security

Panestria R0 is a local synthetic kernel. It is not a hosted service, and R0 is not accepted. Do not point it at production data, personal data, or a real model account.

## Reporting

Report a vulnerability privately to the repository owner. Do not include live passwords, provider keys, or production data in the report. A synthetic request and the source commit are enough.

## Local boundaries

The API binds `127.0.0.1` only. A non-loopback bind is rejected. Compose publishes PostgreSQL on `127.0.0.1:55432` and does not mount the Docker socket into the database container.

`.env.example` contains placeholders. Panestria does not load it. Health and error output must not print the database URL or password. CI does not inject provider credentials and runs only the reviewed commands in `.github/workflows/ci.yml`.

The synthetic token and the placeholder database password are not credentials for any other system. Do not reuse them outside this repository.

## Out of scope for this tree

Sandboxing arbitrary code, real provider authentication, and a public deployment are not provided. R1 security hardening is required before any of those uses.
