# Current queue authority for final integration

This follows [the editing worker guard](105-BACKGROUND-WORKER-AUTHORITY.md)
(PR195). It intersects the existing canonical background run with the trusted
final node, without adding a task state, scheduler, schema or model invocation.

The controller builds the final ToolScope from the actual leased task/contract
and passes its trusted WorkerAuthority to BuildIntegrator. The same kernel guard
accepts only the exact held editing or trusted-integrator claim in that queue's
current plan. Native and integration invocation configuration hashes include the
run/scope intersection; ordinary foreground invocation bytes stay compatible.
No API or worker response can provide this hook or choose another claim.

Final admission/claim/input reconstruction checks the queue/run intersection.
Before further source assembly, each independent acceptance check, evidence
publication and merge-review creation, current withdrawal/goal/plan/account-link/
policy/billing/quota/foreground/original-deadline conditions are checked again.
`verify_build` takes an optional trusted `before_check` callback, independent of
check specifications and reports. It cannot turn an unknown/failed check into a
PASS. Foreground verification keeps its existing callback-free behavior.

After actual Git/check return, the existing historical physical receipt may be
recorded even if the queue was withdrawn. Publication still requires current
authority. A historical RETURNED invocation is not candidate acceptance,
approval, claim release or permission to redispatch. For denial before any
integration invocation, canonical plan cancellation may release the final claim
only through its immutable NO_DISPATCH proof; executed/unconfirmed work stays
held until existing explicit reconciliation proves safe release.

An already running local verifier retains its bounded deadline; this callback
does not claim immediate physical interruption. It fences the next check and
publication. A provider identity is not atomically locked by metadata, and local
integration needs no extra login probe or cloud call. Existing exact owner merge
consent remains separate. This does not invalidate or erase historical effects.

The source-bound component checks use actual disposable PostgreSQL, protected
Git, two scoped editing handoffs and Docker independent checks, with explicit
synthetic native/auth/resource identities. Withdrawal after final claim prevents
integration invocation; withdrawal after all checks confirms historical return
without evidence/approval. Healthy serial background and foreground two-worker
review remain covered. Full authenticated connections, runtime/foreground/resource
qualification, TC06/07/10 and original G1/G2/G3/trial acceptance remain unfinished.

See [owner checks](../testing/BACKGROUND_FINAL_AUTHORITY.md) and
[original observations](../../evidence/background-integration-authority-2026-10-23/report.json).
