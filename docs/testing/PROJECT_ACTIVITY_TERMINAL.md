# Inspect project activity in the terminal

This is a read-only overview of existing work in **one configured project**.
It shows canonical Ask requests and Delegate/Build/kernel goals, active task
counts, reviews and held Build claims. It starts no worker or model. A state such
as COMPLETED is a database observation, not proof of factual accuracy, independent
checks or MVP acceptance. Review content and exact actions in their existing
mode-specific interfaces.

Use current main in an agent/owner-selected checkout with `uv sync --frozen --group dev`.
The database must already be migrated and contain the project. Load its existing
private `PANESTRIA_DATABASE_URL` environment without printing it. This command
does not initialize a database, create a project, widen its policy or fetch models.
Use the `owner_id` and `project_id` from the existing private Ask or Build JSON
configuration; keep them unchanged. UUIDs below are placeholders to replace.

Prepare a new private directory once:

```bash
uv run --frozen panestria activity init \
  --directory "$HOME/.panestria-activity" \
  --owner-id OWNER_UUID --project-id PROJECT_UUID --port 8769
```

Expect CONFIGURED, `server_started: false`, `project_created: false` and
READ_ONLY_METADATA. This creates a small private JSON configuration, a local
bearer token and initialization lock. The token is never printed. An identical
init preserves the original files; conflicting, partial or unsafe files are
refused and preserved. Each project needs its own configuration and unused port.
Keep these private files out of Git. No credential/provider login is requested.

In terminal 1, with the database environment loaded:

```bash
uv run --frozen panestria activity serve \
  --config "$HOME/.panestria-activity/activity.json"
```

Expect STARTING with `http://127.0.0.1:8769`. Leave it running while using the
view. STARTING is not database readiness or an acceptance result. It exposes
only health/readiness and authenticated metadata, with no Ask, job creation,
approval, pairing, artifact or merge routes. It binds IPv4 loopback only, creates
no OS service and cannot be used as a phone endpoint. An occupied port is refused;
choose a new empty configuration directory/port, or stop your own known process.
The command never kills or reuses an existing listener. Ctrl+C stops this server.

In terminal 2:

```bash
uv run --frozen panestria activity tui \
  --config "$HOME/.panestria-activity/activity.json"
```

Expect PROJECT TASKS, your project ID, an observed time and up to eight entries.
An empty project shows no activity. `A` counts active canonical tasks/requests,
`R` pending task reviews, `H` held Build claims. `?` means not applicable/unknown,
not zero free capacity. `!` identifies failure, pending review/reconciliation or
other observed attention conditions. KERNEL means a goal has no canonical
research/Build membership; the UI does not guess its mode from its intent.

- **F5 / r** refreshes the first page. **n** follows a returned next-page cursor.
- **F10 / q** quits the client and restores the terminal. It stops no server/work.
- Snapshots become STALE after 15 seconds or a failed read; refresh explicitly.
  Connection/database failure keeps the last snapshot visibly unconfirmed.
  Authentication or scope loss clears it. There is no automatic mutation retry.
- The standalone view has no edit, submit, cancel or approve controls. Use the
  existing [Build review terminal](BUILD_REVIEW_TUI.md) for exact owner decisions,
  [Ask terminal](LOCAL_ASK_TUI.md) for questions, and research commands for sources,
  drafts and owner claim review. No question, answer, intent, note or artifact
  bytes are displayed by this overview.

An existing offline Ask terminal also opens its project overview with **F4 / t**.
Press the same key to return to Ask. The pending Ask receipt is preserved;
cancellation has no meaning while the read-only pane is open. The Ask server
retains its separate model/setup prerequisites; standalone activity needs neither.
Different Ask/Build project IDs remain separate, not silently combined.

[Connected evidence](../../evidence/project-activity-2026-10-21/report.json)
uses actual PostgreSQL, HTTP, CLI server and PTY keyboard interaction, with
explicit model/native fixtures where existing Ask/Build setup is reused. It
covers scope/pagination, no content/event mutation, read during a real task lock,
Ask progress/control isolation and the standalone no-model launch/port refusal.
These checks do not complete React/SSE, phone/private ingress, qualified research
support, live providers, G3 or the real owner trial.

Select GOAL rows with1–8 for the [read-only event timeline](ACTIVITY_EVENT_TIMELINE.md).
