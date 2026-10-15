# Native tool gateway component

This task implements the container dispatch boundary for AOS-010-S2. It is a
library component, with no API route, Claude MCP server, or enabled native worker
profile. R1 remains IN_PROGRESS and G1 NOT_RUN. A working component does not
certify Claude's startup flags, hostile hooks, authentication, or a verified
end-to-end Build/merge.

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

This PR does **not** supply the durable controller implementation. The test
authority is deliberately synthetic and only exercises the interface. Actual
kernel/outbox wiring, transaction/restart/replay tests and permit admission from
the current policy are still required before any user-facing native execution
is enabled. There is no new task store, database schema, credential store or
in-memory production replay mechanism.

## Container boundary and receipts

The gateway opens a regular, owner-controlled, non-writable-by-others reviewed
script with no final symlink following, checks its digest and size, and snapshots
only those bytes. Scripts inside the candidate root, symlinks, hardlinks and
changed bytes are refused. It stages that snapshot and the bounded request in a
private host directory outside the candidate. Individual files are mounted
read-only; no host bundle, auth directory, environment file or credential is
mounted. Data-file content does not appear in command arguments.

The trusted launcher verifies both digests again inside the container before
executing the reviewed script. The script receives `PANESTRIA_TOOL_REQUEST` as
data. Its own argv contains no worker arguments. The gateway's registry is
separate from the independent verifier's registry, preserving that trust
boundary.

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

## Review and test

On `task/r1-native-tool-gateway`, install the frozen environment and run the
provider-free contract/dispatch checks:

```bash
uv sync --frozen --group dev
uv run --frozen pytest tests/integration/test_native_tool_gateway.py -m 'not live' -q
```

The expected result is 46 PASS, with seven Docker cases deselected. These tests
cover request/registry/access bindings, every scope field, unregistered tools,
script mutation/links/permissions, workspace and deadline guards, cancellation
during claim, a stalled authority check, unknown runtime outcomes, and cleanup
of the private staging files. The synthetic authority is not durability proof.

The OS tests require Linux, Docker access and the exact image already available:

```bash
docker pull python@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9
uv run --frozen pytest tests/integration/test_native_tool_gateway.py -m live -q
```

The expected result is seven PASS. Two cases exercise read-only/scoped-edit
access, host-secret absence, protected runtime mounts and network denial; two
mutate staged script/request bytes and prove the launcher refuses execution;
three prove actual worker removal after revocation, cancellation and deadline.
Each uses an isolated candidate and only its exact owned container. These tests
make no native Claude inference or paid SDK request, require no Claude login,
and do not use the owner's R0 review database.

## Remaining native integration

- Implement and test the durable kernel/controller authority against disposable
  PostgreSQL, including one-use claims, current leases, policy changes and lost
  dispatch replies. Connect protected receipt/artifact publication.
- Expose only the reviewed references through a versioned native tool transport;
  pin the exact MCP server/tool binding in the native profile/parser. The current
  parser continues rejecting MCP servers until that conformance work is done.
- Finish the native adapter, approved context-file launch and hostile
  hook/settings/MCP fixtures. A gateway test does not establish that native Bash
  has been safely routed through it.
- After the owner completes the private Claude profile sign-in and inference is
  available, run the separately authorized synthetic native compatibility and
  generation/verification/approval/merge tests. Preserve the spending and provider
  boundaries; no automatic credential substitution or quota retry loop.
- Finish review/demo/runbooks, remaining R1 clause coverage and one-candidate G1
  evaluation before proposing R1 completion.
