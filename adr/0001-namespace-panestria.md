# ADR 0001: Distribution name panestria

Status: accepted for AOS-001-S1. Design decision D01.

## Context

The preserved AOS-001 source clause names the tree `src/agentos/` and the product AgentOS. Design decision D01 selects one distribution whose package and CLI match this repository. The existing root license is MIT, copyright 2026 Yogesh Naren Bundey. This slice needs an installed package, strict synthetic settings, and a typed health endpoint. It does not need domain workflows.

## Decision

- The installable distribution, import package, and console script are `panestria`.
- Application code lives under `src/panestria`. `src/agentos` is not created.
- Historical `agentos` names in `docs/specification/` stay untouched.
- Sub-packages listed in the source clause (`contracts`, `kernel`, `execution`, `brokers`, `policy`, `resources`, `memory`, `telemetry`, `verification`, and the later `research` and `sandbox` packages) are created by the slice that implements a tested path. AOS-001-S1 creates only `api` and `cli`, plus root `config.py`.
- `apps/mission-control` is reserved for a later release and is not created here. R0 tests do not require Node.
- Settings for this slice accept only profile `SYNTHETIC_DEV`, schema version 1, and a literal loopback bind (`127.0.0.0/8` or `::1`). Other deployment profiles remain disabled until their own slice.
- Process entries in this slice are the library `create_app` and the `panestria` CLI (`version`, `health`). There is no worker, database client, or domain command.
- Settings are read from the process environment with prefix `PANESTRIA_`. `.env.example` documents placeholders and is not loaded.
- The root `LICENSE` file remains the existing MIT text.

## Consequences

Import and CLI checks use `panestria`. A test that required `src/agentos` would contradict D01. Full AOS-001 functional clauses that require the lockfile gate, lint, CI, Compose, or a fresh host remain later slices. Health must not report an executor or database as ready unless a probe actually observed that dependency; this slice's service records the executor as `not_configured`.
