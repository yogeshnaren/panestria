# AOS-008 — Sandbox profiles, mount validation and enforceable outbound controls: implementation plan

**Release:** R1. **Format:** full; shared design supplies cross-component detail. **Implementation:** IN_PROGRESS (component evidence below). **Tests:** partial components observed; item/release acceptance NOT_RUN. **Depends on:** AOS-004, AOS-007. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

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
| AOS-008-TC03 | live | `tests/integration/test_aos_008.py::test_os_effective_uid_mounts_egress_and_limits` | Real host process namespace/UID/cgroup/mount/egress probes match manifest and enforce caps; unsupported feature is not PASS. |
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

## Revision 3 extension — MVP-X09, delivered in R3

The [active personal-platform contract](../specification/architecture/05-PERSONAL-PLATFORM-REVISION-3.md#mvp-x09) adds **Explicit connection grants and secret boundary**. Original parent scope and historical results remain intact. These new slices deliver in **R3**, even when the parent AOS item originally ships in R1; they do not reopen historical G0 acceptance or fabricate G1 evidence. Inspect the current repository before choosing exact new files/migration revisions.

| Slice | Concrete outcome, narrowed to about one developer-day | Prerequisites |
| --- | --- | --- |
| AOS-008-S4 | Implement explicit connection manifests and broker enforcement using existing policy. | AOS-008-S3, AOS-009-S3, AOS-010-S3 |
| AOS-008-S5 | Implement revocation/secret-boundary checks and scoped onboarding integration. | AOS-008-S4, AOS-028-S3 |

Use the [revision-3 slice handoff](../cursor/prompts/MVP-REV3-SLICE.md) with the selected manifest entry. File ownership candidates are in implementation-slices.json; record an ADR for a material change. Existing shared transaction/security/API requirements still apply.

| Added case | Lane | Required passing behavior |
| --- | --- | --- |
| AOS-008-TC05 | security | Owner/project/version-bound connection grants independently constrain read/write/send/delete/spend, paths, origins, accounts, classifications, budgets and expiry. |
| AOS-008-TC06 | security | Workers and connectors cannot inherit broad homes, provider credential directories, browser logins, Docker sockets or secret-bearing environment; synthetic secret/egress probes prove the effective envelope. |
| AOS-008-TC07 | chaos | Revocation/expiry is rechecked before queued/future effects and invalidates stale approval; already-started effects are reconciled honestly. |
| AOS-008-TC08 | e2e | Connection setup shows exact grants, conformance and revoke state; adding a client or folder cannot import its chats or enable uncertified tools. |

These nodes and scenarios are planned, not observed tests. Register real assertion/node/lane/evidence mappings while implementing; missing required evidence blocks G3. Rollout begins disabled, uses synthetic content until its boundary is certified, stops admissions on failure and preserves audit/receipts. R4-R7 work is not authorized by completing this extension.

## Connection declaration and owner-review component (2026-10-16)

[The versioned grant review ledger](../design/38-CONNECTION-GRANT-REVIEWS.md) is
implemented as an additive same-PostgreSQL resource ledger using the existing
Actor/project/task/policy and caller transaction boundaries. Closed manifests
name exact connector/config/account/root/origin/action/class/budget/expiry scope.
Owner review binds the exact digest and expected version; approval atomically
creates an immutable decision/revision and monotonic pointer. Historical retries
never renew eligibility. Policy changes are displayed as stale; revocation and
expiry preserve history. All views remain DECLARATION_ONLY and conformance stays
UNVERIFIED, including when the declaration includes a conformance reference.

At b41ee66, 81 focused contract/real PostgreSQL/policy/setup checks pass. Actual
backup/restore, post-restore revoke/counter continuation, empty downgrade/reapply,
audit downgrade refusal, rollback, immutable constraints and concurrent owner/
cross-project races are included. Source-bound evidence and earlier failed
observations are retained in evidence/connection-reviews-2026-10-16. The broader
13e4ff2 run passed 186 checks and exposed one old restore-test guard expectation;
the corrected final checks preserve the unchanged-head/setup assertions.

This is the durable declaration/review part of AOS-008-S4, not full TC05–TC08.
The actual GrantBroker/capability/root/account registry, current lease/budget and
approval bindings, future-effect revocation/reconciliation, narrow secret/OS
boundary and onboarding UI remain required. No connector, credential, runtime
permission, network/provider call or release is enabled by these declarations.

## Private native egress relay prerequisite (2026-10-16)

[The standalone private relay](../design/39-NATIVE-PRIVATE-PROXY-RELAY.md) provides
bounded container-loopback transport to one pinned private host CONNECT socket.
At `c6fa589`, 74 focused checks pass, including four actual Docker envelope/
synthetic-secret/egress/replacement cases; one actual public TLS HEAD also passes
without auth or inference. Failed earlier timing assertions remain in the
source-bound evidence. The worker no-network profile is unchanged.

This is a transport prerequisite, not completed native auth-process containment
or full AOS-008/AOS-010 conformance. Production native launcher/binary/profile/
credential/MCP integration, current policy/grant/lease/budget admission and actual
hostile configuration/secret/revocation proofs remain required. No release gate
or user task is enabled by this component.

## Credential-free native bootstrap prerequisite (2026-10-16)

[NativeBootstrap](../design/40-NATIVE-OFFLINE-BOOTSTRAP.md) now checks the exact
pinned version/help within the existing restricted-offline DockerSandbox and
inherited AF_INET/AF_INET6-denying seccomp filter. It accepts no task prompt, auth
configuration, environment, command or network choice. A verified executable
snapshot, empty read-only workspace and trusted launcher are the only binds.
At `1ae3209`, 63 focused checks pass (32 new, including 11 actual Docker cases
with a synthetic native fixture). One actual pinned native version/help case
also passes, with no login, inference, gateway or paid call.

The result stays BOOTSTRAP_ONLY. Authentication, connected native container/
proxy/registered-MCP integration, credential-boundary/current-authority checks
and full AOS-008/AOS-010 conformance remain required. Existing host pilot profiles
are unchanged; no G1/G2/G3 gate is promoted. Source-bound evidence and earlier
uncommitted prototype observations are preserved separately.

## Lost create-response cleanup component (2026-10-16)

[Launch reconciliation](../design/41-SANDBOX-CREATE-RECONCILIATION.md) fixes an
actual stopped-container leak demonstrated with an injected lost Docker reply.
Unique launch/profile/image/attempt/name/purpose/ID checks preserve unrelated or
ambiguous resources, including a foreign container sharing the attempt/name.
A missing observation remains NOT_OBSERVED, and lookup/removal uncertainty remains
UNCONFIRMED. No result grants retry or returns a successful sandbox receipt.

At clean `4abb61d`, 115 focused default checks (29 new), seven actual OS probes
and actual pinned credential-free version/help pass. Original failed evidence
and the subsequent corrected observations are retained. The catalog's TC03
primary node now names the actual UID/mount/egress test; its resource-pressure
parameters remain required alongside it. TC04 now correctly requires live OS
evidence to match the existing test annotation. Both catalog statuses stay
NOT_RUN. The launch reference is still in memory; durable pre-dispatch intent
and controller-death reconciliation are required before full TC04/G1 acceptance.

## Durable registered-tool launch component (2026-10-16)

[The same-PostgreSQL launch journal](../design/42-DURABLE-SANDBOX-LAUNCH.md) adds
one-use immutable intent before Docker create on the actual registered-check
controller path. Intent/event commits share the caller transaction; lost commit
acknowledgment admits no create. An actual shorter-deadline profile is witnessed
without widening any other cap. Fresh authority is checked before startup.
Reconstruction uses the scoped stored reference, and historical cleanup keeps
unknown work fenced without manufacturing task/check/approval success.

Clean `ec9a43f` passes170 focused checks (46 new), including six actual controller
SIGKILL cases, two admission faults, actual schema/downgrade/backup/restore and
existing research/setup/native-tool paths. Source-bound evidence retains earlier
failed observations. Head28/schema1078 lines were generated from disposable
PostgreSQL. DBOS transaction/workflow/outbox documentation was rechecked in the
design. Existing R0 acceptance is preserved.

This covers one registered-tool recovery path. Other worker/verifier/private
control-stage lifecycle recovery, connected native auth/proxy/MCP, full grant/
lease/budget/capability enforcement and G1/G2/G3 evidence remain required.
No provider inference, credentials or paid API are used or enabled here.
