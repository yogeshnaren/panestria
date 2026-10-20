# Verification for accepted plan nodes

Canonical plan storage is now on main. This component connects its immutable
membership to the existing independent Build verifier, without changing the
original goal contract or old non-plan evidence bytes.

For an accepted executable plan, the kernel derives each task's check keys and
literal changed-file paths from its retained node. It requires one terminal
integration task reaching every other node, with the entire goal check set.
Every executable node must have at least one required check. Storage-only plans
with another shape remain stored/inspectable but cannot use this execution path.

The controller loads this scope before independent verification. The verifier
runs the node's checks and fails changes outside its paths even when the wider
goal permits them. Protected reports contain the scope hash; publication and
reads independently reconstruct it from the current canonical plan. Missing,
foreign, expanded or worker-chosen subsets cannot become authoritative evidence.

An intermediate result reports NODE_VERIFIED. It does not request a merge,
complete the goal or skip final verification. Generic owner approval requests,
Build merge review, dispatch and confirmed merge completion reject intermediate
tasks, including ones that happen to pass every goal check. The terminal task
still requires full checks against its integrated tree and exact owner approval.
Existing non-plan one-worker review/merge behavior is preserved.

This is verifier/authority integration, not the scheduler or a completed two-worker
demo. Admission, native runtime qualification, isolated workspaces, canonical
handoff completion, conflict handling and final-tree assembly remain required.
The protected controller fixtures test these guards with actual PostgreSQL/Git/
CAS and path verification; they do not establish new live provider/OS certificates.
See [the design decision](../../adr/0006-plan-task-verification.md).
