# Read-only goal event timeline

Start the existing [project activity server and terminal](PROJECT_ACTIVITY_TERMINAL.md).
No new configuration, model or provider is needed. In the project pane, press
1–8 to select a GOAL row. ASK rows use their separate request receipts and do
not acquire invented goal events. The shared Ask/profile terminal project pane
uses the same controls.

The terminal shows the selected goal's canonical state and bounded event rows:
decimal sequence, kind, schema version and privacy label. The API also retains
opaque event IDs for reconnect/deduplication. It
never retrieves event payloads, trace IDs or plaintext payload fingerprints.
Event names cannot supply a check PASS, worker success or approval authority.

- PgUp/PgDn scrolls within the current page.
- F5 or n loads the next page/new events from the last delivered cursor.
- r explicitly replays from the start.
- b or Escape returns to project tasks; F4/t returns to Ask where applicable.
- Cancellation/submission keys have no mutation meaning in the timeline.
- q leaves the terminal under the existing active-Ask warning rules.

A read older than15 seconds or a failed refresh is marked stale/unconfirmed.
A retention gap/future cursor restores the canonical snapshot and discards
missing history rather than inventing events. Empty updates preserve the bounded
last page while refreshing the snapshot. At most50 event rows are retained in
the view; only the rows that fit are drawn. This TUI uses explicit JSON paging,
not an automatic subscription or a complete React reducer.

`GET /v1/activity/goals/{goal_id}/events?after=0` exposes the same metadata-only
page under the existing owner/project authentication. `Accept: text/event-stream`
selects existing canonical SSE replay: Last-Event-ID reconnect, bounded connection,
retention resync and authority checks before delivery. Cursors stay decimal
strings, including values greater than2^53. An unknown goal/other project denies.
The activity-only server still mounts no goal/Ask/profile/session/approval mutation
routes. No browser/phone credential, TLS ingress or device scope is enabled.

The metadata path uses read-only repeatable-read transactions without acquiring
goal/task write locks. Browser authority is checked separately before the read
and before delivery, including cached SSE frames. Original full goal event routes
retain their existing behavior. OpenAPI includes the explicit metadata contract.

[Original component observations](../../evidence/activity-event-timeline-2026-10-21/report.json)
cover actual PostgreSQL, HTTP, SSE and PTY paths. Model/native fixtures are only
used to seed the existing Build/Ask regression journey; no inference is run.
Full React/Vite Mission Control, generated client, cross-mode intake/evidence,
read-only phone ingress and original AOS-028/G3 acceptance remain pending.
