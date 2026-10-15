# Durable binding for an internal registered check

Prerequisite: #74 private transport, built on merged #73 protocol. This focused
component connects one controller-selected read-only check and protected candidate
snapshot to existing PostgreSQL invocation fencing, policy intersection and Docker
sandbox. It does not enable a native CLI profile or grant access through an API.

Bind the actor, canonical goal contract/hash, current attempt/epoch/policy reference,
reviewed script digest, read-only sandbox profile, candidate manifest and one
controller session UUID. Model arguments contain only the two advertised references.
Admit only a command required by a trusted-command-ref in that exact contract;
read permission must be PERMIT across trust/privacy/autonomy with validated trust
certificate. Approval-needed is a refusal, never an inferred approval.

Use a deterministic request/key for the session so a reconstructed controller
cannot rerun a CLAIMED/UNKNOWN/RETURNED invocation. Prepare/claim/current checks
and events commit through the existing InvocationService and same database. The
claim and periodic checks must reauthorize read policy, lease and cancellation;
no Docker or candidate/report mutation occurs inside those transactions. Trust
certificate validation reads the existing protected certificate store.

Verify the protected Git snapshot before and after the run. Mount it read-only,
with reviewed script outside candidate scope, no network and nonroot resource
caps. Bound raw check output to 8 KiB, store the complete output only inside a
protected bounded report, read it back and verify its hash before recording a
RETURNED invocation. A process that exited with a nonzero check code still has a
completed execution receipt; that receipt reports a failed check and cannot
complete the task. Cancellation, policy/lease loss, missing/corrupt report or any
uncertain outcome cannot produce a COMPLETED protocol receipt.

The read receipt is not independent verification, a merge approval or a release
pass. Actual PostgreSQL/Docker/Unix/stdio tests use only synthetic candidate data;
no provider requests, credentials or account changes are needed. Actual native
MCP configuration and hostile-project/tool conformance remain a separate task.
