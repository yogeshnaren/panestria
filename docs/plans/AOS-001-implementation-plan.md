# AOS-001 — Repository scaffold, developer toolchain, CI and local services: implementation plan

**Release:** R0. **Format:** checklist; shared design supplies cross-component detail. **Historical baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917 (README and MIT LICENSE only). **Live status:** S1–S3 implemented and TC01–TC04 observed passing; owner handoff acceptance is pending. **Depends on:** none.

**Current technical validation:** G0 PASS on `f161193ed31918592015ec9e68163d31d77cb0ae`; all R0 cases observed, including fresh Ubuntu. Owner acceptance remains pending. See [completion](../reviews/R0-DEMO-REVIEW.md). Earlier status lines below are historical.

Read [architecture](../design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](../design/02-DATABASE-AND-MIGRATIONS.md), [security](../design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](../design/04-API-AND-USER-FLOWS.md), [decisions](../design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](../testing/TEST_EXECUTION.md) and [source spec](../specification/specs/AOS-001.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

An unassisted developer can clone, bootstrap and test a modular-monolith project on supported Ubuntu without a cloud account or real model subscription.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/config.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/api/main.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/api/health.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/cli/main.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `create_app(settings, readiness_probe) -> FastAPI`
- `Settings.validate_profile() -> ValidatedSettings`
- `HealthService.readiness(deadline) -> Readiness`

**Migration ownership:** Alembic scaffold only; no domain tables.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-001-F01 | Use one Python 3.12+ distribution managed by `uv`, one `pyproject.toml`/lockfile and `src/agentos/` with `contracts`, `kernel`, `execution`, `brokers`, `policy`, `resources`, `memory`, `telemetry`, `verification`, `api` and `cli` sub-packages; reserve `apps/mission-control` for React/Vite later but do not require Node to execute the R0 API tests. | AOS-001-S1, AOS-001-S2, AOS-001-S3; owning files/interfaces above | AOS-001-TC01, AOS-001-TC02, AOS-001-TC03, AOS-001-TC04; parameterize every condition in this clause |
| AOS-001-F02 | Pin Python/Node dependencies, create `pyproject.toml`, lint/type/test commands, Alembic location, `.env.example` containing *only placeholders*, Docker Compose PostgreSQL with health check and persistent named volume. | AOS-001-S1, AOS-001-S2, AOS-001-S3; owning files/interfaces above | AOS-001-TC01, AOS-001-TC02, AOS-001-TC03, AOS-001-TC04; parameterize every condition in this clause |
| AOS-001-F03 | Document environment variable names, process modes, deterministic seeded synthetic project, local-only service binding, `make`/`just` commands and an offline dependency-cache strategy. No runtime arbitrary `pip install`. | AOS-001-S1, AOS-001-S2, AOS-001-S3; owning files/interfaces above | AOS-001-TC01, AOS-001-TC02, AOS-001-TC03, AOS-001-TC04; parameterize every condition in this clause |
| AOS-001-F04 | CI runs Ruff, Mypy, Import Linter boundary checks, unit and migration smoke tests; integration tests start an ephemeral DB and detect schema drift. Protect repo scripts from unreviewed auto-execution. | AOS-001-S1, AOS-001-S2, AOS-001-S3; owning files/interfaces above | AOS-001-TC01, AOS-001-TC02, AOS-001-TC03, AOS-001-TC04; parameterize every condition in this clause |
| AOS-001-AC01 | Fresh Ubuntu VM bootstraps from clean checkout using documented commands. | AOS-001-S1, AOS-001-S2, AOS-001-S3; owning files/interfaces above | AOS-001-TC01, AOS-001-TC02, AOS-001-TC03, AOS-001-TC04; parameterize every condition in this clause |
| AOS-001-AC02 | CI enforces Ruff, MyPy, Pytest, dependency-lock reproducibility and basic secret scanner; unit tests run without provider credentials. | AOS-001-S1, AOS-001-S2, AOS-001-S3; owning files/interfaces above | AOS-001-TC01, AOS-001-TC02, AOS-001-TC03, AOS-001-TC04; parameterize every condition in this clause |
| AOS-001-AC03 | PostgreSQL service is healthy and migration check returns zero; API inaccessible from non-loopback interface; no unexpected egress during smoke test. | AOS-001-S1, AOS-001-S2, AOS-001-S3; owning files/interfaces above | AOS-001-TC01, AOS-001-TC02, AOS-001-TC03, AOS-001-TC04; parameterize every condition in this clause |
| AOS-001-AC04 | Failing lint/test/prohibited dependency injection makes CI fail; no real keys in commit, build image or logs. | AOS-001-S1, AOS-001-S2, AOS-001-S3; owning files/interfaces above | AOS-001-TC01, AOS-001-TC02, AOS-001-TC03, AOS-001-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-001-S1](../cursor/prompts/AOS-001-S1.md) | repository inventory | One installed src/panestria package, strict settings and typed health with unit fixtures; preserve MIT/license and write naming ADR. | AOS-001-TC01; command/report/exit, immutable evidence and diff |
| [AOS-001-S2](../cursor/prompts/AOS-001-S2.md) | AOS-001-S1 | Frozen dependency/bootstrap commands, Ruff/Mypy/Import Linter, provider-free CI and deliberately failing boundary fixtures. | AOS-001-TC02; command/report/exit, immutable evidence and diff |
| [AOS-001-S3](../cursor/prompts/AOS-001-S3.md) | AOS-001-S2 | Scoped PostgreSQL Compose/migration scaffold, fresh-machine/offline-cache/loopback/reset proof and setup runbook. | AOS-001-TC01, AOS-001-TC02, AOS-001-TC03, AOS-001-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-001-TC01 | unit | `tests/integration/test_aos_001.py` | Valid SYNTHETIC_DEV config and unavailable DB produce truthful bounded health; invalid bind/secret-bearing output rejected. An oversized header line is rejected and is not echoed. A slow database call does not stop /healthz. Several tests in that module map to this one scenario group. |
| AOS-001-TC02 | contract | `tests/contract/test_aos_001_toolchain.py` | A disposable forbidden import, stale lock, failing lint/type/unit each fail its gate; positive installed src imports pass. |
| AOS-001-TC03 | integration | `tests/integration/test_aos_001_postgres.py` | Fresh scoped DB is healthy, empty Alembic scaffold applies, wrong-volume/symlink cleanup denied. |
| AOS-001-TC04 | live | `tests/integration/test_aos_001.py::test_fresh_host_loopback` | Fresh supported Ubuntu bootstrap, dependency cache and no-egress runtime smoke require no AI credentials; record real sockets/startup/RSS. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_001.py --junitxml=evidence/AOS-001.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

