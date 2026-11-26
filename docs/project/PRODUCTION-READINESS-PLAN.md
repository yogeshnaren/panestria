# Panestria production-readiness plan: self-hosted Release 1 (v1.0)

**Status:** proposed, 2026-11-23. The owner made the scope decisions below and approved this plan in a working session. They take effect when [ADR 0016](../../adr/0016-self-hosted-release-1-scope.md) is accepted.

**How to read this document:**
- Code paths are relative to `src/panestria/` unless they start with `tests/`, `migrations/`, `docs/`, `tools/`, `apps/` or `.github/`, or name a repository-root file.
- "RP" is the [R3 remediation plan](R3-REMEDIATION-PLAN.md). Items here reuse its IDs and do not duplicate them.
- The detailed findings are in a review record the owner keeps private. It describes security defects that are not yet fixed. Publish it, or the relevant parts, once the items marked **(private case set)** below have landed.

## Context

An adversarial review on 2026-11-23 of `main` at `29c2092` found:

- **Static checks pass.** Ruff, format, mypy strict, import-linter, secret scan and the compat surface are all clean.
- **67 of 2,627 non-live tests fail on a stock Ubuntu checkout**, mostly for environmental reasons:
  - umask 0002 makes packaged scripts group-writable, so the gateway rejects them;
  - Node 16 is on PATH for the browser tests;
  - one timestamp-racy test.
- **Functional defects:**
  - there is no recovery after a crash, for either goals or the Ask server;
  - RESTRICTED/PRIVATE memory handling does not meet the classification policy;
  - one oversized pinned note blocks every Ask;
  - `/readyz` can never return 200;
  - `alembic downgrade base` wipes a populated database;
  - merges and cancellations can get stuck;
  - there is no lease reaper.
- **Security hardening** is needed in input handling, credential checks, rate limiting, session scope, path-policy semantics, verification independence and prompt-injection resistance. The details are in the private record. The containerised-CLI and SNI work is already public in ADR 0010.
- **Missing pieces:**
  - packaging, setup, logging, backup/upgrade, release engineering;
  - private-repo Build policy;
  - Codex, Delegate adjudication and gate tooling.
- **Existing remediation plan.** `docs/project/R3-REMEDIATION-PLAN.md` (RP) already plans much of this. Phase 0 and most of Wave 1 landed. RP 1.7 and Waves 2–8 have not started; `main` has had only dependency bumps since 2026-10-28.

**Owner decisions (2026-11-23):**

1. **Deployment model:** self-hosted per user, with each user running a single-owner instance.
2. **Release 1 scope:**
   - offline Ask;
   - one-worker Claude Build;
   - Mission Control for these.
   - Delegate, Codex, two-worker Build, phone, background quota work, encrypted profiles and cloud inference move to Release 2 behind flags that default to off.
3. **Platform:** Linux x86-64 only.

**Outcome:** a signed v1.0 that a new user can install, set up, run as a service, back up, upgrade and recover after a crash. It must pass a Release-1 gate, a 14-day owner trial, an external beta and a pentest.

**Ground rules:**

- **Governance.** This pulls R7 distribution items ahead of the R3 gate. AGENTS.md requires that owner decision to be recorded (0.1).
- **PR discipline.** One `task/<name>` PR per cohesive change (`docs/TASK_PR_WORKFLOW.md`).
- **Tests first.** Every defect fix starts with a failing test that reproduces it.
  - Tests for defects whose fix lands in a later phase go in now as `xfail(strict=True)` with the item ID.
  - Items tagged **(verify)** come from code reading only; reproduce them first.
- **Migration train.** One migration PR in review at a time, each with an N-1 upgrade test. The order is listed under Sequencing.

## Release scope

| Release 1 (v1.0, supported) | Release 2 (off by default) | Not planned |
|---|---|---|
| Offline Ask with scoped memory | Delegate research (AOS-019..023) | Hosted multi-tenant service |
| One-worker Claude Build on the user's own repos | Codex adapter; two-worker plans | macOS, Windows, arm64 |
| Mission Control: Ask, Build review and evidence, activity | Phone companion; background quota queue | Rootless Docker (Release 2) |
| setup, doctor, service, backup, upgrade, logs | Encrypted profiles; cloud SDK route; usage/cost/trace views; multi-call tool loop | — |

**Process model (fixed here, per RP 3.3):**

