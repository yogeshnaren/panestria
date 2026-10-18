# Explicit bounded sandbox input transport

This prerequisite extends PR95's opaque input frame with a production runner
transport. It does not switch NativeToolGateway or its launcher to that transport;
the gateway's host temporary-stage crash gap remains open.

`SandboxProfile.stdin_mode` is either `closed` (default) or `native-frame-v1`.
Closed profiles omit the new field from their canonical hash, preserving their
historical identities. The explicit framed profile includes it and has a new
hash. Existing durable authority compares the whole approved profile, allowing
only a shorter remaining wall time. A matching new launch hash cannot widen an
old closed-input permit.

`DockerSandbox.run(..., input_frame=bytes)` requires the framed profile and
1–327705 bytes. A closed profile rejects any input. A framed profile rejects
missing, empty, nonbytes or oversized input before Docker or launch intent.
The runner bounds transport bytes; the trusted consumer remains responsible for
frame validation, expected digests and processing before execution. Queuing bytes
to an attach client alone does not prove that a script consumed them.

## Effective configuration and lifecycle

Before startup, inspect exact OpenStdin/AttachStdin/StdinOnce values for the
approved mode, TTY false and both output streams captured. Preserve all existing
network, identity, mount, resource, logging and one-use launch/reconciliation
checks. Closed mode explicitly gives the host attach process DEVNULL stdin.
Framed mode starts it with interactive stdin and a bounded byte payload.

A single selector multiplexes nonblocking input and output in chunks of at most
16384 bytes. Closing the input pipe after the last queued byte supplies EOF.
There is no writer thread or buffered input flush. Cancellation, wall deadline,
output pressure, EPIPE, partial pipe registration and worker/client exit close
owned descriptors and preserve exact-container cleanup.

Output EOF is insufficient evidence that a worker stopped. A dead attach client
while its worker is still running causes refusal and termination. Completion also
requires a successful client and an actual `exited` container state; a never-started
container's initial ExitCode0 cannot pass. Failed attachment diagnostics are
suppressed because they can contain host paths. The runner's existing Docker
inspection/cleanup timeouts still apply: the wall cap is not a certified
end-to-end recovery latency guarantee.

## Evidence

Clean `c1963e29a2577e14b71f6aa9aad0303abacf930b` passes 211 focused checks in
75.40s, with 20 existing live cases excluded. Ruff, mypy (198 files), 11 import
contracts, the secret scan and source diff check pass. Of 38 new cases, 21 cover
contract/real OS pipes, 16 use actual Docker resources and one exercises actual
PostgreSQL authority. See `evidence/sandbox-framed-stdin-2026-10-18` for source
hashes, raw results, earlier passing source revisions and explicit fixture limits.

The actual maximum-frame case observes opaque byte digests/EOF and inherited
seccomp2, AF_INET/AF_INET6 denial, nonroot UID, zero effective capabilities and
NoNewPrivs. Other cases cover blocked readers, output/memory pressure, closed
output, early exit, actual Running before cancellation/attach-client kill and
five effective-config faults before start. Two unstarted-container cases inject
a client program returning0/42; they are not actual Docker start-failure
certificates. Small OS-pipe tests explicitly substitute the container-state seam.
Existing six direct-runner controller SIGKILL regressions retain that scope.

## Next integration

Version the reviewed-command execution interface and re-review all concrete
scripts. The demo's `apply.py` currently reads `/runtime/native-request.json` and
must be migrated deliberately; virtual `__file__` alone does not solve that.
Bind framed mode to new permits/registry/runtime certificates, stream only after
fresh one-use claim and durable intent, and use the authority-bound factory in
every actual durable controller. Remove host staging with no silent fallback.
Then validate actual gateway/controller-death recovery with PostgreSQL and Docker.

No vendor CLI, model, provider, SDK, authentication, new credentials/images or
owner service was used here. No full AOS003/AOS008/AOS010, G1/G2/G3 or R3 owner
acceptance follows from this transport component.
## Exit observation follow-up (2026-10-18)

[Design48](48-ATTACHMENT-EXIT-ORDERING.md) fixes a real inspect/client-poll
ordering race exposed by PR99 CI. A fresh worker-state inspection follows the
observed attachment exit; all original exit/input/status/cleanup refusal guards
remain. Original failed CI and deterministic child reproductions are preserved.
This later component evidence does not rewrite or relabel this document's
original source qualification or promote a runtime/release certificate.
