# Find work needing review

Current Mission Control includes **Pending reviews** after pairing. It lists
latest unaccepted plans and pending action approvals from your selected canonical
project, including expired records. It does not expose document content or make
a decision. It updates every10seconds; **First page / refresh reviews** requests
another snapshot. **More pending reviews** loads the next bounded page.

Use the existing [observer setup](MISSION_CONTROL_OBSERVER.md) for metadata only,
or the explicit [plan review mode](MISSION_PLAN_ACCEPTANCE.md) to inspect and
accept PUBLIC plans. Use a separate config/unused port when the owner review
service is running; no existing service is automatically upgraded.

In plan review/intake mode:

1. Find the plan ID in Pending reviews. **Select plan for inspection** fills the
   recovery form. It sends no stage or acceptance request.
2. Press **Inspect staged plan**, review the full canonical contract, checks,
   paths, DAG, inventory, budget, digest and expiry.
3. If plan-acceptance mode is enabled, use its separate checkbox and **Accept
   exact plan**. Intake-only mode cannot accept. Qualified execution remains a
   separate owner workflow.
4. Refresh Pending reviews. A confirmed accepted plan disappears from this
   pending list; its canonical records/tasks/history remain retained. The list
   does not optimistically remove a row when a button is pressed.

An uncertain pending stage/acceptance keeps its original ID. Selecting another
inbox item cannot replace it; inspect that original operation first. An action
approval's **Open approval goal** loads canonical status/timeline. Full protected
Build preview/consent still requires the separate
[Build review mode](MISSION_BUILD_REVIEW.md); generic approvals use their existing
owner workflows. The inbox itself has no approval, reject, run or merge button.

EXPIRED means the recorded expiry was reached at observation time. A future
expiry does not qualify current policy, runtime, actor or consent. Exact review
and the existing decision guards always decide. Failed/stale reads hide entries;
reconnect and refresh. An empty page means no matching pending records in that
page, not that the MVP, goal or release is accepted. Refresh the first page to
find new reviews that arrived before your pagination anchor.

The list shows metadata for open goals only. Closed goals and resolved requests
remain in canonical history. Policy grants, other review families, full dispatch
and original release/owner acceptance are separate R3 obligations.

Focused connected checks (production assets and Chromium setup first):

```bash
uv run --frozen pytest tests/integration/test_mission_review_inbox.py tests/e2e/test_aos_005.py::test_openapi_matches_the_mounted_routes
```

Fixtures use disposable PG55439, owned ports, actual HTTP/CLI/Chromium and Git,
explicitly seeded VERIFYING task state and declared synthetic inventory. No
native execution, provider/search/model call or runtime qualification is claimed.
Preserve owner services, data and original evidence.