## Failure, operations and rollback

Unsafe scope/config/version/malformed evidence is non-retryable denial; transient safe I/O uses bounded retry; ambiguous external effects pause in RECONCILING. Mutations check current owner/project/contract/epoch and append events atomically. Timeouts/cancellation preserve durable state; diagnostics redact sensitive content. No generic retry can create exactly-once external effects.

Capture relevant task/attempt/epoch/policy/trace and immutable evidence IDs. Roll out behind this capability gate. On regression stop affected admissions, retain history/receipts/evidence and revert code/config; migrations use tested restore/forward repair. Never blindly delete history or compensate a confirmed effect. Implement setup/diagnosis, stuck-state and scoped cleanup runbook steps with this item.

## Item completion

- [ ] Every source clause maps to actual assertions and observed evidence.
- [ ] Required scenarios PASS for one recorded candidate/environment; missing/skipped/unknown/live gaps remain blockers.
- [ ] Migration/API/adapters match the approved design; material changes have an ADR.
- [ ] Applicable live/compatibility, runbook and rollback/restore evidence complete.
- [ ] User-visible results are verifiable; worker narrative grants no authority.

Only then complete this item. A release cannot promote while its other required items remain unfinished. AOS-030 trial/owner acceptance decides complete MVP; SOTA authorization remains separate.
