# Propose a bounded repair of a stopped PUBLIC Build

Use this after inspecting a stopped plan and releasing **every** physically
confirmed attempt with [receipt-bound release](RETURNED_BUILD_RELEASE.md). A
claimed/unknown process, missing verifier-return proof, live task or uncertain
merge keeps repair blocked. This command never frees that work or retries it.
Do not cancel the whole goal if you intend to propose a repair: cancelled goals
cannot be silently reopened.

Create a private replacement proposal with a fresh plan UUID and fresh task UUIDs,
updated dependency references, the same goal/contract hash and declared inventory.
Keep the original paths/checks/zero API budget. Leave enough original wall budget
for every version's full envelope: for example, three 270-second plans need at
least 810 seconds in the original goal. This is conservative upper-bound charging,
not an estimate of actual elapsed or provider usage.

```bash
panestria plan revise OWNER_UUID PROJECT_UUID PARENT_PLAN_UUID PARENT_PROPOSAL_SHA256 RETURN_PROOF_SHA256 --proposal /private/revised-proposal.json --inventory /private/original-inventory.json --maximum-versions 3
panestria plan inspect OWNER_UUID PROJECT_UUID NEW_PLAN_UUID --output /private/new-revision-review.json
panestria plan accept OWNER_UUID PROJECT_UUID NEW_PLAN_UUID NEW_EFFECT_DIGEST --accept-plan
```

The existing private `PANESTRIA_DATABASE_URL` selects the database; no database or
provider is configured by these commands. Review the exact parent, failed result,
paths/checks, version bound, cumulative budget and expiry before accepting. The
maximum includes the initial version and unaccepted drafts, and cannot be raised
by later proposals. Lost identical replies replay the original digest/expiry.
Changing proposal contents requires another permitted version. No child task or
execution permission is created until separate acceptance; accepted tasks still
require the current runtime, policy, capacity and explicit run intent.

Use [the native plan command](NATIVE_PLAN_EXECUTION.md) only for its supported two
independent PUBLIC Claude nodes plus trusted final integrator. A general valid DAG
is not automatically a supported native execution shape. Current/old status and
original evidence remain inspectable. Old plan dispatch/cancel receipts cannot
affect a newly accepted version. A successful revised final tree still requires
all original checks and a fresh exact owner merge decision. Failed old tasks stay
failed even after the current revised goal completes.

`plan_repair_limit_exhausted` and `plan_repair_budget_exhausted` mean stop and
review the goal rather than loop. `plan_previous_work_unconfirmed` means inspect
canonical tasks, claims, invocation and effect receipts. `plan_parent_superseded`
means read the latest retained version. Scope/privacy/cost changes are refused;
obtain corresponding new authorization instead of editing retained records.

[Source-bound evidence](../../evidence/bounded-plan-revisions-2026-10-20/report.json)
uses real disposable PostgreSQL, Git, MCP/Docker tools, final checks and scripted
test-owner approval. Native transport/auth/capacity are explicit fixtures, with
no provider call. It observes failed-run release, concurrent replay, immutable V1
bytes, finite versions/budgets, stale-plan denial and revised exact merge/goal
completion. It is not a generic repair-quality, live runtime or G3 release pass.