- one app server (API and UI) that never runs workflows;
- one `panestria worker` process that runs Ask inference admission and durable Build workflows;
- PostgreSQL.
- All three are `systemd --user` units.

## Phase 0: decisions (week 1)

| ID | Item | Done when |
|---|---|---|
| 0.1 | Record this plan and [ADR 0016](../../adr/0016-self-hosted-release-1-scope.md), which covers release scope, phase re-ordering, the process model and migration policy. After acceptance, align `docs/phase-tracker.json` and the phased-plan header. | ADR accepted by the owner |
| 0.2 | ADRs: confirm 0012 (local OTel) and 0014 (pacing, already shipped). Defer 0013 (Delegate) and 0015 (X14). ADR 0016 also records forward-only migrations with rollback by restoring a backup; RP 6.6c implements it. | Statuses updated |
| 0.3 | Branch protection with the 8 required jobs. CI runs `tools/ci_*.py` and `docs/testing/ci-regression-policy.json` from the base ref, so a PR cannot loosen its own selection. | A PR that edits the policy still runs the base policy |
| 0.4 | Licensing: confirm MIT and remove "Apache-2.0 candidate". Add NOTICE entries for `hwprobe.py` (Apache-2.0 per the skills front matter), psycopg (LGPL-3.0) and certifi (MPL-2.0). Fix `docs/CREDITS.md`. | NOTICE in the wheel |
| 0.5 | **Gate.** Confirm that automated per-user Claude Code subscription use through this harness is permitted, and write the user notice. If it is not, Release-1 Build needs the API-key route, which changes scope; decide before 2.5 starts. | Owner/legal sign-off recorded |
| 0.6 | Docker: Release 1 supports rootful Docker with a documented root-equivalence warning. Rootless needs uid/cgroup rework (`sandbox/runner.py:247`, `inference/runtime.py:116,208`) and moves to Release 2. | Recorded |
| 0.7 | Decide which RP verification items Release 1 keeps: mutation ≥90% on safety modules, `junit_guard` (unexpected-skip guard), independent re-score. Recommendation: keep all three. | Recorded |

## Phase 1: stabilise and restructure (weeks 2–7)

### 1A Test and CI trust (first)

| ID | Change | Key files | Done when |
|---|---|---|---|
| 1.1 | Stop trusting packaged gateway scripts by file mode:<br>• pin the sha256 of `sandbox/scoped_bash.py` as a build-time constant and verify the bytes, which already travel in the input frame (`native_tool_gateway.py:217-221`), against it;<br>• keep the mode/owner check only for owner-supplied check scripts;<br>• install-permission integrity, including the read-only mounts at `:223-224`, moves to `doctor` (3.3). | `execution/scoped_bash.py:150`, `sandbox/native_tool_gateway.py:131-151` | kernel + platform lanes green under umask 0002 and 0022 |
| 1.2 | Add `st_nlink` to `_key`; make the test cross a real timestamp tick. | `execution/source_digest.py:30`, `tests/unit/test_source_digest.py` | 50 consecutive local runs pass |
| 1.3 | Browser tests: require Node ≥20.19 from `PANESTRIA_TEST_NODE` or PATH; skip locally, fail in CI, following the `requires_nonroot` pattern in `tests/conftest.py`. | 13 `test_mission_*` / `test_phone_*` files | No Node-16 failures locally |
| 1.4 | CI fixes:<br>• `make ci-full` includes the boundary lane;<br>• separate concurrency groups for push, schedule and PR;<br>• coverage floors enforced on PRs;<br>• pip-audit and `npm audit` on PRs;<br>• an issue is opened when the nightly run fails. | `Makefile:33`, `.github/workflows/ci.yml:23,207` | A floor drop fails the PR |
| 1.5 | Hermeticity matrix job: kernel and platform lanes under umask 0002 and Node 20. | `ci.yml` | Prevents 1.1–1.3 regressions |

### 1B Structure needed by everything else (RP Wave 2 subset; merges the old 1.11 and 3.5)

