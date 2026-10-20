# Release capacity from confirmed stopped Build work

An unavailable/failed/cancelled native run must not automatically reuse its slot.
The owner can now release a stopped attempt only when canonical returned receipts
and protected reports prove the physical work has ended. This is a historical
accounting operation: it does not retry, mark code correct, renew permission or
approve a merge. UNKNOWN or CLAIMED work remains held.

After inspecting the exact goal/plan/attempt and private reports:

```bash
panestria plan claims OWNER_UUID PROJECT_UUID PLAN_UUID
panestria plan release-returned OWNER_UUID PROJECT_UUID PLAN_UUID ATTEMPT_UUID --evidence-store /absolute/private/build-runtime/reports
```

The database comes from the existing `PANESTRIA_DATABASE_URL`. The reports path is
the private owner Build root's `reports` directory, not a worker workspace. Supply
existing credentials privately; no provider/API credential or model is required.
The command returns RELEASED, a proof digest and `execution_authority: NONE`.
Repeated identical releases reuse the immutable proof and make no external call.

Current schema head is `0036_returned_build_release`. It adds VERIFIED_RETURN to
the existing immutable release ledger without rewriting prior claims, handoffs,
NO_DISPATCH or VERIFIED_FINAL records. Back up the database **and** private report
store before upgrading your own installation using the normal Alembic workflow.
This implementation's tests migrated only disposable databases; the owner's review
database/services were preserved. Downgrade refuses after the new proof is used;
restore or forward repair preserves its audit.

The release requires exact historical owner/project/plan/task/attempt/epoch,
contract/binding/report hashes and a stopped/fenced task. Current policy revocation
does not prevent acknowledging that old work ended; it also cannot authorize new
work. Dispatched/uncertain side effects or another active attempt block release.
Prepared invocations cannot launch after the task is fenced. Unknown/claimed
invocations, missing/mismatched receipts, unconfirmed native termination and
uncertain verifier cleanup are refused.

A noncandidate native response must have a confirmed terminated process and the
expected scoped PUBLIC Bash profile. A native candidate alone is insufficient:
independent verification happens later. That case also needs an actual protected
published verifier bundle, exact plan checks and known cleaned/prelaunch check
outcomes. A cancelled candidate without this proof stays held. The final node uses
its separate [integration return receipt](FINAL_INTEGRATION_RECOVERY.md), pinning
the exact final inputs and verifier reports. An ambiguous return is not converted
to RETURNED by this command.

A failed task remains FAILED. A confirmed withdrawn CANCELLING task (or explicitly
withdrawn final conflict) becomes CANCELLED through the declared cancellation edge.
An already successful verifier attempt remains historical success even when its
merge was withdrawn. The goal is not declared complete, and an existing failed
check is not turned into PASS. Use `plan cancel` again if you intend to finish
withdrawing the whole goal; safe slot release itself does not create a repair.

[Source-bound component evidence](../../evidence/returned-build-release-2026-10-20/report.json)
observes confirmed-rejection release with concurrent replay after policy revocation,
UNKNOWN retention, actual failing combined checks, withdrawn final approval,
immutable audit, populated downgrade refusal and actual pg_dump/restore. Native,
auth and capacity observations are explicit fixtures; the database, protected Git,
MCP/Docker tools and independent final checks are real. No new provider call or
live runtime/gate qualification is claimed. The original receipts and returned
claim rows remain inspectable. Never release by elapsed time, manually relabel an
UNKNOWN outcome, prune storage or assume a disappeared process from a heartbeat.
