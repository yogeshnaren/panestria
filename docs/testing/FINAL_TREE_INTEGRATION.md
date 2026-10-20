# Review the exact combined Build result

After independently verified intermediate nodes are completed through the
[canonical scheduler](PLAN_SCHEDULER.md), claim the final integration task. Use its
actual attempt ID and epoch from `plan claims`. The accepted inventory must bind
the actual base-tree snapshot, and all candidate objects must already be retained
in that owner's protected bare repository.

```bash
panestria plan integrate --config /absolute/private/build.json PLAN_UUID FINAL_ATTEMPT_UUID EPOCH
panestria build status --config /absolute/private/build.json GOAL_UUID --diff
panestria build tui --config /absolute/private/build.json GOAL_UUID
```

The command uses existing private Build configuration/current runtime certificates
and canonical scope; it grants no policy, credential, provider or model admission.
It imports no worker Git configuration or hooks. It revalidates each protected
handoff, actual tree, snapshot and allowed paths against the common base. Distinct
file changes and deletions can combine. Different edits to the same file, including
non-overlapping text edits, conservatively require owner resolution. Structural
file/directory conflicts also stop. Worker workspaces and protected refs are never
overwritten by this operation.

A CONFLICT response includes a private CAS report hash, conflicting paths and
contributing task IDs. It has no integrated candidate, verifier PASS or merge
approval. The owner must review alternatives and prepare a separately admitted
resolution; automatic conflict resolution/replanning is not implemented here.

A clean combination gets a fresh exact candidate, then **every original goal
check** runs against its full frozen tree in the existing independent verifier.
Passing individual nodes cannot substitute for this run. A wrong combined result
returns FAILED with evidence and no approval. Current policy, accepted plan,
handoffs, checks and fenced attempt are revalidated before publication. Cancellation
between successful checks and publication prevents authoritative evidence/approval.

WAITING_APPROVAL identifies the exact full-tree evidence and owner preview. The
existing Build status/review terminal now resolves canonical final tasks as well
as legacy one-worker tasks. Review the diff and each check; approving uses the
existing protected Git CAS and exact owner decision. Integration itself does not
approve, dispatch a merge or complete the goal. The original base must still match
at protected-ref dispatch, and changing reviewed code/checks invalidates authority.

The retained input report identifies controller integration and worker inference
NOT_RUN. Native worker qualification and the real two-worker orchestration/demo
remain required separately. [Plan lifecycle](PLAN_LIFECYCLE.md) releases confirmed final reservations and cancels all goal tasks. Failed/unknown physical-process reconciliation is still executor work; an ambiguous process is never assumed stopped.
The integration staging directory retains bounded snapshots/results under the
private Build root (worst-case about576MiB plus protected Git objects within the
scheduler's disk reserve). Nothing prunes these directories or owner storage.