| ID | Change | Key files and reuse | Done when |
|---|---|---|---|
| 1.6 | RP 2.1: move `_lock`, `_private` and `_atomic` out of `execution/proposal_demo.py` into a platform fsutil module. They are imported by `owner_build`, `native_plan`, `offline_build`, `background_run`, `local_plan`, `local_repair`, `native_qualification` and four other modules. | `execution/proposal_demo.py` | No product module imports demo code |
| 1.7 | RP 2.2 packaging:<br>• the wheel ships migrations, a vendored `hwprobe` module (no zip at runtime), the built Mission Control `dist/` and NOTICE;<br>• pin hatchling;<br>• Linux classifiers;<br>• ship a hash-pinned constraints file (`uv export --frozen`) and install with it (pipx or `uv tool`).<br>CI smoke test: a non-editable install in a fresh venv under both umasks. | `pyproject.toml`, `resources/hardware.py:21,57`, `api/local_server.py:92` | The installed wheel runs migrate and starts |
| 1.8 | RP 2.3 devkit split: `api/serve.py`, `demo.py`, `execution/synthetic_journey.py`, the proposal demo and `cli/review_demo.py` (which has a `/home/yogesh` path) leave the wheel. `task_workflow.py:351` stops importing `SyntheticJourney`. | — | Wheel has no demo code; R0 tests run from the dev-only package |
| 1.9 | RP 2.9 app factory: one uvicorn app serving Ask, Mission Control (all Release-1 views), Build review, activity and the goal/approval/artifact routes. Replaces the hand-rolled R0 server and one-mode-per-process (`api/mission_web.py:66-93`). | `api/main.py`, `api/local_server.py`, `api/activity_server.py` | One port; SSE streams correctly |
| 1.10 | RP 2.5 subset: a DB connection pool. LISTEN/NOTIFY is deferred; polling is fine for one user. | `api/db.py`, `api/event_stream.py` | A dashboard tab opens fewer than 2 connections per second |

### 1C HTTP and CLI robustness (on the factory app from 1.9)

| ID | Change | Key files | Done when |
|---|---|---|---|
| 1.11 | Harden credential comparison for every input. | `api/auth.py` | Every malformed-credential case returns 401 **(private case set)** |
| 1.12 | Input-handling hardening:<br>• typed path and query parameters;<br>• bounded request parsing;<br>• a global exception handler that returns the standard envelope and logs;<br>• database errors mapped to 4xx or retryable 503. | `api/routes/*.py`, `api/main.py` | Every malformed-input case gets a JSON 4xx/5xx and a log line **(private case set)** |
| 1.13 | Rework rate limiting: one bucket per credential, health and static assets handled separately, budget sized for dashboard polling. | `api/security.py` | Rate-limit cases pass **(private case set)** |
| 1.14 | Readiness checks DB, migration head, model socket, Docker and enabled features; healthy → 200. Worker heartbeat is added after 2.3. | `api/health.py:377,416` | `/readyz` 200 when healthy; `panestria health` exits 0 |
| 1.15 | CLI:<br>• tokens from file or env, never argv;<br>• hardened HTTP client settings;<br>• JSON-safe errors;<br>• `--verbose`;<br>• a documented exit-code taxonomy. | `cli/goals.py`, `cli/approvals.py`, `cli/main.py:69` | No token in process listings; no tracebacks **(private case set)** |

### 1D Kernel liveness: what Phase 1 fixes now

| ID | Change | Key files | Done when |
|---|---|---|---|
| 1.16 | Failing tests (`xfail(strict=True)`) for all kernel defects fixed in 2.1 and 2.2:<br>• a cleanly refused merge stuck in RECONCILING;<br>• cancel only handles the first task and is blocked by a PREPARED effect;<br>• lease death on the last attempt; exhausted RETRY_WAIT **(verify)**. | `tests/integration/` | Tests land, fail as expected and are tracked |
| 1.17 | Approvals:<br>• commit EXPIRED before raising (it is rolled back today);<br>• allow re-request after expire, deny or revoke (transition back into WAITING_APPROVAL);<br>• reject a past `expires_at`;<br>• use `clock_timestamp()` consistently;<br>• cancel closes pending approvals;<br>• `list_pending` hides terminal goals. | `kernel/approvals.py:232-246`, `contracts/task.py:38-61`, `contracts/approval.py:66` | An expired approval persists and can be re-requested |
| 1.18 | Orphan reaping at worker start: sandbox containers via the existing, uncalled `DurableToolAuthority.reconcile_launch` (`execution/tool_authority.py:94`). No home-made goal rescan; durable recovery is 2.3's job. | — | SIGKILL mid-build → no orphan containers after restart |
| 1.19 | Migration safety (no migration of its own; first in the train):<br>• `lock_timeout` in `migrations/env.py`;<br>• the N-1 upgrade harness, covering the DBOS system schema;<br>• the product CLI exposes no downgrade, per ADR-0016;<br>• alembic downgrades for 0001–0017 refuse populated data. | `migrations/env.py:33`, `migrations/versions/0001-0017` | `downgrade base` on a populated DB refuses |

