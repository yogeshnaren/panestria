# R3 Build Specification — Multi-Agent Build + Mission Control

**Planning status:** DRAFT implementation; active scope is personal-platform-3. Read [the revision-3 contract](../architecture/05-PERSONAL-PLATFORM-REVISION-3.md) and [R3 build sequence](../../phases/R3-BUILD-PLAN.md). No runtime acceptance is claimed.

**Goal:** Demonstrate real concurrent work across two independently authenticated, policy-constrained coding harnesses, while making progress and approvals useful to a human.

**Stories:** [AOS-024](../specs/AOS-024.md), [AOS-025](../specs/AOS-025.md), [AOS-026](../specs/AOS-026.md), [AOS-027b](../specs/AOS-027b.md), [AOS-028](../specs/AOS-028.md), [AOS-029](../specs/AOS-029.md), [AOS-030](../specs/AOS-030.md).

## Execution topology
- Kernel planner emits typed task DAG with dependencies, bounded budgets, check definitions and candidate workers. LangGraph only when real bounded cyclic planning/review is required.
- Harness broker runs Claude Code and Codex through the same WorkerAdapter contract. Each has its own version/auth/sandbox manifest and a separate Git worktree.
- Scheduler leases independent READY tasks and checks resource, privacy, autonomy and capacity; two attempts can execute concurrently when permissions permit.
- Result integration checks conflict and final merged tree, re-runs deterministic tests, and requires approval for protected merge. Successful isolated tests are insufficient.
- DBOS persists authoritative retries/recovery; a timed-out external action enters RECONCILING before any repeat.

## UI core
- React/Vite Mission Control with 3 distinct intakes Ask/Delegate/Build, task/fleet status, artifact/test/diff view, exact bound approvals, errors/unknowns, egress exposure, and OTel/Phoenix trace drilldowns.
- SSE is replayable from persisted event cursor; UI reducer is not the state authority. UI reconnect passes outage and duplicate event fixtures.
- Controls must show reasons (waiting approval, quota unknown, resource cap, auth issue, offline) instead of fake progress.

## R3 security/quality
- Two simultaneous writes to same path are not auto-merged; conflicts reviewable.
- A provider auth/quota denial never triggers a fallback that violates data privacy/consent.
- A malicious repository hook cannot execute for either worker in certified profile.
- All approvals bind final tree SHA, not stale intermediate changes.
- Phoenix exporter outage does not stop execution; no sensitive payload/credential leaks.

## Complete MVP gate
`A-1` offline Ask; `D-1` read-only grounded research; `B-1` concurrent Build; independent three-axis policy negative tests; six chaos scenarios from frozen master §17; 14-day daily-use observation. Log results against code SHA, model/CLI version and hardware profile; no statistically unjustified claims on tiny sample sets.

## Expanded personal MVP scope

MVP-X07–X14 add a bounded encrypted owner profile/canonical classification, portable charter/style/model context, explicit connections/secrets, verified milestones/stalls/repair, a quota-aware preferred-provider queue with verified offline capture, private read-only phone views, target-host resource budgets and REA-informed reuse. Parent IDs and original phase assignments remain intact; these new obligations deliver in R3 and require separate evidence.

The G3 manifest now requires 157 scenarios (124 original + 33 new): pass its 156-case pretrial subset, then complete AOS-030-TC04 with the 14-day owner trial/decision. Only the complete set can PASS final G3. The phone boundary is a deliberate exception to the older no-remote-MVP design: disabled-by-default private authenticated TLS ingress and server-enforced read-only device scope, not public API exposure or remote approvals. Owner-reported quota can schedule useful work, and authorized bounded work may proceed with unknown precision; no-extra-spend and training-purpose eligibility are independently enforced. R4–R7 remain separately authorized expansion.
