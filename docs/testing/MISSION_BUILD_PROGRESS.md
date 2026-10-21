# Protected Build check progress in Mission Control

This adds a **read-only PUBLIC Build evidence view** to the
[local Mission Control observer](MISSION_CONTROL_OBSERVER.md). It reuses the same
canonical progress service as `panestria plan progress` and the Build terminal.
It does not run workers, decide approvals, merge code or accept a release.

Build the updated frontend, then explicitly select your **existing private Build
report store** when starting the separate observer. For an existing Build config,
that is its configured `root` plus `/reports`, the directory also accepted by
`plan progress --evidence-store`. The observer never creates it or reads native
credentials/certificates from your Build config. Do not paste a config or its
secrets into the browser.

```bash
uv run --frozen panestria mission-control serve \
  --config "$HOME/.panestria-mission/activity.json" \
  --assets "$PWD/apps/mission-control/dist" \
  --build-evidence-store /ABSOLUTE/EXISTING/PRIVATE/BUILD_ROOT/reports
```

Use the existing separate metadata settings and unused loopback port. Pair as
explained in the observer guide, open the goal and select **Inspect Build
evidence**. Without the explicit store, the view reports **UNCONFIRMED / not
configured**. Ordinary metadata observation still works. A store that is absent,
symlinked/noncanonical, owned by someone else or accessible to group/other is
refused. The read-only store interface cannot publish a report or bundle.

Expected behavior:

- The bar counts final required checks supported by **currently revalidated
  protected bytes**, not event count, worker narrative or elapsed time.
- Each check has its own verdict and report hash. Current-plan milestones show
  evidence status, candidate commit and evidence reference. Descriptions, report
  bodies, diffs, prompts, file paths and private profile content are omitted.
- Canonical goal status, owner merge (`NOT_REQUESTED`, `PENDING`, `CONFIRMED`) and
  release acceptance (`NOT_ASSESSED`) are separate. A full check bar can coexist
  with an ACTIVE goal awaiting owner approval. This is not R3 acceptance.
- Unknown invocations and held claims remain visible. Missing/altered protected
  evidence cannot retain its PASS score. An unavailable response clears the
  previously displayed view; a view older than 15 seconds hides the stale score.
  It refreshes about every ten seconds only while opened.
- The API requires the configured owner/project, a current readable **PUBLIC**
  goal contract and the existing plan/evidence validation. Non-PUBLIC and foreign
  goals are denied; a raw report cannot be fetched through this endpoint.

The new GET `/v1/activity/goals/{id}/build-progress` uses a consistent snapshot
and rolls back its transaction, including any unexpected write. It rechecks
browser authentication before delivery. Configuration is trusted server state;
callers cannot select another store in a request. All current mutation routes
remain absent from this observer.

The connected check uses actual Chromium, the physical CLI server, PostgreSQL,
Git and Docker Bash/independent verification. Native transport, authentication,
OS certificates and capacity are explicitly **TEST_FIXTURE_NOT_LIVE**. It starts
with zero checked requirements, runs the existing synthetic two-worker driver,
observes verified checks with owner merge still PENDING, corrupts only its own
synthetic protected artifact, and observes zero/UNCONFIRMED without new events.
The original kernel progress/owner-merge test and OpenAPI equality test are also
retained. This is component evidence, not a Claude/OS/G3 qualification.

```bash
uv run --frozen pytest tests/integration/test_mission_build_progress.py -q
```

Use the same frontend/browser preparation and disposable Postgres 55439 rules as
the observer guide. The pinned worker image must already be prepared by trusted
test setup. Reviewed runtime scripts must not be group/world-writable. The first
local runs correctly refused an agent worktree's 0664 trusted script; only that
scratch checkout's permissions were corrected, with no production guard change.
CI checkouts use 0644. Original failed runs and the actual correction are preserved
in `evidence/mission-build-progress-2026-10-21/report.json`.

The original raw artifact/diff/test preview, exact approval controls, distinct
Ask/Delegate/Build inputs, phone/TLS/device qualification and cumulative release
requirements remain pending. This narrow evidence projection completes none of
those whole slices by itself.
