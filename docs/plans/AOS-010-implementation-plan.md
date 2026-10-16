# AOS-010 — Hardened Claude Code worker adapter and hostile-repository tests: implementation plan

**Release:** R1. **Format:** full; shared design supplies cross-component detail. **Implementation:** IN_PROGRESS. **Tests:** PARTIAL; live CLI conformance pending. **Depends on:** AOS-004, AOS-008, AOS-009. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](../design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](../design/02-DATABASE-AND-MIGRATIONS.md), [security](../design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](../design/04-API-AND-USER-FLOWS.md), [decisions](../design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](../testing/TEST_EXECUTION.md) and [source spec](../specification/specs/AOS-010.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

One official Claude Code worker can perform a bounded, authorized code task without executing hostile repository-provided hooks, MCP servers, or plugin initialization.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/brokers/harness/claude.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/brokers/harness/event_parser.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/brokers/harness/process_runner.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/sandbox/native_tool_gateway.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/memory/context.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `ClaudeCodeAdapter.validate/start/events/observe/cancel/collect(job)`
- `CliProfileProbe.inspect(binary_ref, auth_handle, effective_config) -> CompatibilityManifest`
- `NativeToolGateway.execute(reviewed_request, scope, deadline) -> ToolReceipt`

**Migration ownership:** Adapter/version/profile/auth-mode/consent metadata; no token serialization or credential table.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-010-F01 | Inventory and validate any existing `claude-code-worker` skill. Pin Claude CLI version and auto-updater policy; probe `claude auth status` without extracting credentials. | AOS-010-S1, AOS-010-S2, AOS-010-S3; owning files/interfaces above | AOS-010-TC01, AOS-010-TC02, AOS-010-TC03, AOS-010-TC04; parameterize every condition in this clause |
| AOS-010-F02 | Implement subscription-compatible startup profiles. Test `--safe-mode` for disabling project customizations; it may ignore `CLAUDE.md`, so trusted context enters via documented prompt-file interface. Evaluate `--restricted` against the pinned build and explicit tool list; fallback to controlled `--setting-sources`, `--settings`, `--strict-mcp-config` only if behavior proven. `--bare` is API-only; do not imply subscription access. | AOS-010-S1, AOS-010-S2, AOS-010-S3; owning files/interfaces above | AOS-010-TC01, AOS-010-TC02, AOS-010-TC03, AOS-010-TC04; parameterize every condition in this clause |
| AOS-010-F03 | Use dedicated Claude config directory owned by user; worker sees only scope-necessary CLI state; sandbox-protect from repo contents. Explicit permission mode, no interactive prompt expectation, max turns/wall time, runtime cancel/status semantics. | AOS-010-S1, AOS-010-S2, AOS-010-S3; owning files/interfaces above | AOS-010-TC01, AOS-010-TC02, AOS-010-TC03, AOS-010-TC04; parameterize every condition in this clause |
| AOS-010-F04 | Parse versioned streamed JSON defensively; normalize events; fail closed on unknown event/privilege request or missing auth. Disable auto-execution from `.claude/`, `.mcp.json` and `.claude/settings.json` on test fixture. | AOS-010-S1, AOS-010-S2, AOS-010-S3; owning files/interfaces above | AOS-010-TC01, AOS-010-TC02, AOS-010-TC03, AOS-010-TC04; parameterize every condition in this clause |
| AOS-010-AC01 | Malicious `SessionStart` and `PreToolUse` hooks and MCP definitions with exfil sentinel never execute. | AOS-010-S1, AOS-010-S2, AOS-010-S3; owning files/interfaces above | AOS-010-TC01, AOS-010-TC02, AOS-010-TC03, AOS-010-TC04; parameterize every condition in this clause |
| AOS-010-AC02 | Safe-mode context comes through approved prompt file, not ignored workspace `CLAUDE.md`; scope of safe/restricted modes confirmed against installed CLI. | AOS-010-S1, AOS-010-S2, AOS-010-S3; owning files/interfaces above | AOS-010-TC01, AOS-010-TC02, AOS-010-TC03, AOS-010-TC04; parameterize every condition in this clause |
| AOS-010-AC03 | No-tools mode cannot call shell; Build profile explicitly permits bounded Bash inside sandbox; auth-required and quota errors handled without retry storm. | AOS-010-S1, AOS-010-S2, AOS-010-S3; owning files/interfaces above | AOS-010-TC01, AOS-010-TC02, AOS-010-TC03, AOS-010-TC04; parameterize every condition in this clause |
| AOS-010-AC04 | Cancel/timeout produces correct status; structured-output schema fixture tests cover partial/truncated JSON. | AOS-010-S1, AOS-010-S2, AOS-010-S3; owning files/interfaces above | AOS-010-TC01, AOS-010-TC02, AOS-010-TC03, AOS-010-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-010-S1](../cursor/prompts/AOS-010-S1.md) | AOS-004, AOS-008, AOS-009 | Inspect original skill, pin/probe official CLI/auth/config/profile semantics and sanitized event fixture parser; no live auth provisioning. | AOS-010-TC01; command/report/exit, immutable evidence and diff |
| [AOS-010-S2](../cursor/prompts/AOS-010-S2.md) | AOS-010-S1 | Bounded process lifecycle/context-file launch with edited workspace and tested credential/tool separation; shell-tier spike remains explicit. | AOS-010-TC02; command/report/exit, immutable evidence and diff |
| [AOS-010-S3](../cursor/prompts/AOS-010-S3.md) | AOS-010-S2 | Hostile hooks/MCP/config, silent timeout/cancel/partial JSON fixtures plus separately consented synthetic live compatibility smoke. | AOS-010-TC01, AOS-010-TC02, AOS-010-TC03, AOS-010-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-010-TC01 | contract | `tests/integration/test_aos_010.py::test_claude_json_errors` | Sanitized success/auth/quota/truncated/malformed/unknown state-bearing events normalize or fail safely; candidate is never kernel completion. |
| AOS-010-TC02 | security | `tests/integration/test_aos_010.py::test_hostile_repo_configs` | Malicious SessionStart/PreToolUse/settings/MCP sentinels never run; inherited/managed unexpected configuration refuses certification. |
| AOS-010-TC03 | live | `tests/integration/test_aos_010.py::test_claude_modes_auth_tool_isolation` | Exact CLI/auth/profile combination supports scoped task/context; synthetic credential outside tool scope unreadable; enabled Bash tier requires OS gateway proof. |
| AOS-010-TC04 | chaos | `tests/integration/test_aos_010.py::test_claude_silent_timeout_cancel` | Watchdog fires even with no stdout, bounded process group shutdown reported accurately and lost start receipt reconciled. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_010.py --junitxml=evidence/AOS-010.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

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

