# Run an accepted PUBLIC two-worker Build plan

This foreground controller executes two independent Claude subscription assignments,
retains their verified handoffs, checks their combined tree and stops for exact
owner merge review. Each worker has one scoped Bash job in its own network-disabled
workspace. A new-file assignment may start with no selected source files. The
existing [Build review TUI](BUILD_REVIEW_TUI.md) reviews the final goal.

Use the separate private [owner Build setup](OWNER_BUILD_CLI.md), a database migrated
to current head, Docker/the pinned image and a current real
[runtime certificate](BUILD_RUNTIME_QUALIFICATION.md). The existing dedicated Claude
profile must be authenticated. The operator configuration, credentials, private
reports and exercise files stay outside Git. No API key, login, model download,
paid overflow or fallback is supplied by this command. Keep the owner's existing
review databases/services separate from disposable integration tests.

## Prepare, review and accept

Obtain the current protected `refs/heads/main` commit as BASE_SHA. Export its actual
sanitized snapshot and the expected binary/source/profile worker declarations:

```bash
panestria plan inventory --config /absolute/private/build.json BASE_SHA --output /absolute/private/inventory.json
```

`DECLARED_FOR_REVIEW` is inventory metadata, not runtime qualification or a grant.
Prepare an owner-authored PUBLIC contract and proposal using
[the typed plan format](BUILD_PLAN_PREFLIGHT.md). This driver accepts one or two
independent `claude-public-bash` nodes, then one `trusted-integrator` node depending
on every edit node. Use literal assignment paths, `scoped-bash` for workers,
`trusted-test-runner` for the final node, node wall limits of30–120seconds and zero
API microunits. Aggregate attempts/wall budget must fit the contract. The terminal
node contains every original acceptance check and all predecessor paths. Scope,
privacy, checks and budgets are frozen; a model cannot widen them.

```bash
panestria plan validate OWNER_UUID PROJECT_UUID --contract /absolute/private/contract.json --proposal /absolute/private/plan.json --inventory /absolute/private/inventory.json
panestria plan stage OWNER_UUID PROJECT_UUID --contract /absolute/private/contract.json --proposal /absolute/private/plan.json --inventory /absolute/private/inventory.json --idempotency-key public-plan-1
panestria plan inspect OWNER_UUID PROJECT_UUID PLAN_UUID --output /absolute/private/frozen-review.json
panestria plan accept OWNER_UUID PROJECT_UUID PLAN_UUID EFFECT_SHA --accept-plan
```

Review the exact retained plan/contract/inventory and pending consent first.
Acceptance creates canonical tasks; it does not launch them or approve a merge.
Consent expires after15minutes. The driver executes an accepted plan. Use the separate [local draft command](LOCAL_BUILD_PLANNER.md) for an explicit one-call offline proposal and [bounded revisions](BOUNDED_PLAN_REVISIONS.md) after eligible stopped work.

## Execute and review the final tree

```bash
panestria plan run --config /absolute/private/build.json PLAN_UUID --public-subscription-run
panestria build status --config /absolute/private/build.json GOAL_UUID --diff
panestria build tui --config /absolute/private/build.json GOAL_UUID
```

The explicit flag authorizes this PUBLIC subscription run under the already
reviewed project policy. Current policy/certificate, actual base snapshot, declared
workers and supported redacted native metadata must match before reservation.
Fresh actual CPU/RAM/disk/power observations retain foreground reserves. At most two
plan claims across controllers occupy capacity; serialized scopes/capacity can wait.
No GPU/model capacity or precise remaining subscription quota is inferred.

Expect `WAITING_APPROVAL` only after every editing node completes, protected
handoffs, conservative combined-tree assembly and the full final checks. The
`tasks` array is canonical; the in-memory `worker_observations` array is a completion
snapshot and can lag a just-committed handoff. Goal state stays ACTIVE and the
protected ref stays at BASE_SHA until exact owner approval in the TUI or existing
`build approve` command. Approval updates only the protected copy, preserving the
original source working checkout.

Conflicting candidates produce `CONFLICT`, a canonical RECONCILING task/event and
private conflict paths/contributors visible in Build status. There is no candidate
PASS, approval or ref advance. This is an owner review stop, not automatic conflict
repair. A failed/uncertain/native-quota result stops new admissions and is never
silently retried with another provider. Inspect canonical claims before fresh work:

```bash
panestria plan claims OWNER_UUID PROJECT_UUID PLAN_UUID
panestria plan cancel OWNER_UUID PROJECT_UUID PLAN_UUID PROPOSAL_SHA
```

Cancellation fences every task and both native calls. Claimed/UNKNOWN work retains
capacity until physical reconciliation proves release safe; expiry alone cannot
free it. See [lifecycle recovery](PLAN_LIFECYCLE.md). Ctrl-C also requests plan-wide
cancellation and waits for bounded owned calls. Closing a review screen does not
cancel a running controller.

## Observed validation and limits

[Source-bound results](../../evidence/native-plan-execution-2026-10-20/report.json)
retain controller checks, legacy CLI/TUI compatibility and actual failures before
the assignment-context correction. On clean `6a1f39c`, eight affected component
checks passed, eleven actual runtime checks passed and the actual two-Claude
journey passed in22.29seconds. It observed both native disclosures before either
native return, two tool receipts/handoffs, final PASS checks, wrong-digest refusal,
exact scripted test-owner merge and zero remaining plan claims. The original
source checkout stayed unchanged. This is synthetic test-owner approval, not a
human acceptance or G3 pass.

To deliberately repeat the live journey with an existing matching certificate:

```bash
PANESTRIA_NATIVE_QUALIFICATION_DIRECTORY=/absolute/private/qualification uv run --frozen python -m pytest tests/integration/test_native_plan_execution.py::test_actual_public_two_claude_plan_and_exact_final_merge -q
```

The default controller suite mocks native/auth/capacity only and still exercises
real Postgres, Git, private CAS, MCP, Docker tools and independent checks. It is not
native qualification. The narrow fork/join driver does not complete the general
DAG, second adapter, revision/repair, personal-platform integration, cumulative
release gates or actual owner trial.