### 1E Ask and memory

| ID | Change | Key files | Done when |
|---|---|---|---|
| 1.20 | Ask crash recovery:<br>• reclaim the model container when the controller is provably dead, reusing the proof logic in `ModelRuntime._reap_orphans`' non-preserve branch (`inference/runtime.py:96-128`);<br>• remove the stale socket;<br>• startup reconciler for `ask_request` rows left PREPARED/RUNNING past their deadline;<br>• `local init` validates socket path length ≤107 bytes;<br>• default runtime dir `$XDG_RUNTIME_DIR/panestria`. | `inference/runtime.py`, `api/local_server.py:90`, `cli/local_init.py` | SIGKILL mid-Ask → clean restart; long paths refused at init |
| 1.21 | Finish RP 1.2 (migration): refuse new RESTRICTED/PRIVATE memory with `memory_restricted_requires_vault` plus a DB trigger; flag existing rows for owner review; Ask/TUI explain why. | `memory/service.py:93-112` | Private-label memory is refused outside the vault |
| 1.22 | Deletion, MVP-X03 (migration):<br>• SECURITY DEFINER purge plus tombstone for memory, corrections and curated examples;<br>• history omits suppressed bodies by default;<br>• backup limits documented. | `memory/service.py`, `learning/curation.py` | `panestria memory purge` removes bodies |
| 1.23 | Memory limits and query:<br>• pin budget and pin count checked at add/pin time;<br>• FTS lexemes quoted so a leading `-` is not negation;<br>• FTS predicate pushed into the scoped query. | `memory/service.py:204-223`, `memory/context.py:114-135` | Oversize pin refused; "-5 degrees" has no stray hits; EXPLAIN uses the index |
| 1.24 | Injection resistance (no schema change):<br>• refuse pinning of non-owner-authored (derived) memory;<br>• add injection cases to `tests/fixtures/ask/golden-v1.json`;<br>• answers list the sources used. | `memory/context.py`, `execution/offline_build_recall.py` | Injection cases have a documented expected behaviour **(private case set)** |
| 1.25 | Resource admission:<br>• unknown power state allowed (desktops and VMs), configurable;<br>• thermal observed or the dead branch removed;<br>• disk measured on the data and model volumes. | `resources/admission.py:36-39`, `resources/hardware.py:65,100` | Ask runs on a battery-less desktop and in a VM |

## Phase 2: one-worker Build safe on real repositories (weeks 5–18, two parallel streams, then 2.8)

**Stream A: durable kernel**

| ID | Change | Key files | Done when |
|---|---|---|---|
| 2.1 | Task state machine (RP 3.1, migration): one compare-and-set transition function replacing about 25 raw `UPDATE … SET state`; every transition emits an event; the trigger runs in **warn mode**. Fixes cancellation of every task (`kernel/cancellation.py:53-96`, including the hard-coded `"CREATED"` at :96), PREPARED-cancellable effects, and the lease reaper ordering and exhaustion handling (`kernel/leases.py:50-155`). Depends on RP 1.7. | `kernel/transition.py`, `kernel/{leases,retries,effects,scheduler,build,cancellation}.py` | 1.16 kernel xfails pass |
| 2.1b | RP 3.1b: the trigger switches to enforce after a 2-week soak with zero violations. | migration | Illegal transitions rejected by the DB |
| 2.2 | Effect ledger plus stuck-effect sweeper (RP 3.2/3.7, migration):<br>• adds `FAILED_NO_EFFECT` (the `side_effect` check at `0002_kernel.py:214` lacks it);<br>• `reconcile` honours NoEffect;<br>• a CAS refusal or pre-I/O revalidation denial is definitive;<br>• `panestria build reconcile` plus owner resolution;<br>• the base-moved case offers "re-verify on new base". | `execution/outbox.py:46-60`, `kernel/effects.py:227-305`, `execution/protected_merge.py:90-126` | Two builds on the same base: the second ends FAILED with a re-verify option |
| 2.3 | DBOS worker runtime and durable Build workflow (RP 3.3/3.4):<br>• unique `executor_id` per process; stable `application_version`;<br>• transient DB errors retried, not terminal;<br>• `panestria worker` unit;<br>• Build moves out of the CLI process (`cli/build.py:33`) and out of API threads (`MissionRunService`). | `execution/task_workflow.py`, `dbos_runtime.py`, `owner_build.py` | Kill at any step → resume or settle (drills 4.6) |

