# Bounded native Bash Build

The Build backend now connects a distinct Claude Code MCP tool to the existing
durable invocation and secret-free Docker boundary. `ScopedBashController`
initializes a disposable workspace from a protected source snapshot. Its job
permits one Bash script (16 KiB input, at most 30 seconds, 8 KiB output). Built-in
Claude tools remain disabled; the model cannot choose credentials, a host path,
scope, policy, lease, executable profile or verifier registry.

The reviewed bridge runs Bash only inside the non-root container. Root is
read-only, network-none and inherited seccomp deny IPv4/IPv6 sockets across exec,
and only the attempt workspace is writable. No `.git`, owner home, Docker socket,
database credential or provider credential is mounted. Shell startup files and
inherited environment are disabled. One-use dispatch and launch records commit
before Docker create/start. Reopening MCP or rebuilding the controller does not
replay the job, including after an unknown result.

`verify_for_review` is the trusted controller continuation. It checks the current
scope, policy, lease, protected base and confirmed tool receipt, captures stopped
worker bytes as Git objects, independently verifies a frozen snapshot, and
publishes the resulting evidence. Failed required checks mark the task failed.
Passing checks create an exact merge approval request. The method never approves
or merges. Existing protected Git CAS/outbox handling applies after a real owner
decision. Worker-produced `.git`, secrets, links and special files are rejected
before import; the importer never runs worker Git hooks, filters or tests.

## Run the qualification

Use a disposable checkout with frozen dev dependencies and the existing pinned
worker image prepared by `panestria.cli.review_demo.prepare_worker_image`.
The database fixture owns only its temporary container on port 55439; keep that
port available and do not run another R1 database suite concurrently.

```bash
uv run --frozen pytest tests/unit/test_bash_protocol.py \
  tests/unit/test_native_command_protocol.py tests/unit/test_native_mcp_profile.py \
  tests/integration/test_scoped_bash.py \
  tests/integration/test_registered_check_authority.py \
  tests/integration/test_build_snapshot.py \
  tests/integration/test_durable_registered_admission.py -m 'not live' -q
```

This provider-free run includes actual PG/Docker/Bash and protected Git. Expect
the valid two-file job to reach `WAITING_APPROVAL`; a wrong digest is rejected;
the scripted synthetic test owner approves the exact effect; only then does Git
advance and the task complete. A worker saying `WORKER_TESTS_PASS` with incorrect
code fails the independent check and produces no merge request.

The separately opt-in native case uses pinned Claude Code 2.1.273 and the existing
private authenticated profile at `~/.panestria-native-claude`. It sends only the
fixed PUBLIC fixture task and performs one bounded subscription call:

```bash
uv run --frozen pytest tests/integration/test_scoped_bash.py -m live -q
```

Expect the same two-file outcome, separate checks, wrong-digest rejection and
exact scripted approval flow. It also checks that hostile SessionStart,
PreToolUse, repository MCP and CLAUDE.md customizations remain inert. No SDK key,
OpenAI call, paid overflow or provider fallback is used. Subscription cash/quota
precision remains unknown. Do not automatically retry an unavailable native run.

## Scope and next integration

The [source-bound report](../../evidence/r1-native-bash-build-2026-10-18/report.json)
records passing checks and preserves the initial failed native compatibility run.
The read-check profile remains separate and read-only.

The native case is an explicitly authorized operator conformance exercise. The
local Bash controller grants no cloud export permission. A generic owner-project
launcher must still bind independently admitted PUBLIC context, its runtime
certificate, durable native-call intent, current policy and cancellation. This
PR does not expose an unchecked generic cloud launch API or change the existing
fixed proposal-demo website. One-command V1 returns metadata, so it does not
claim an interactive debugging loop or private-repository cloud support.

The test owner is scripted. Human review and full cumulative G1 evaluation remain
separate. AOS-016-TC04 is owner-deferred; neither that test nor G1/G3 is marked PASS.