## Observed local implementation progress

The pinned stream parser and process supervisor are implemented in
`brokers/harness/event_parser.py` and `process_runner.py`. Synthetic checks cover
quota/auth failures, unknown/malformed/truncated streams, unauthorized tool
capabilities, terminal/exit consistency, output bounds, silent timeout,
cancellation after pipe EOF, and terminating a child retaining a pipe. Results
remain unaccepted candidates; no stream text completes a kernel task. This
supervisor requires an approved isolated launch and is not an OS boundary.

No provider request is made by these tests. Native profile, dedicated auth
principal, tool gateway, malicious repository configuration and successful live
conformance remain pending; synthetic PASS does not certify those capabilities.

Metadata preflight is implemented in `brokers/harness/cli_profile.py`, with frozen
inspection-only contracts and `panestria native inspect`. It inventories the
original skill as data, pins executable bytes/version, bounds both metadata pipes
and the total deadline, discards account/credential fields, and refuses unsafe
or changed config references. Installed CLI metadata and empty private-directory
checks are observed; these do not certify startup profiles. See [native
preflight](../testing/NATIVE_PREFLIGHT.md) for commands and remaining obligations.

The reviewed command gateway component is implemented in
`sandbox/native_tool_gateway.py`, with strict input/scope contracts and a
digest-checking container launcher. It snapshots reviewed scripts and data
outside candidates, requires controller dispatch authority, enforces read/edit
profiles and observes cancellation/deadlines/authority loss. The authority seam
is tested synthetically; seven actual Docker cases exercise OS isolation and
digest rechecks. See [the gateway runbook](../testing/NATIVE_TOOL_GATEWAY.md).
Durable controller/outbox wiring, native transport, allowed MCP/parser bindings,
startup/hostile-repository conformance and authenticated generation/merge remain
pending. No user-facing native profile is enabled by this component.


The internal [registered-check MCP session](../design/23-NATIVE-REGISTERED-CHECK-PROTOCOL.md)
adds closed lifecycle/tool schemas, fixed references, replay prevention, bounded
counts and cancellation signals. Its 48 hermetic checks plus 74 related existing
checks pass at 309bfa5. The callback is explicitly a controller fixture. No native
profile/service is enabled; durable current-scope authority, private transport,
registry access, finalized report proof and actual CLI/tool conformance remain
pending. It is not a replacement for those boundaries or full AOS-010 cases.

The [private transport](../design/24-NATIVE-CHECK-PRIVATE-TRANSPORT.md) adds a
one-connection Linux Unix socket and subprocess stdio relay. At c5818c0, 169
targeted checks passed (47 new transport/dispatch, 48 protocol, 74 existing;
seven live gateway cases excluded). Actual pipes exercise deadlines, cancellation,
identity, output pressure and owned cleanup. Callbacks are labeled fixtures, not
durable execution authority or native CLI qualification. Profiles remain disabled
until the current lease/policy/registry/protected-report binding and actual native
MCP conformance are verified. Evidence: evidence/native-command-transport-2026-10-15.

The [durable one-check controller](../design/25-NATIVE-CHECK-DURABLE-BINDING.md)
connects an exact required read command to current policy/lease, deterministic
PostgreSQL invocation fencing, the existing Docker gateway and protected report
readback. At ed0d63c, 139 checks pass: 27 new actual PG/Docker/stdio, 17 existing
invocation and 95 protocol/transport. Concurrent/reconstructed controllers do not
rerun the command. Real running-container cancellation and lease revocation remove
only the exact test-owned container. Nonzero check exits remain failed checks;
no receipt completes a task or creates approval. Source-bound report and earlier
failed development observations: evidence/native-check-authority-2026-10-15.
Actual native MCP/settings/parser/hostile-project conformance remains pending;
this component does not enable or certify a native shell tier or full G1 case.

The [separate PUBLIC synthetic MCP profile](../design/26-NATIVE-MCP-READ-PROFILE.md)
uses the existing pinned Claude subscription principal with restricted/explicit
settings and only the private registered-check tool. At f67b647, 172 targeted
checks and two actual native checks pass, including empty-auth zero-turn hostile
configuration startup and an actual subscription call through PostgreSQL, Docker
and protected report. Six earlier native rejections stay recorded as failures.
No credentials were read/copied, paid SDK or provider fallback used. Native cash
is unknown; the budget flag is an estimate. Bare mode was excluded because it
skips subscription credentials; safe-mode no-tool proposals remain unchanged.
No general owner task/native shell profile or full AOS010/G1/R3 case is enabled
or promoted. Evidence and limits: evidence/native-mcp-profile-2026-10-15.

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
