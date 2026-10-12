# AOS-008 — Sandbox profiles, mount validation and enforceable outbound controls: implementation plan

**Release:** R1. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-004, AOS-007. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](../design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](../design/02-DATABASE-AND-MIGRATIONS.md), [security](../design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](../design/04-API-AND-USER-FLOWS.md), [decisions](../design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](../testing/TEST_EXECUTION.md) and [source spec](../specification/specs/AOS-008.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

Worker filesystem, process, resource and network access are constrained at OS boundaries before any real repository or vendor account is used.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/sandbox/profiles.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/sandbox/docker_runtime.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/sandbox/mounts.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/sandbox/network.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/sandbox/processes.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/sandbox/artifact_ingress.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `SandboxRuntime.create(profile, mounts, network_policy, budget) -> SandboxHandle`
- `SandboxRuntime.verify_effective_policy(handle) -> EnforcementManifest`
- `SandboxRuntime.destroy(handle, expected_identity) -> CleanupReceipt`
- `PinnedEgressGateway.authorize_connect(context, hostname, resolved_ips) -> ConnectionPermit`

**Migration ownership:** Versioned sandbox/capability/enforcement manifest records; protected profile and configuration digests.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-008-F01 | Define `mock-no-network`, `read-only-research`, `scoped-code-edit`, `restricted-offline` profiles with specific mount allowlist, process UID, cgroups/seccomp where supported, destination allowlist, capability flags, CPU/RAM/time bounds. | AOS-008-S1, AOS-008-S2, AOS-008-S3; owning files/interfaces above | AOS-008-TC01, AOS-008-TC02, AOS-008-TC03, AOS-008-TC04; parameterize every condition in this clause |
| AOS-008-F02 | Use Linux namespaces/bubblewrap or Docker with explicit hardening selected by threat model. Worktrees isolated but not trusted as sole security boundary; vendor CLIs may require authorized network egress to their endpoints. | AOS-008-S1, AOS-008-S2, AOS-008-S3; owning files/interfaces above | AOS-008-TC01, AOS-008-TC02, AOS-008-TC03, AOS-008-TC04; parameterize every condition in this clause |
| AOS-008-F03 | Protect against bind mount escapes, symlinks, hardlinks, Git hooks, known private credential paths, `/proc` escapes, shell config and unexpected proxies; test sandbox startup fail-closed. | AOS-008-S1, AOS-008-S2, AOS-008-S3; owning files/interfaces above | AOS-008-TC01, AOS-008-TC02, AOS-008-TC03, AOS-008-TC04; parameterize every condition in this clause |
| AOS-008-F04 | Disallow privileged containers, host Docker socket mounts and broad `$HOME` visibility; separate vendor CLI auth state from untrusted worktree filesystem. | AOS-008-S1, AOS-008-S2, AOS-008-S3; owning files/interfaces above | AOS-008-TC01, AOS-008-TC02, AOS-008-TC03, AOS-008-TC04; parameterize every condition in this clause |
| AOS-008-AC01 | Attempt read `~/.ssh`, `/etc/shadow`, parent of worktree, follow symlink outside root and resolve 127.0.0.1/169.254.169.254: blocked at OS/network boundary. | AOS-008-S1, AOS-008-S2, AOS-008-S3; owning files/interfaces above | AOS-008-TC01, AOS-008-TC02, AOS-008-TC03, AOS-008-TC04; parameterize every condition in this clause |
| AOS-008-AC02 | Network disallowed profile demonstrably cannot open remote or localhost socket; worker cannot mount broader filesystem or launch privileged container. | AOS-008-S1, AOS-008-S2, AOS-008-S3; owning files/interfaces above | AOS-008-TC01, AOS-008-TC02, AOS-008-TC03, AOS-008-TC04; parameterize every condition in this clause |
| AOS-008-AC03 | Sandbox failure means task FAIL/DENY, not unconfined fallback. | AOS-008-S1, AOS-008-S2, AOS-008-S3; owning files/interfaces above | AOS-008-TC01, AOS-008-TC02, AOS-008-TC03, AOS-008-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-008-S1](../cursor/prompts/AOS-008-S1.md) | AOS-004, AOS-007 | Concrete Linux Docker profiles and capability probe; non-root/read-only root/caps/process/resource ceilings, explicit mount containment. | AOS-008-TC01; command/report/exit, immutable evidence and diff |
| [AOS-008-S2](../cursor/prompts/AOS-008-S2.md) | AOS-008-S1 | Default-deny egress gateway/pinned destination and separate verifier/reader profiles; fail closed on startup/enforcement gaps. | AOS-008-TC02; command/report/exit, immutable evidence and diff |
| [AOS-008-S3](../cursor/prompts/AOS-008-S3.md) | AOS-008-S2 | Effective in-sandbox filesystem/network/credential/process attacks and cleanup/conformance report on actual OS. | AOS-008-TC01, AOS-008-TC02, AOS-008-TC03, AOS-008-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-008-TC01 | security | `tests/integration/test_aos_008.py::test_mount_symlink_proc_escape` | Synthetic host credential/parent/proc/device/hardlink targets blocked; no privileged container or docker socket. |
| AOS-008-TC02 | security | `tests/integration/test_aos_008.py::test_network_gateway_escape` | Direct socket/DNS/private/localhost/metadata attempts denied where profile forbids; allowed channel cannot become arbitrary proxy. |
| AOS-008-TC03 | live | `tests/integration/test_aos_008.py::test_effective_os_resource_limits` | Real host process namespace/UID/cgroup/mount/egress probes match manifest and enforce caps; unsupported feature is not PASS. |
| AOS-008-TC04 | chaos | `tests/integration/test_aos_008.py::test_sandbox_failure_cleanup` | Startup failure refuses unconfined fallback; orphan process cleanup uses identity and preserves unrelated workspace. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_008.py --junitxml=evidence/AOS-008.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

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
