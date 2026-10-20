# Inspect and save actual Build progress

For an accepted canonical PUBLIC Build goal, the owner can now see a terminal bar
of **final required checks**, the current execution state, attention reason and
next action. A private JSON snapshot retains the original contract/check/non-goal
identities, every plan/version/hash, node evidence/candidate/check/handoff refs,
repair envelope and held/unknown work. These are observations of canonical state,
not a second task store or permission to dispatch. They do not estimate an overall
MVP percentage or claim semantic requirements beyond the declared checks.

Use the current migrated database via private `PANESTRIA_DATABASE_URL`, your goal's
owner/project UUIDs, and the private Build runtime's existing `reports` directory.
Choose a **new** output filename in an owner-owned directory with mode700:

```bash
panestria plan progress OWNER_UUID PROJECT_UUID GOAL_UUID --evidence-store /absolute/private/build-runtime/reports --output /absolute/private/new-progress.json
```

The command prints a20-character check bar, counts, goal state, attention/next
action, separate owner-merge/release-acceptance states, remaining conservative
wall envelope and a saved snapshot SHA256. It creates a mode600 file and refuses
to replace an existing export. Compare snapshots by their pinned contract/plan,
candidate and check/evidence references, not only their observation timestamps.
Non-goals remain explicitly NOT_ASSESSED: listing an exclusion is not proof of
compliance. No question, source file, credential or model response is transmitted.

A repeatable-read PostgreSQL transaction observes one consistent event boundary
and revalidates current owner/project policy, contract, plan consent/membership,
protected report bytes, check definitions/results and attempt/epoch. An invalid
or missing blob becomes UNCONFIRMED, with zero claimed PASS for that final bundle;
it does not erase historical task completion. Intermediate-node PASS and handoff
refs appear under milestones, but only the unique current final tree supplies
the goal's check bar. A new unaccepted draft cannot displace the accepted tree.

Expected attention reasons include:

| Reason | What it means / next step |
| --- | --- |
| NO_VERIFIED_MILESTONE | No final verified evidence yet; inspect current plan/checks. A heartbeat cannot advance the bar. |
| EXECUTION_ACTIVE | Current execution/verification is active; CLAIMED alone does not mean a crash or success. |
| OWNER_PLAN_REVIEW_REQUIRED | Inspect the latest exact pending proposal and separately accept it if appropriate. |
| OWNER_MERGE_REVIEW_REQUIRED | Final checks are recorded, but the goal stays ACTIVE until exact separate owner approval. |
| BUILD_STOPPED | Inspect the failed/cancelled task and physical return before any repair. |
| REPEATED_UNCHANGED_FAILURE | The same failed tree/check definitions repeat across versions; stop and reconsider the approach. |
| RECONCILIATION_REQUIRED | UNKNOWN invocations, expired held work or a reconciling task needs qualified inspection; capacity remains held. |
| VERIFIED_BUILD_COMPLETED | Canonical completion, current passed final evidence and exact confirmed Git-effect receipt agree. |
| COMPLETION_UNCONFIRMED | A historical completed goal lacks independently revalidated final proof now; inspect retained bytes/effects. |

The failure fingerprint uses contract, candidate **tree**, verifier-bundle and
required failing check/spec/verdict identities, so changed commit timestamps or
new task IDs do not hide unchanged failure. This view reports the stop/recommendation;
it does not autonomously revise or terminate a worker. [Bounded revisions](BOUNDED_PLAN_REVISIONS.md)
independently enforce finite versions and original cumulative budget. An initial
V1 has no chosen family maximum yet, shown as null rather than invented precision.
Full original envelopes are charged, including unused/unaccepted drafts.

[Source-bound evidence](../../evidence/build-progress-2026-10-20/report.json) uses
actual disposable PG/Git/MCP/Docker/final checks and scripted test-owner merge.
Native/auth/capacity are explicit fixtures. It observes heartbeat resistance,
review versus completion, tampered bytes, scope refusal, active versus unknown
calls, private create-once export with no DB mutations, and repeated unchanged
failed trees across separately reviewed revisions. No new provider/model call,
full requirement/rubric assessment, automatic stall repair, cumulative G3 or human
trial acceptance is claimed. Mission Control/TUI integration remains separate.
