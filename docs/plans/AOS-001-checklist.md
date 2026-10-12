# AOS-001 — Panestria scaffold implementation checklist

**Superseded for execution.** The active item plan is [AOS-001-implementation-plan.md](AOS-001-implementation-plan.md), which has slices S1–S3. This checklist’s older S1–S4 split is historical. Do not start work from this file. The initial-commit inventory below remains historical baseline evidence.

**Repository:** [yogeshnaren/panestria](https://github.com/yogeshnaren/panestria). **Release:** R0. **Plan status:** superseded by the implementation plan. **Inspected baseline:** `main` at `4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917` on 2026-10-11. Recheck the branch before implementing; do not overwrite concurrent work.

This checklist applies the [AOS-001 specification](../specification/specs/AOS-001.md), [common requirements](../specification/COMMON-REQUIREMENTS.md) and [R0 contract](../specification/releases/R0-KERNEL-PROOF.md) to the actual initial repository. R3 remains the complete MVP boundary with owner review before SOTA implementation.

## Observed baseline and naming decision

- [x] GitHub API access verified. Repository is public; default branch is main.
- [x] Complete, non-truncated commit tree inspected: README.md (11 bytes, title only) and LICENSE (MIT). No application, dependency files, tests, CI, Docker setup or repository AGENTS.md exists in that tree.
- [x] Existing LICENSE is retained. No blanket conclusion about third-party skill/model licenses follows from the repository license.
- [x] Repaired specs, original archives and skill source are available in this local planning package. Their integrity/prototype results are recorded separately from application acceptance.
- [ ] Record ADR-PAN-001: working implementation package/CLI name panestria, one distribution, `src/panestria/`; retain AOS IDs. Apply this namespace mapping in active implementation references. The frozen AgentOS architecture and original archives remain historical originals. This is a proposed naming decision within this plan, not a completed rename or public package release.
- [ ] Confirm the exact Python 3.12 patch, uv/tool versions and PostgreSQL image digest in the bootstrap slice after compatibility checks. GitHub Actions and Docker Compose are proposed for this repository; Node/frontend setup waits until R3.

## Outcome and scope

A developer can obtain the repository, install locked dependencies, run lint/types/tests, start a scoped PostgreSQL fixture and a loopback health endpoint without an AI account. AOS-001 creates developer scaffolding; domain tables, durable task execution and real workers belong to later items. Unit tests must not depend on PostgreSQL being started or provider credentials being present.

## Exact planned files

| Files | Purpose |
|---|---|
| README.md, docs/SETUP.md, CONTRIBUTING.md, SECURITY.md | Project purpose, staged MVP/SOTA boundaries, prerequisites, development commands, synthetic reset and support/security notes |
| docs/decisions/ADR-PAN-001-naming-and-layout.md | Package/CLI namespace and path mapping from historical src/agentos |
| docs/roadmap/ and docs/specification/ | Reviewable roadmap/contracts/provenance selected for repository import; retain source hashes and original archives locally before any public publication decision |
| .gitignore, .python-version, .env.example | Exclude local environments/caches/secrets; pin interpreter; placeholder-only config names |
| pyproject.toml, uv.lock | One distribution, src layout, reviewed runtime/dev dependencies, package entry point and tool settings |
| src/panestria/__init__.py, config.py | Version/configuration metadata, explicit SYNTHETIC_DEV profile, validated loopback host and no secret echo |
| src/panestria/api/main.py, health.py | App factory, typed health response and separate dependency-readiness reporting |
| src/panestria/cli/main.py | Minimal command help/version entry point; reserve goal/approval commands for AOS-005 |
| .importlinter | Enforced contracts and layering as modules are introduced; no separate package distributions |
| alembic.ini, migrations/env.py, migrations/README.md | Migration scaffold only; AOS-002 creates domain tables |
| deploy/compose/postgres.yaml | Digest-pinned PostgreSQL, loopback-only optional developer port, healthcheck, named synthetic volume; no worker Docker socket |
| Makefile | bootstrap, lint, typecheck, test, db-up, db-down, db-migrate, dev-api, r0-demo and reset-synthetic-data contracts |
| tests/unit/test_config.py, test_health.py | Configuration/health success and negative cases without live DB |
| tests/architecture/test_import_boundaries.py | Disposable deliberately forbidden import proves architecture checks fail |
| tests/integration/test_bootstrap_database.py | Ephemeral synthetic DB, readiness/migration scaffold and safe teardown |
| .github/workflows/ci.yml | Frozen dependency checks, lint/types/unit/import checks, secret scan and separate DB smoke job |

Create additional sub-packages only when a real slice needs them. The eventual contracts/kernel/execution/brokers/policy/resources/memory/telemetry/verification boundaries are reserved by the spec; creating empty implementations for every future component is not an exit criterion.

## Sequenced slices — target about one developer-day each

| Slice | Prerequisite | Checklist | Acceptance and evidence |
|---|---|---|---|
| 001-S1 | Recheck repository HEAD | Preserve existing README/license, record naming ADR and source provenance, add minimal one-package metadata/config/health and unit fixtures | Frozen bootstrap succeeds; package imports from installed src layout; valid config/health tests pass; invalid bind/profile/config rejected |
| 001-S2 | S1 | Ruff/Mypy/Pytest settings, Import Linter contracts, Make targets and first CI jobs | Positive checks exit 0; deliberate lint/type/test/forbidden-import fixtures exit nonzero; retain clean CI output and lock hash |
| 001-S3 | S2 | Scoped Compose DB, healthcheck, Alembic scaffold and integration fixture | Healthy DB; migration scaffold upgrade/check does not create application domain tables; test teardown cannot target real data or traverse a symlink |
| 001-S4 | S3 | Setup/support/offline-cache docs, safe reset, secret scan, fresh-machine and loopback/no-egress smoke | Documented Ubuntu setup works with no AI credentials; cached dependency installation verified; service bound locally; bootstrap leaves no tracked artifacts/secrets |

Split a slice further if implementation estimates exceed about one day. Estimates await an actual checkout/environment inventory; four rows are not a four-day delivery promise. Review the concrete first slice before coding. No application implementation was executed as part of preparing this checklist.

## Interfaces and command contracts

- [ ] `create_app(settings, readiness_probe)` creates FastAPI without starting external services or contacting model/provider endpoints. Settings can be injected for tests.
- [ ] `GET /healthz` reports service liveness, version and profile with no paths/DSNs/tokens. Dependency readiness is explicit, bounded and injectable; a stopped DB reports degraded/unavailable rather than crashing liveness or inventing success.
- [ ] `make bootstrap` validates lock consistency and syncs frozen dependencies. It may download reviewed dependencies during an explicit setup; runtime code may not install packages. Document an offline-cache path separately.
- [ ] `make lint`, `make typecheck`, `make test` have stable nonzero failure exits. `make test` runs provider-free unit tests; integration checks are explicit and separate.
- [ ] `make db-up/db-down/db-migrate` operate only on the named local synthetic project and volume. Database-unavailable/missing-tool cases return actionable failures.
- [ ] `make dev-api` binds loopback by default. Non-loopback configuration is rejected in SYNTHETIC_DEV; logs redact connection secrets.
- [ ] `make r0-demo` clearly exits nonzero with “not implemented until AOS-005” for now; CI treats that expected stub separately. A successful health smoke must not claim the end-to-end kernel exists.
- [ ] `make reset-synthetic-data` validates profile/project/volume before action and cannot accept an arbitrary filesystem path. No teardown of real workspaces or automatic sudo provisioning.

Proposed verification commands after their files/dependencies exist (not run yet):

```text
uv lock --check
uv sync --frozen
uv run --frozen ruff check .
uv run --frozen mypy src/panestria
uv run --frozen lint-imports --config .importlinter
uv run --frozen pytest tests/unit tests/architecture
uv run --frozen pytest tests/integration/test_bootstrap_database.py
```

Import Linter's CLI/config behavior and uv's one-project pyproject/lockfile structure were checked against their official docs. Exact dependency/tool versions remain a recorded bootstrap compatibility result.

## Required acceptance matrix

| Requirement | Fixture/proof | Expected outcome |
|---|---|---|
| Reproducible fresh setup | Clean supported Ubuntu VM with documented prerequisites | All scaffold checks pass, no AI credentials needed; versions/hashes recorded |
| Locked dependencies | Stale metadata/lock discrepancy | Lock check fails; CI never silently rewrites the lock |
| Package/import separation | Disposable contracts module attempts to import API/CLI; later domain modules cannot import presentation/vendor modules | Import check fails; positive graph remains acyclic |
| Tests enforce truth | Failing unit/type/lint fixture | Corresponding check and CI fail, never masked by a shell wrapper |
| Typed configuration | Invalid profile, unsafe bind, missing/malformed DB configuration | Bounded safe error; secret values absent from error/log output |
| Dependency status | Probe returns unavailable, timeout or error | Accurate readiness state; liveness remains distinct and contains no invented DB success |
| DB scaffold | Fresh ephemeral PostgreSQL and empty migration scaffold | Health and Alembic check pass; no AOS-002 domain schema prematurely introduced |
| Local-only services | Inspect bound API/DB sockets; non-loopback client attempt | Loopback-only exposure; attempted forbidden bind rejected |
| Runtime egress | Unit/health smoke with outbound network blocked after dependencies are cached | No unexpected remote request; dependency setup and service runtime measurements distinguished |
| Secret hygiene | Synthetic scanner fixture and tracked-file scan | Synthetic secret rejected; placeholder .env.example accepted; no real credential read or logged |
| Safe cleanup | Wrong profile/volume and symlink/path escape fixture | Reset/teardown denied; unrelated files and databases untouched |
| Expected incomplete demo | r0-demo before AOS-005 | Explicit nonzero unavailable status; cannot be counted as R0 gate completion |

Enforce actual tool/database/OS guards where applicable. Do not substitute a prompt instruction or a CI badge for observed behavior. Architecture negative fixtures execute only in disposable copies; no deliberate breaking change is merged into the real package.

## Migrations, operations and rollback

- [ ] Schema changes are N/A beyond an empty Alembic scaffold. AOS-002 owns principal/project/goal/task/approval/event tables.
- [ ] Record startup time and idle RSS as measured baselines; do not promise hardware throughput from simulated probe presets.
- [ ] Document missing uv/Docker/DB service and occupied-port handling, bounded readiness timeouts, logs and scoped reset.
- [ ] Development/CI DBs use clearly named disposable instances. Runtime logs omit DSNs/passwords and do not scan personal directories.
- [ ] Rollback the scaffold commit and stop only its synthetic Compose project. Preserve named developer volumes unless the user intentionally resets synthetic data. No application history migration exists yet.
- [ ] Record actual code commit, CI run, lock/tool versions, fresh-machine transcript, loopback/egress observations and known limitations under release evidence. All evidence is currently pending.

## Completion and next item

- [ ] Every AOS-001 acceptance requirement passes; preserve negative-case evidence.
- [ ] README clearly distinguishes scaffold readiness, R0 kernel proof, R1/R2 pilots, R3 MVP review and later SOTA phases.
- [ ] AOS-001 status becomes implemented only after those observations; G0 remains incomplete until AOS-002–005 pass.
- [ ] Generate the AOS-002 full implementation plan against the resulting actual package/config/DB fixture, using the canonical acceptance schema and repaired shared contracts.

Sources: [inspected commit](https://github.com/yogeshnaren/panestria/tree/4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917), [uv project structure](https://docs.astral.sh/uv/concepts/projects/layout/), [Import Linter CLI](https://import-linter.readthedocs.io/en/stable/get_started/run/).