**Stream B: worker isolation (starts after 0.5 clears)**

| ID | Change | Key files | Done when |
|---|---|---|---|
| 2.4 | RP 2.13 `refactor-sandbox-execute`: split launch, attach and settle so a long-lived CLI container is possible. | `sandbox/runner.py` | No behaviour change (compat-checked) |
| 2.5 | Egress SNI enforcement: ClientHello SNI must equal the CONNECT host (RP 4.1). | `sandbox/egress.py:141-152` | Domain-fronting test denied |
| 2.6 | Claude CLI in a container behind the gateway (ADR 0010, RP 4.2). Resolve in the ADR before coding:<br>• a writable per-user CLI config volume, needed for OAuth refresh (today `claude_check.py:185` passes the real config dir);<br>• the MCP bridge as a host-side process over a mounted Unix socket, because `sys.executable -m panestria…` does not exist in the CLI image.<br>Reuse `sandbox/native_proxy_relay.py` and `brokers/harness/native_bootstrap.py`. | `brokers/harness/claude_check.py:181-289`, `process_runner.py` | The CLI has no host filesystem or network beyond the allowlist; login refresh works |
| 2.7 | Claude Code version support:<br>• a supported-version manifest instead of a single binary hash (`claude_proposal.py:27`);<br>• local requalification from the installed package with packaged fixtures (`native_qualification.py:161`);<br>• a configurable model-id allowlist (`event_parser.py:282`);<br>• a live-lane canary. | — | A new CLI version is qualified by a command |

**After A and B: real repositories (the largest risk on the critical path)**

| ID | Change | Key files | Done when |
|---|---|---|---|
| 2.8 | Private-repo Build policy and plumbing (ADR 0011, RP 4.6, migration):<br>• replace the PUBLIC-only gates (about 31 checks, e.g. `owner_build.py:178`, `native_build.py:86`) with a per-repo grant and an export decision;<br>• `.env`/`.ssh`/secret exclusion and a secret-scan block;<br>• import from a local path or branch;<br>• export the approved merge as a local branch or patch, never pushed. | `execution/owner_build.py`, `verification/git_snapshot.py`, `cli/build.py` | Build runs on a private repo with explicit consent; the user receives a branch |
| 2.9 | Path policy:<br>• real glob semantics, or reject unsupported patterns at contract load;<br>• case-insensitive dotfiles;<br>• default protected and review-required paths bound into the preview (`.github/workflows`, `.gitattributes`, `.gitmodules`, `CLAUDE.md`, `AGENTS.md`, `.codex`, `.vscode`, `.npmrc`, `.netrc`). | `verification/paths.py`, `contracts/goal.py`, `verification/git_snapshot.py` | Path-pattern cases pass; unsupported patterns are rejected at load **(private case set)** |
| 2.10 | Verification honesty:<br>• checks and tests in protected paths;<br>• static screening of diffs for check-subverting patterns;<br>• a separate verification deadline;<br>• the UI states that checks are evidence and the exact-diff approval is the authority. | `verification/sandboxed.py`, `execution/native_build.py` | Check-subversion cases are flagged; real suites fit their budget **(private case set)** |
| 2.11 | Build envelope: configurable budgets (context selection, script and attempt time) within safe caps, plus an owner-declared toolchain image digest for checks. The multi-call tool loop is deferred to Release 2. | `execution/native_build.py:86,146`, `owner_build.py:176`, `sandbox/profiles.py:12` | Representative real-repo tasks complete within budget |
| 2.12 | Workspace GC after terminal states (evidence kept); storage admission in `OwnerBuild.submit`; `git gc` of `destination.git`. | `owner_build.py`, `build_storage.py` | Flat disk use over 50 builds |
| 2.13 | Review UX:<br>• paginated diff, no 64 KiB cap;<br>• binary and non-UTF-8 listing;<br>• approval requires the diff to have been viewed;<br>• watchdogs reuse a pooled connection with backoff. | `execution/build_review.py:96-110`, `BuildReview.tsx`, `native_tool_gateway.py:256-289` | A large diff is reviewable; a 1 s DB stall does not burn the attempt |

