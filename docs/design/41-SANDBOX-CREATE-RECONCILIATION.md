# Reconcile a sandbox create whose reply was lost

An actual owned Docker create with an injected lost reply demonstrates a gap in
the previous runner: the container exists, but the exception happens before its
ID reaches the cleanup block. The reproduction removes that exact test fixture
after observing the leak. No candidate process starts during this fault.

Give every create a distinct UUID4 launch label in addition to the existing
attempt identity and purpose. Bind an immutable controller reference to that
launch, attempt, profile hash and observed pinned image ID. Check the exact
container ID/name/image/labels before execution and again before cleanup.

On an error or malformed/unowned returned ID, look up only the launch nonce. One
exact matching owned resource can be removed and its absence rechecked. Missing,
multiple, mismatched, unreachable and unconfirmed removal observations do not
count as cleanup success. A foreign container with the same attempt/name remains
untouched. No global prune, broad attempt cleanup or process start/retry occurs.

`SandboxLaunchUncertain` exposes the controller reference and truthful REMOVED,
NOT_OBSERVED or UNCONFIRMED observation with a static exception code. An unknown
create never returns a successful sandbox receipt, even if its observed resource
was removed. A trusted controller can recheck the reference later. No worker or
public API may mint reconciliation authority.

The nonce remains in memory here. Full process-death recovery still needs the
durable controller to persist its launch intent before dispatch and reconcile
external outcomes. No new parallel task store is introduced. NOT_OBSERVED does
not prove a delayed create cannot subsequently arrive, authorize a retry or pass
AOS-008-TC04/G1. Preserve failed observations and test exact-owned cleanup with
real Docker plus explicitly injected lost/malformed replies and identity faults.

## Observed validation

At clean `4abb61d`, 115 focused default checks pass (29 new), plus seven actual
OS boundary/resource/cleanup probes and one pinned native version/help case
(two credential-free metadata commands). The original leaked-container
reproduction, injected lookup/removal/late-create failures, and an earlier
zero-test command selecting a stale planned node are retained separately in
`evidence/sandbox-create-reconciliation-2026-10-16`. The actual nodes passed;
the stale plan/catalog primary name and startup-cleanup live-required annotation
are aligned without changing NOT_RUN release status. Native task/connected auth,
durable intent/controller-death recovery and G1/G2/G3 remain pending.
