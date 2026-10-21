# Project activity observations and terminal

The owner prioritizes usable terminal workflows before GUI work. This adds one
content-free, project-scoped observation surface and a standalone loopback launch
mode. It is partial AOS-028 backend/terminal delivery. Original React/TypeScript,
SSE reconciliation, approvals/evidence, private phone ingress and release cases
remain required; this does not substitute terminal tests for browser cases.

`project_activity` requires a repeatable-read, read-only transaction. It reads
canonical `ask_request` and `goal` records in the authorized owner/project;
Delegate membership comes from `research_request`, Build from `build_plan` or
the existing legacy native Build task, otherwise KERNEL. It computes attention,
active/review counts and actual held Build claims. No task state machine, grant,
event, dispatcher, model or cached success score is added.

`GET /v1/activity` uses the existing Host/Origin and bearer authorization with
server-pinned owner/project. Pages are limited to32 entries (terminal8), ordered
by created time, UUID and source. Cursors contain a source/UUID and resolve only
inside the same authorized project. Ask/goal UUID collisions stay distinct.
Pagination reads fresh canonical snapshots; it is not a frozen full-history
export or SSE subscription. New entries appear on first-page refresh.

The typed closed DTO omits all content, artifact IDs/bytes/digests, prompt,
intent, profile, title, note and answer fields. Responses use no-store. The
client verifies scope and contract, bounds the HTTP response/time and disables
environment proxies/redirects. Auth/scope loss clears the view; failed/old reads
are unconfirmed. Observed canonical completion never confers verification or
acceptance. Held claims do not mean free capacity; non-Build values are unknown.

The standalone `activity init/serve/tui` profile needs only existing scope IDs,
private local auth files and the migrated database. It mounts only observations
and health, no browser sessions, Ask, goal creation, artifacts, tools or approval
routes. Existing offline Ask mounts the same observation router without mounting
unrelated goal mutation routes. The initializations are exclusive/create-once,
private and preserve conflicts/partial files. Ports are exclusively reserved and
other processes/services untouched. No model/cache/provider login or OS timer.

The terminal displays eight bounded rows and a last-observed time. It marks reads
stale after15 seconds without confirmation, offers explicit refresh/next page,
and preserves the separate Ask request while its metadata pane is open. Runtime
and content/actions remain in their owning interfaces. The small settings files
and in-memory view are not an authoritative second store.

[Guide](../testing/PROJECT_ACTIVITY_TERMINAL.md) and
[source-bound component evidence](../../evidence/project-activity-2026-10-21/report.json)
record real PG/HTTP/CLI/PTY behavior and retained initial assertion failures.
No live provider turn, model download, phone endpoint, release promotion or
owner acceptance was performed.