## Phase 3: installable, operable product (weeks 6–20)

| ID | Change | Done when |
|---|---|---|
| 3.1 | One versioned config file with a migration path (RP 2.4). A `features` section is the kill switches. **The flags-off configuration is the one the gate and pentest test.** | Old configs migrate; disabled features unmount and refuse clearly |
| 3.2 | `panestria setup`, `doctor` and `uninstall` (RP 6.6a), reusing `cli/local_init.py` and `kernel/local_setup.py`:<br>• prerequisite checks: nonroot, Docker, Ollama, Claude login, ports, disk, install-permission integrity (from 1.1);<br>• DB provisioning with a generated 0600 password, restart policy and no published synthetic credentials;<br>• pulls the sandbox, model and CLI images by digest and prunes old ones (runners use `--pull never`);<br>• `loginctl enable-linger`;<br>• `doctor --report` produces a redacted bundle;<br>• uninstall keeps data unless told otherwise. | Wheel → working Ask without reading code |
| 3.3 | `panestria model pull`: explicit consent, digest-verified; Ollama binary hash and version-range checks (`inference/runtime.py:22-24,169-177`). | No hand-built model cache |
| 3.4 | `systemd --user` units for app, worker and DB; graceful SIGTERM; single-instance locks; `service install/status/logs`. | Services return after reboot |
| 3.5 | Logging and local tracing (RP 2.12, 7.4):<br>• JSON logs to journald with redaction;<br>• every 5xx, auth failure and swallowed `except Exception` is logged;<br>• install `Telemetry`/`TraceRequests` (currently never called);<br>• no off-host export. | Every probe failure leaves a log line with a correlation id |
| 3.6 | Backup, restore, upgrade (RP 6.6b/6.6c):<br>• backup covers DB, blob and evidence stores and configs, optionally encrypted;<br>• restore fence;<br>• automatic backup before upgrade;<br>• rollback = restore;<br>• Postgres major-version upgrade procedure;<br>• guard `make reset-synthetic-data` and fix the runbook's `down -v` (`docs/operations/RUNBOOK-AND-RELEASE.md:29`).<br>The per-domain restore tests (`test_profile_ask_restore.py`, `test_aos_003.py`, `test_local_setup.py`) become the drill's assertions. | CI drill: backup → wipe → restore → identical; upgrade N-1 → N |
| 3.7 | Retention for the Release-1 domains (Ask, Build, events, sessions, pairing, storage samples):<br>• `panestria prune --dry-run`;<br>• archive-then-delete via SECURITY DEFINER;<br>• lifetime caps become rolling windows (`kernel/quota.py:124`, `resources/storage_history.py:23`). | 6-month simulated growth stays bounded |
| 3.8 | Error catalogue (RP 2.11) for codes a Release-1 user can see, with meaning and fix-it text; `doctor` hints. | Every user-visible code is documented |
| 3.9 | Mission Control:<br>• session hardening for reads **(private case set)**;<br>• session list, revoke and logout after reload;<br>• focus management, axe checks and measured contrast (RP 7.3);<br>• experimental views hidden behind flags. | axe clean; session cases pass **(private case set)** |

## Phase 4: security, privacy, quality (weeks 12–22)

