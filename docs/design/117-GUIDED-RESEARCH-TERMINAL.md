# Guided same-request research terminal

This AOS-023-S1/S2 component connects the existing local query proposal,
owner-selected collection, local draft and exact claim-review terminal. It is a
manual interface over existing services, not a new autonomous planner or an
accepted research answer. AOS-022 qualification, original D-1/live evidence and
G2/G3 remain open.

`panestria research guide REQUEST --synthesis-config FILE` reads the existing
canonical request/task and retained receipts. An optional `--collection-config`
must select the same owner, project and blob root. It never stages a replacement
goal, edits policy, creates a shadow queue, migrates a database or resets an epoch.
Missing search setup does not prevent viewing the local proposal. No default
service, credential, model download or provider fallback is selected.

The terminal offers one current stage:

| Original canonical facts | Offered action |
|---|---|
| CREATED request, no query-plan intent | Explicit one-time local CPU PLAN |
| Retained successful query plan, CREATED request | Exact query/disclosure/limits review, then original COLLECT if configured |
| VERIFYING, retained passages, no synthesis intent | Exact bounded local inputs, then original DRAFT |
| Retained draft with currently valid sources/policy/task | Open existing owner claim REVIEW |
| Failed/unconfirmed intent, interrupted/cancelled/other state, or no passages | STOP; inspect original state |

Read the entire page, press `v`, then separately `y` to attempt that exact stage.
Escape cancels confirmation. Every subsequent stage needs a fresh full review;
opening or scrolling never calls a model, searches or fetches. A model proposal
cannot authorize its own disclosure. Untrusted question/query/passage text is
displayed as escaped JSON, including invisible/control characters. The complete
stage digest is displayed on its own line, even at the minimum terminal width.

The controller re-prepares the view before executing. The original planning and
synthesis services compare the reviewed input hash under their existing locks,
before retaining the original intent. Collection compares the selected queries,
request/contract/version/epoch, runtime/settings, original limits and contract
budget under the original activation lock. Its original certificate, policy,
connection, lease, dispatch capacity, known/uncertain observations, cancellation
and source checks still apply. The review digest is not a policy grant or a
qualification certificate. The guide adds no external capability.

Per-stage bounds remain the original ones: query proposal at most 3 queries of
256 UTF-8 bytes, 512 output tokens; local draft at most 4 claims, 768 output tokens,
4 passage prefixes; each model request has 4096 context and a 60-second deadline
with separately admitted startup. Collection uses its original source/byte/
deadline/contract/connection limits. These manually confirmed component stages
are not a claim of a qualified autonomous aggregate Delegate budget or workflow.

Existing per-stage intent/return/failure events and artifact hashes are the only
durable stage facts. After a thrown error, interruption or lost reply the current
view offers no retry. Reopening reads the original outcome: a committed return
advances without replay, while failed/unconfirmed work or RECONCILING stops. A
fixed per-request guide key is used only when the original stage has no intent.
No second collection epoch, synthetic success, automatic repair or new goal is
offered to bypass uncertain work.

The last action opens the existing claim/source judgment terminal. Judgments
remain OWNER_REPORTED, automatic support NOT_QUALIFIED, task/training authority
NONE. It does not submit a citation/rubric acceptance check or mark a task done.
The original failed semantic qualification, deferred actual search and release
gate requirements remain unchanged.
