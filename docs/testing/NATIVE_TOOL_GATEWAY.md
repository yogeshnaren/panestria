# Native tool gateway: current boundary and testing

Use a review checkout of current `main`, recording `git rev-parse HEAD` and
`git status --short`. The old `task/r1-native-tool-gateway` branch and original
test counts describe an earlier implementation. This guide covers registered
tool dispatch and recovery components. R1 remains IN_PROGRESS; G1/G2/G3 and the
R3 owner trial are not accepted. These checks do not certify Claude Code,
Cursor, all their agents or arbitrary tools. Local Ask still disables Build/tools.

## Input and authority

`ToolRequest` contains only an invocation UUID, a reviewed command reference and
a canonical JSON object encoded in `payload_json`. Payloads are limited to
32 KiB and depth 16; duplicate keys, nonfinite numbers, malformed JSON and
non-object roots are refused. The complete request envelope is capped at
64 KiB, including escaping. Arbitrary argv, environment, mounts, authority,
workspace and deadline fields are forbidden in worker input.

The trusted controller constructs `NativeCommandRegistry` and `ToolPermit`.
The latter binds the request and registry digests, owner/project/task/attempt,
lease epoch, contract digest, policy reference, exact workspace, sandbox profile
and absolute monotonic deadline. A read command requires a read-only workspace;
an edit command requires the scoped editable profile. Workers cannot register
commands or supply permits.

`ToolAuthority` is a required controller dependency, not an optional default or
a model-supplied boolean. Its `claim` must validate every permit binding and
commit a unique dispatch intent before returning. `check` must recheck current
scope, lease, contract, policy and cancellation. Neither method may grant
permission from worker text or CLI inspection metadata. Replays must be refused,
including after an unknown outcome. Both methods need bounded database/network
timeouts, and checks must be read-only and safe in a supervisor thread.

`DurableToolAuthority` now supplies committed one-use invocation claims and a
bound runner factory. That runner commits a launch intent before Docker create
and checks current authority again before start. `InvocationService` and
`SandboxLaunchService` use existing PostgreSQL transaction/event rules. Explicit
non-durable test authorities are component seams, not production admission or
proof that an account/connector is permitted. Recovery uses historical exact
identities; it does not mint another dispatch claim.

## Container boundary and receipts

The gateway opens a regular, owner-controlled, non-writable-by-others reviewed
script with no final symlink following, checks its digest and size, and snapshots
only those bytes. Scripts inside the candidate root, symlinks, hardlinks and
changed bytes are refused. The reviewed command has explicit `python-memory-v1`
execution; old execution/profile/registry hashes are not silently upgraded.
The gateway snapshots script/request bytes in bounded memory and sends a
versioned stdin frame. **No host input staging directory, dynamic script/request
bind mount or file-mode fallback exists.** The actual bind mounts are the
admitted workspace plus installed read-only launcher, frame parser and network
denial code. No broad home, auth directory, Docker socket or arbitrary host
environment is added by this gateway. Request data stays out of argv.

The launcher checks exact lengths, trusted digests and EOF before compiling the
script. `PANESTRIA_TOOL_REQUEST` supplies data; `__main__` has proper module
identity and a virtual `__file__`. Reopening that source file or the old
`/runtime/native-command.py` and `/runtime/native-request.json` is unsupported.
The gateway registry remains separate from the independent verifier registry.
Duplex transport drains output while sending input and closes input when done.
Client exit alone is insufficient: worker exit, complete input and attachment
state must agree. See [design45](../design/45-SANDBOX-FRAMED-STDIN.md),
[design46](../design/46-NATIVE-MEMORY-INPUT.md) and
[design48](../design/48-ATTACHMENT-EXIT-ORDERING.md).

`DockerSandbox` supplies the pinned image, effective configuration inspection,
nonroot UID, read-only root, dropped capabilities, process/memory/CPU/output
limits, network denial and cleanup by exact container identity. Editable tools
can change only the admitted candidate workspace; temporary container storage
is also available. A tool script must still validate its operation-specific
payload and paths. The component does not turn an arbitrary host shell command
or repository hook into a reviewed tool.

Authority is checked before execution, about every 100 ms while running, and
afterward. A failed check, caller cancellation or deadline sets the trusted
sandbox cancellation event. A stalled check is capped at 500 ms and yields an
unknown result; controller I/O timeouts must release its daemon check thread
and any associated connection. Docker daemon operations retain their existing
30-second timeouts, so this is not an absolute end-to-end termination bound.
The supplied profile's wall cap can be shorter than the overall deadline.

`ToolReceipt` contains request/scope/registry digests, a component outcome and
the observed sandbox receipt when available. `completed` means this reviewed
command exited zero while the authority checks passed. It is never a verifier
PASS, merge approval or kernel completion. A runtime exception or unconfirmed
termination yields `unknown`, even if cancellation/revocation also occurred;
the controller must retain the claim and reconcile rather than blindly retry.
Only a sandbox receipt proves observed process termination and cleanup. A
revoked invocation can leave candidate edits, which cannot be published without
the independent current-scope verifier and kernel approval gates.