| ID | Item | Done when |
|---|---|---|
| 4.1 | A current STRIDE threat model covering local OS users, untrusted repos, model output, browser, supply chain and backups. | Each threat maps to a control and a test |
| 4.2 | Host hardening:<br>• random DB credentials reachable only by the owner;<br>• no world-writable `/tmp` defaults;<br>• XDG dirs 0700;<br>• assert the seccomp/AppArmor/userns state;<br>• `nosuid,nodev` binds. | Another local user cannot read DB, tokens or workspaces |
| 4.3 | `tests/security/` adversarial suite (RP 6.8), which turns the private case set into permanent tests, plus the hostile-repo corpus. | In CI; the private record can then be published |
| 4.4 | Supply chain:<br>• scan the Python, Postgres, Ollama and CLI image digests;<br>• Renovate;<br>• an SBOM covering Python, npm and images;<br>• a Sigstore-signed wheel with provenance;<br>• a digest-refresh process. | Release artifacts signed and attested |
| 4.5 | Privacy: data inventory, privacy notice, retention and erasure limits, and the provider-terms notice (0.5). | In the user docs |
| 4.6 | Fault drills (RP 6.4), k=5, nightly:<br>• kill mid-Ask;<br>• kill mid-Build before claim, after claim and during merge;<br>• DB outage;<br>• disk full;<br>• Docker restart;<br>• reboot. | All drills recover |
| 4.7 | Ask p95 on CPU reference hardware and a minimum-hardware statement, recorded in an ADR. | Regression check in CI |
| 4.8 | Release-1 gate: bind the relevant G1 cases plus production cases (wheel install, upgrade, backup drill, crash drills, adversarial suite, perf) to tests; RP 6.1/6.2 evaluator scoped as `REL1`. Keeps the 0.7 checks. | `gate evaluate --gate REL1` passes |
| 4.9 | External security review and pentest of the RC, in the flags-off configuration. | Highs fixed or owner-accepted |
| 4.10 | `SECURITY.md`: contact, supported versions, disclosure timeline, private reporting enabled. | Published |

## Phase 5: candidate, beta, GA (weeks 20–28)

| ID | Item | Done when |
|---|---|---|
| 5.1 | Docs (RP 8.2–8.8 subset):<br>• user docs covering install, Ask, Build, backup/upgrade, troubleshooting, security model;<br>• support matrix: Ubuntu 22.04/24.04 and Debian 12 in CI; Python 3.12, with 3.13 tested or capped;<br>• a generated STATUS replacing the contradictory status files;<br>• retire or CI-check `docs/CHECKSUMS.sha256`. | `doc_check` passes |
| 5.2 | Release engineering:<br>• semver and a CHANGELOG;<br>• a release branch with hotfix and backport rules;<br>• a tag-triggered release workflow (wheel, dashboard, SBOM, signatures);<br>• a security-update notice channel;<br>• a stated support window. | `v1.0.0-rc.1` built only by CI |
| 5.3 | RC freeze, then a 14-day owner trial. The pentest (4.9) runs during the trial. | No open S0/S1 |
| 5.4 | External beta from trial week 2: 5–10 users on varied hosts (battery-less desktop, laptop, VM) for 3 weeks, reporting via `doctor --report`. | ≥90% install without help; no data loss; crash recovery confirmed |
| 5.5 | GA: REL1 PASS, pentest highs closed, beta exit met. | `v1.0.0` |

## Release 2 backlog (after v1.0, each behind a flag)

- **Delegate:**
  - per-source denials and empty pages recorded instead of aborting;
  - a deadline stop and a RECONCILING→VERIFYING path;
  - relevance chunking instead of the first 384 bytes;
  - retryable stages;
  - fixes for hidden-text, encoding and PDF coverage;
  - grant ceilings;
  - SearXNG provisioning;
  - AOS-022 adjudication (RP 5.1/5.2);
  - the Delegate workflow (RP 5.3);
  - a live brief.
- **Workers:** the `WorkerAdapter` contract and Codex (RP 4.3–4.5); durable two-worker plans; the multi-call tool loop.
- **Other features:**
  - phone with real-device qualification;
  - a durable background queue without the 1-hour item lifetime;
  - encrypted profiles that work from an installed package;
  - a cloud SDK route wired to `BudgetService` and the exposure ledger;
  - usage, cost and trace views (RP 7.1/7.2);
  - SSE LISTEN/NOTIFY (RP 2.6);
  - rootless Docker.

**Hosted multi-tenant (not planned).** Its prerequisites, for the record:

- per-request identity;
- row-level security;
- per-tenant scheduler and locks;
- VM sandboxes;
- multi-process serving;
- KMS keys.

## Sequencing and estimates

**Critical path:**
0.1 → 1A → 1.6 → 1.7 → 1.8 → 1.9 → {Stream A: 2.1 → 2.2 → 2.3 ∥ Stream B (after 0.5): 2.4 → 2.5 → 2.6 → 2.7} → 2.8 → 3.2 → 4.6/4.8 → 5.3 → 5.4 → 5.5

**Migration train (strict order):**
1.19 (harness, no migration) → RP 1.7 side-table seq → 1.21 → 1.22 → 2.1 (warn) → 2.2 → 2.3 → 2.8 → 2.1b (after soak) → 3.7

