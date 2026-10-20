# Accepted plan nodes and final-tree verification

Status: implementation decision for R3, 2026-10-20.

The one-worker path correctly requires all goal checks. Applying that unchanged
to every node of a two-worker plan prevents independently verifiable partial
work, and permitting arbitrary check subsets would weaken goal acceptance.

Derive a task's applicability from immutable accepted plan membership. Revalidate
its owner/project, latest goal contract, policy, inventory, DAG and consent using
the canonical store. The worker cannot select its keys or paths. Each executable
node must have a required check. An executable plan has one terminal integration
node, reaches all other nodes, and assigns every goal check to that terminal.
Storage-only proposals without this shape remain inspectable but not executable.

The independent verifier receives this derived typed scope. It executes exactly
the node's accepted checks and fails changed paths outside that node's literal
paths, even if the broader goal allows them. Its protected reports bind the
scope hash; kernel publication independently reconstructs and checks the scope.
The original GoalContract is never rewritten or cloned to create worker subsets.
Existing non-plan evidence v1 bytes and all-check semantics stay unchanged.

Intermediate verification does not authorize a protected merge. The public
approval service, Build merge review and effect dispatch refuse intermediate
nodes even if they happen to run every goal check. The final node requires the
whole check set on its exact integrated tree and the existing owner approval.
Intermediate results are NODE_VERIFIED, not a completed goal or merge. Scheduling,
verified-node handoff completion, conflict resolution and real adapter/runtime
qualification remain separate integration work; this decision supplies no new
provider, credentials, budget or implicit worker admission.
