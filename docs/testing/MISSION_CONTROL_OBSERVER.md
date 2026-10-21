# Local read-only Mission Control

This React dashboard observes an existing Panestria project. It lists Ask/Delegate/
Build/kernel activity and opens goal task states and event metadata. It submits no
work and approves nothing. State comes from the same Postgres/API as the terminal;
an event called `goal.completed` cannot complete the displayed goal.

Use `main` after the Mission Control observer PR merges. Keep the existing Ask,
Build and research terminals for their actions. This is partial AOS-028-S1/S3,
not the three-mode intake, evidence/approval UI, phone companion or an R3 release.

## Prepare the production UI

From the repository root, use an already installed Node **20.19+ on the 20.x
line, or 22.12+**, with npm **9.5+**. Node 24.19.0 is used by CI and the recorded
local browser run. The workstation's old system Node 16 is insufficient. Select
an existing supported runtime explicitly; these commands do not install Node.
Versions and npm integrity hashes are pinned in the task-local package lock.

```bash
cd apps/mission-control
npm ci --ignore-scripts --no-audit --no-fund
npm run build
cd ../..
```

The resulting `dist` contains three assets (about 231 KB before compression for
the recorded build). Dependencies and browser test binaries require additional
space; none are automatically pruned. The build is not committed or bundled into
the Python wheel: `--assets` explicitly selects that local production build.
Missing, empty, symlinked or oversized required files refuse startup. No CDN or
Vite dev server is involved at runtime.

## Choose an existing project and unused port

You need a migrated Panestria database, an existing owner/project, Python's frozen
environment and its existing private database environment. Load that environment
in the server terminal; never put its credentials in browser URLs or Git.

Prepare **separate** metadata settings on an unused loopback port. Replace the
UUID placeholders with the existing project's IDs:

```bash
uv run --frozen panestria activity init \
  --directory "$HOME/.panestria-mission" \
  --owner-id OWNER_UUID --project-id PROJECT_UUID --port 8770

uv run --frozen panestria mission-control serve \
  --config "$HOME/.panestria-mission/activity.json" \
  --assets "$PWD/apps/mission-control/dist"
```

Initialization creates only private stable settings/token files; it creates no
project, grant, model or service. The foreground server must remain running while
you inspect the browser. Ctrl+C stops that exact foreground process. An occupied
port refuses startup; it never kills an existing listener. Ordinary `activity
serve` remains metadata-only without browser/session routes.

## Pair and inspect

In another terminal with the same checkout/environment:

```bash
uv run --frozen panestria mission-control pair-code \
  --config "$HOME/.panestria-mission/activity.json"
```

Open `http://127.0.0.1:8770/`, enter the eight-character code and select **Pair**.
It expires after 120 seconds and is usable once. Requesting a new code invalidates
outstanding codes for that project; existing sessions remain intact. The browser
receives a namespaced HttpOnly/SameSite cookie. The token is not returned to UI
code; the logout CSRF value stays in memory only. After a page reload, reading can
continue with the cookie; pair again to regain the memory-only logout control.
No token, CSRF value, private content or view state is saved in localStorage.

Expected behavior:

- The project table shows the latest canonical entries, active-task/review counts,
  attention flags and unknown held capacity. **Older activity** and **Latest**
  navigate bounded pages. An empty project shows an explicit empty state.
- **Open goal** shows canonical status, task state/version/epoch and the latest
  200 observed metadata events. Ask receipts have no invented goal timeline.
- SSE notifies the view to reread canonical JSON. Reconnect/backfill deduplicates
  IDs and keeps decimal event cursors exact above JavaScript's safe integer range.
  A retention resync drops unverifiable history. A 10-second reconciliation also
  refreshes quiet goals. No event grants completion, merge or acceptance authority.
- A failed refresh or observation older than 15 seconds shows **STALE /
  UNCONFIRMED**. Revocation/expiry clears the private project/goal view. **Log out**
  confirms actual session revocation; a failed request reports it as unconfirmed.
- Keyboard focus, native labels/buttons, scrolling tables and React text escaping
  are used. No artifact/source HTML is rendered. This is desktop loopback only;
  phone access, LAN binding, TLS/device grants and Firefox qualification are pending.

## Checks and evidence boundary

CI keeps the existing six check names. `quality` regenerates OpenAPI types,
requires no generated diff, type-checks and builds. Only `platform` installs
Chromium and runs the physical browser journey within its normal pytest lane.
Other lanes do not install frontend dependencies or browsers.

For that targeted journey locally, after preparing the production build:

```bash
cd apps/mission-control
npx --no-install playwright install chromium
cd ../..
uv run --frozen pytest tests/integration/test_mission_control_browser.py -q
```

It uses disposable Postgres 55439, a random owned loopback port, synthetic IDs,
a real Python CLI server and headless Chromium. Do not run it in parallel with
other suites using 55439. `PANESTRIA_TEST_NODE` can select an existing supported
Node binary; `PLAYWRIGHT_BROWSERS_PATH` can select a task-owned browser directory.
There are no provider/model calls, mocked HTTP routes or owner-data migrations.
It tests metadata scope/auth isolation, offline catch-up, >2^53 decimal cursors,
deduplication, retention, canonical state and logout/revocation. It does not qualify
private phone access, full Mission Control actions or cumulative G3/owner trial.

Original source-bound observations are indexed in
`evidence/mission-control-observer-2026-10-21/report.json`; failures are preserved.
Upstream primary references: [Vite requirements](https://vite.dev/guide/),
[production builds](https://vite.dev/guide/build),
[React root API](https://react.dev/reference/react-dom/client/createRoot).
Installed runtime licenses are retained in the frontend's third-party notices.