**Parallel:**
- 1C/1E after 1.9;
- 3.1/3.5/3.8 alongside Phase 2;
- 4.1/4.4 early;
- 3.9 after 1.9.

**Estimate:** about 100–110 PRs, because many items span several PRs. Code-complete is around week 20–22. GA is around week 24–28, with the beta overlapping the trial's second week. These assume one developer with agent help at about 5 PRs a week, a pace that is not yet proven on RP Waves 2–3. Re-estimate at the end of Phase 1.

## Verification

- **Every PR:**
  - `make ci-full`, which includes the boundary lane;
  - the hermeticity matrix (umask 0002, Node 20);
  - `tools/compat.py check` against the baseline, with intended changes recorded in `docs/testing/compat-exceptions.json`;
  - coverage floors;
  - a failing-then-passing test for every fix.
- **Nightly:** the full profile, the fault drills (4.6), the adversarial suite (4.3), the wheel install smoke test (1.7), the backup/upgrade drill (3.6) and mutation testing on safety modules.
- **Live lane (owner host, before RC):**
  - Ask A-1 at k=5 with the real model;
  - Build on a real private repo with the containerised CLI;
  - CLI requalification;
  - a reboot drill.
- **Release:** `gate evaluate --gate REL1`, the trial (5.3), the beta exit (5.4) and the pentest (4.9).
- **The private case set becomes permanent tests** in `tests/security/` (4.3).

## Execution status

| Item | Branch | State (2026-11-25) |
|---|---|---|
| 0.1 | `task/production-readiness-plan` | Merged (#243); ADR 0016 is still proposed |
| 1.1 | `task/scoped-bash-digest-pin` | Merged (#245) |
| 1.2 | `task/source-digest-nlink` | Merged (#244) |
| 1.3 | `task/browser-test-node-gate` | Merged (#246) |
| 1.4 | `task/ci-gaps`, `task/coverage-deferral-tolerance` | Merged (#247); the PR deferral tolerance gained a measured `execution` override in #254 |
| 1.5 | `task/hermeticity-matrix` | Merged (#248) |
| 1.6 | `task/fsutil-module` | Merged (#249) |
| 1.7 | `task/packaged-assets`, `task/packaged-migrations`, `task/db-cli-coverage`, `task/wheel-install-smoke` | Part a merged (#255): skills archive, NOTICE and licence texts in the wheel. Part b merged (#257, in-process tests #260): migrations in the wheel, `panestria db status` and `panestria db upgrade`. Part c merged (#261): dashboard in the wheel, hash-pinned `constraints/runtime.txt`, and the required `wheel-install` CI lanes |
| 1.8 | `task/sandbox-prepare-image`, `task/devkit-split` | Merged (#258, #259): `panestria sandbox prepare-image`; the R0 demo, synthetic journey and proposal demo moved to the dev-only `devkit/`. `api/serve.py` stays until 1.9 |
| 1.9 | `task/app-factory`, `task/app-profiles` | Part a merged (#262): the goal API runs under uvicorn with `TransportLimits` instead of its own HTTP parser, and goal events stream over a real socket. Part b in review: one app factory, with every current server mode pinned by a golden surface test |
| 1.16 | `task/kernel-liveness-xfails` | Merged (#252): K1, K2 and K4 reproduced as 10 strict xfails for 2.1/2.2 |
| 1.17 | `task/approval-expiry` | Merged (#253) |
| 1.19 | `task/migration-safety` | Merged (#251); later migration PRs reuse `tests/migration_harness.py` |
| 1.23 | `task/memory-limits-query` | Merged (#250) |

Known CI flakes, not yet fixed:

- `test_aos_008.py::test_resource_pressure_is_contained[memory-memory_limit]`: an OOM kill reported as `process_failed`.
- `test_offline_native_bootstrap.py::test_real_container_failures_do_not_become_metadata_success[fail-failed]`: `deadline_exceeded` under host load.
- Build plan runs ending `STOPPED`, seen twice in `hermeticity (kernel)`
  (`test_build_storage_admission.py::test_actual_pressure_after_workers…`,
  `test_build_progress.py::test_failed_final_check…`). Under heavy local host
  load (about 5× slower lanes) many Docker-backed Build tests ended `STOPPED`
  in both umasks, and one passed alone at low load, so this looks
  load-sensitive rather than a umask issue. Not yet investigated further.

Every other item is NOT_STARTED.