Treat tool output and request content as private project data. The controller
must ingest them into its protected artifact path and enforce owner/project
access; neither belongs in generic diagnostics, analytics or cloud fallbacks.

## Run provider-free checks

Prerequisites: Linux, Docker access, frozen Python dependencies and the exact
worker/PostgreSQL images already cached. Inspection does not download images:

```bash
docker image inspect python@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9 >/dev/null
docker image inspect postgres@sha256:ca0bd484cb98bf4b24eb1010e73fb3fcbd6714d240fbc1a10eea5b7dbecb641d >/dev/null
```

Fixtures own disposable synthetic databases and exact containers. Reserve test
ports 55439/55440; do not run another fixture stack on the same port or substitute
an owner database URL. API/demo servers need not run. These commands use fixed
synthetic data, no Claude/Cursor login, inference, API keys or paid SDK calls.

First run contract and actual PostgreSQL claim/replay checks:

```bash
uv run --offline --frozen pytest tests/integration/test_native_tool_gateway.py tests/integration/test_invocations.py -m 'not live' -q --junitxml=/tmp/panestria-gateway-default.xml
```

Explicitly live-marked OS cases are excluded here. Default does not mean every
test is hermetic: invocation tests use real disposable PostgreSQL.

Then run these exact synthetic OS/recovery nodes:

```bash
uv run --offline --frozen pytest tests/integration/test_native_tool_gateway.py::test_actual_gateway_boundary tests/integration/test_native_tool_gateway.py::test_actual_launcher_rechecks_snapshot_before_executing_code tests/integration/test_invocations.py::test_real_gateway_uses_durable_claim_and_refuses_replay tests/integration/test_memory_gateway_crash.py -q --junitxml=/tmp/panestria-gateway-os.xml
```

Current parameterization yields 13 cases:

| Cases | Boundary |
| --- | --- |
| 2 read/edit | Actual container access, protected mounts, synthetic host-secret absence, virtual source identity, network denial and cleanup; authority is synthetic |
| 2 frame tamper | Changed script/request bytes refuse before executing the reviewed command |
| 1 durable dispatch | Actual PostgreSQL claim/container execution; repeating the claim is refused |
| 8 controller death | SIGKILL at claim/intent/create/running, each with/without lease release; historical exact recovery and no re-dispatch |

The crash module is not marked `live`: adding `-m live` to that combined command
would omit its eight cases. Do not replace it with every live test; other
modules have distinct login/provider/network/spending prerequisites. Preserve
actual XML, exit status and source identity. Failures/skips/errors remain visible;
counts alone cannot prove all required assertions ran.

## Recovery and result interpretation

`completed` is a registered command result, not independent verifier PASS, merge
approval, task completion or release acceptance. Candidate edits require current
independent final-tree checks and exact approved merge authority. UNKNOWN runtime
or cleanup outcomes retain the claim/exposure; they do not permit blind retry.
Docker operations retain 30-second limits, so this is not a hard end-to-end
shutdown guarantee. Failed attachment diagnostics do not become worker output.

After controller loss, a claimed pre-launch invocation is finished historically
as UNKNOWN; stored launches reconcile by their exact durable identity. The tests
preserve unrelated similarly labeled containers, task state and approvals. An
absent runtime or historical receipt cannot authorize another claim. Recovery
can retain edits or unknown exposure and cannot manufacture success or undo a
confirmed external effect.

Original observations remain source-bound in
[memory gateway evidence](../../evidence/native-memory-input-2026-10-18/report.json)
and [transport race evidence](../../evidence/attachment-exit-race-2026-10-18/report.json),
including earlier failures. They are not relabeled as current release certificates.

## Remaining native and connection integration

Actual connection GrantBroker/account/capability/root/source-purpose/current
policy/lease/budget/approval and future-effect revocation integration remains
unfinished. A supplied conformance hash or approved declaration conveys no
runtime connector authority. Contained native auth/proxy/MCP and hostile startup
configuration need actual conformance before capability enablement. A tool
gateway does not prove arbitrary native Bash has been routed through it.

The existing fixed public native proposal/demo evidence is a separate narrow
profile. It does not orchestrate Claude chat, every Cursor agent or arbitrary
repositories. Other worker/verifier/setup lifecycles, full runtime/API/UI,
same-candidate G1/G2/G3 evaluation and the actual 14-day owner trial remain
required. This runbook starts no live provider tests and changes no credentials,
services, owner databases or accepted gates.

The [runbook command report](../../evidence/gateway-runbook-2026-10-18/report.json)
records62 default passes/8 live excluded8.32s at clean e9487aa, then13 actual
synthetic OS passes18.23s with only this guide edited. Runtime/tests stayed
identical to e9487aa. Both raw XML files and that source distinction are retained;
this does not qualify a new runtime or release candidate.
