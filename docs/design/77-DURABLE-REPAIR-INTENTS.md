# Durable bounded repair model intents

AOS-025-S3/S4/S5 and MVP-X10 require a model-turn bound that survives a fresh
output directory, process or backup restore. Extend the existing local repair
command and immutable `task_event` ledger; do not add another task store or make
model output an accepted plan.

Before model I/O, a READ COMMITTED writer acquires fleet, project and goal/task
locks, rereads the frozen parent/source/policy and remaining budget, appends a
strict `build.repair_draft.started` event and obtains its commit acknowledgment.
Generation holds no database lock. A lost start acknowledgment never dispatches
the model. Mutation reads occur after writer locks; a repeatable-read snapshot
opened while waiting would risk missing a committed cancellation/revision.
Read-only source observations still use repeatable read.

The first intent fixes `maximum_versions - 1` model turns (one or two) over the
entire goal family. Every acknowledged turn permanently reserves360 seconds for
generation and lifecycle overhead from the original cumulative wall envelope.
The existing generation request still limits60 seconds/1024 output tokens.
This reservation is not measured elapsed time or a guarantee of interrupting
uninterruptible driver/filesystem I/O. A return beyond the reservation becomes
unconfirmed and cannot publish or permit further model/revision work. There are
no refunds, cash estimates, automatic retries or implicit provider changes.

Additive migration0037 constrains goal-level audit payloads and uniquely guards
turn, key and final outcome. Existing event ordering/immutability remains in
force. The strict read projection rejects malformed, duplicate or unbound audit.
Downgrade refuses once repair audit exists. Only disposable databases were
migrated for these checks; operational backup/forward migration is separate.

Returned artifacts use the existing protected report CAS. A confirmed outcome
binds all eight fixed private files to their hashes and original intent. Same-key
replay validates those exact private bytes and acknowledges historical output
without inference, renewed review or authority. Different keys/directories cannot
reset counts. Failed returned output remains NOT_PUBLISHED. Missing return or
uncertain lifecycle completion remains UNCONFIRMED and blocks further repair I/O
and canonical revisions. If completion committed but its acknowledgment was lost,
keep the original outcome/files; the next exact replay resolves that observation.
No force-clear or inference-based reconciliation is provided.

The source cursor excludes only the two exact repair bookkeeping event kinds;
policy/task/contract/other goal events still fence publication. Final publication
rereads the locked source after protected artifact writes. Progress and the
metadata-only `plan repair-turns` command expose counts, reservation seconds and
unconfirmed turns. A plan revision independently includes these reservations in
its cumulative consent and still needs separate exact owner acceptance.

[Connected evidence](../../evidence/repair-draft-intents-2026-10-21/report.json)
uses real PostgreSQL, CLI, Git, protected CAS, MCP/Docker native fixtures and
custom-format backup/restore. Original synthetic model/runtime identities remain
explicit. Qualified repair accuracy, autonomous repair, broader planning and full
original AOS-025/G3/owner acceptance remain pending.
