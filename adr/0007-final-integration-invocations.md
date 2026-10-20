# 0007: Track final integration before trusted checks start

Status: accepted implementation decision for the R3 Build recovery slice.

The accepted final plan node owns a durable capacity claim. Unlike native workers,
its original trusted Git/verification continuation had no invocation intent. Plan
cancellation therefore saw no dispatched invocation/effect and could incorrectly
release that claim as NO_DISPATCH while a read-only verifier was still running.
This is a recovery/admission gap; a correct final PASS alone cannot prove safe
capacity accounting during cancellation or a crash.

Reuse the existing same-Postgres prepare/claim/return protocol with an additive
`build-integration` invocation kind. Its binding includes exact scope/attempt/epoch,
contract/policy, immutable plan/handoff/check fingerprint and verifier-bundle digest.
Prepare and claim commit before any assembly/check work. Reentry cannot re-claim
an existing invocation. No migration or new task state/store is required: existing
JSON bindings remain intact and the closed Python kind union gains this value.
Older consumers that do not support this kind must reject it, not reinterpret it
as a model/native tool invocation. Sandbox native-tool launch records remain a
separate purpose and do not authorize this continuation.

Validate private paths before claiming. Use the attempt's remaining database lease
time, bounded by the node wall envelope, for Git/verification deadlines. Successful
trusted assembly/check return writes a protected receipt and historical RETURNED
record before independent evidence publication. Publication/approval still require
fresh policy/plan/lease/cancellation checks. Physical return can be acknowledged
after cancellation/revocation without granting completion or future dispatch.

A conflict returns trusted Git metadata without launching verification. Runner
receipts whose reasons establish stopped/cleaned execution, or known trusted
prelaunch refusals, may be acknowledged as returned. Unrecognized/uncertain cleanup,
interruption or a lost reply records/retains UNKNOWN. It produces no verifier PASS
or merge approval and retains capacity. Uncertain cleanup becomes visible as a
RECONCILING final task when it remains current. There is no automatic replay or
lease-expiry release.

This slice supplies the missing intent/physical-return boundary. A later explicitly
verified historical release can use these proofs; this change does not release a
claimed cancellation or infer that an unknown native process has disappeared.
The owner can still withdraw authority across all plan tasks. Source-bound tests
must demonstrate the claim remains held during cancellation, original final review
still works, uncertain cleanup cannot publish/replay, and protected refs are unchanged
on refusal. No extra provider calls or owner database/service changes are needed.
