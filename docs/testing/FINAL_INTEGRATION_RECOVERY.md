# Final integration dispatch and recovery

The trusted final plan node now records a `build-integration` invocation using the
same canonical PostgreSQL prepare/claim/return protocol as other bounded work.
Its exact scope, contract/policy, attempt/epoch, accepted plan/handoffs/checks and
verifier bundle are pinned. The claim commits before protected Git assembly or
independent checks begin. Reentry cannot dispatch that invocation again.

This matters during cancellation: an active final verifier is dispatched work,
even though it is a trusted controller rather than Claude. Plan-wide cancellation
must retain its capacity instead of classifying the slot as NO_DISPATCH. The
controller uses the remaining database lease time for its Git/check deadline.
A cancellation still prevents candidate PASS publication or merge approval.

A confirmed trusted return records a protected receipt and historical RETURNED
invocation before independent evidence publication. That receipt does not approve
the candidate or resume the attempt. Cancellation/policy/lease/input fences still
apply to publication and exact owner merge review. Physical return may be recorded
after cancellation; capacity is not automatically released by that observation.

Unrecognized/uncertain verifier cleanup retains UNKNOWN and the claim. While the
attempt remains current, the final task becomes RECONCILING with a retained report
and explicit cleanup reason. There is no evidence PASS, approval or protected-ref
change. Exceptions, interrupts and lost receipts similarly cannot permit a replay.
A conflict has its own returned trusted Git report and canonical owner review stop.

Inspect existing `plan claims` and `build status` for the plan/goal, and retain the
private reports. Do not manually change UNKNOWN to RETURNED, free the database
claim, prune storage or retry a potentially running process merely because the
lease expired. Safe historical release/physical recovery remains the next scoped
implementation outcome; this change supplies its missing final-controller intent.

The [decision](../../adr/0007-final-integration-invocations.md) explains the additive
invocation kind and failure boundaries. The [component evidence](../../evidence/final-integration-intent-2026-10-20/report.json)
uses real isolated PostgreSQL, protected Git and Docker checks. Native transport,
capacity and worker identity are explicit fixtures. It does not qualify a native
provider/runtime or complete the B-1/G3 release gate.
