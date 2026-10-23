# Retain a confirmed Build result for offline reference

A canonical PUBLIC Build can now retain its exact contract, approved diff,
independent final evidence and check reports as a private offline reference.
This runs only after the goal is COMPLETED with confirmed independent final
checks and the exact successful owner-approved Git effect. A pending review,
failed candidate or worker's claim of success cannot become this reference.

For an already confirmed goal, use the existing private Build config/database:

```bash
panestria build capture-reference --config /absolute/private/build.json GOAL_UUID
```

Expect `status: SAVED` and a `reference_sha256`. To capture automatically after
a normal successful owner merge, explicitly add this boolean to your existing
private Build config:

```json
"capture_verified_results": true
```

The default is false. This opts in to local PUBLIC-result retention; it grants
no inference, execution, memory-promotion or training permission. If capture
fails or storage is full, the returned `offline_reference` is UNAVAILABLE while
the already confirmed Build stays COMPLETED. There is no new worker/merge retry.
After inspection, the manual capture command can retry just this derived capture.

To view the retained metadata or escaped untrusted diff:

```bash
panestria build reference --config /absolute/private/build.json REFERENCE_SHA256
panestria build reference --config /absolute/private/build.json REFERENCE_SHA256 --diff
```

The reader needs only the private config's owner/project/root and the archive.
It does not connect to PostgreSQL, Git, a model, native authentication or runtime
certificates. For a restored copy, update `root` in a private copy of the config
to its absolute private directory containing `offline-results/`. No native auth
or certificate directory needs to be restored. The full historical config schema
remains required; it contains configuration paths, not copied credentials.

The archive is `BUILD_ROOT/offline-results/`. Keep the entire directory when
copying/backing it up. Its content-addressed mode0400 blobs and final manifest
live under `blobs/` in private mode0700 directories. Each read verifies byte
hashes, complete part reconstruction and copied contract/final-evidence scope,
version, required verdicts and check-report references. Tampered/missing parts
are UNAVAILABLE, not an empty successful reference. The archive is a portable
review record, not a full Git repository backup or a fresh execution result.
Rebuilding a repository still needs its baseline/source and ordinary review.

Each manifest binds owner/project/goal/task, plan/hash, original contract,
base/candidate/evidence, exact approval/effect, original canonical merge-event
time and protected invocation binding/receipt/controller-source references.
Model identity stays UNKNOWN when not present in the original evidence. Native
logs/responses are not copied or guessed. The capture copies the independently
checked final code diff rather than treating raw model advice as verified truth.

New schema2 captures also show each invocation's original `request_sha256` and
`configuration_sha256`. For admitted native Build, the request hash identifies
the selected context JSON. `requested_model` is the recorded launcher alias;
`reported_init_model` is the CLI startup report retained in its original receipt.
They do not prove the model serving every response, hidden context, weights,
fallback, usage or billing. The legacy generic `model` remains null. Missing
original metadata stays null even when today's model selection is known.
Old schema1 archives remain readable without rewriting. Explicit recapture can
create a separate schema2 reference from original canonical records; it never
updates an old reference hash. No migration or new inference is needed.

New source receipts also record a bounded original selected-context metadata
manifest: the exact task/assignment header, Git tree and selected file paths,
hashes and byte lengths. It contains no file content or credentials. Confirmed
capture can now reconstruct those exact original files from their protected
immutable Git tree, verify the complete original request hash and retain the
selected context in a new schema3 archive. Its original binding/receipt travel
with it. Missing/changed original metadata, file content, assignment or source
tree refuses capture while preserving the confirmed merge. No current launcher
or plan is used to guess old inputs. Original schema1/2 archives and absent
original input metadata remain immutable and UNKNOWN.

Default viewing still shows metadata only. To view one retained selected input,
use its invocation UUID from the manifest:

```bash
panestria build reference --config /absolute/private/build.json REFERENCE_SHA256 \
  --input INVOCATION_UUID
```

Expect `selected_context` with its original hash/size and payload. This is at
most16KiB of selected PUBLIC input, including pre-edit file contents. It does not
include fixed harness prompts, later tool conversations, raw native output or
physical network observations. A legacy/unretained selection returns
`offline_context_not_retained`. A copied complete archive verifies and displays
this data without a database, Git, auth, certificate or model. It grants no new
task, source-quality, memory or training permission. Schema3 retains the existing
1MiB capture/8MiB history caps; larger captures refuse instead of silently dropping
input evidence. Nothing is pruned automatically.

[Source-bound context checks](../../evidence/native-context-archive-2026-10-23/report.json)
cover exact original pre-edit input/new-file empty selection, copied offline
view, original metadata/hash/assignment/tree refusal, forged provenance refusal,
legacy UNKNOWN, archive capacity and ordinary recall. They use real disposable
PG/Git/MCP/Docker and scripted test-owner approval; native/auth/account/runtime
qualification remains synthetic. No provider request or source certificate is
created or renewed.

[Identity design](../design/110-OFFLINE-INVOCATION-IDENTITY.md) and
[source-bound checks](../../evidence/offline-invocation-identity-2026-10-23/report.json)
cover new and legacy receipt transport, offline copied-archive reads and recall
regressions. Native identity frames are synthetic fixtures, not live qualification.

Only **OWNER_LOCAL_REFERENCE** is permitted here. Training eligibility remains
**UNKNOWN** and training export is **DENIED** until a separate provider/agreement,
data-rights, consent, validation and purpose review exists. Ownership/approval of
a code change does not silently complete that review. There is no training
exporter, fine-tuning, automatic knowledge/skill ingestion or weight update in
this component. Archive validation grants no new task or approval authority.

Limits are explicit:64 provenance records, up to256KiB per retained part,
1MiB payload per capture,32KiB chunks/manifest,4096 blobs and8MiB history. Complete
unchanged references deduplicate without another history write. New bytes are
preflighted before copying; the final manifest is published last. A filesystem
interruption may leave bounded unreferenced chunks, never a published partial
reference. Nothing is automatically deleted/pruned, including orphaned chunks;
retention and backup/restore decisions belong to the owner. Small capture writes
are separate from worker/workspace admission and are enabled explicitly.

[Original component evidence](../../evidence/offline-build-reference-2026-10-21/report.json)
uses actual disposable PG/Git/MCP/Docker verification and scripted exact owner
merge, private deduplicated capture, standalone copied-archive CLI/diff viewing
with no database or credentials, wrong-owner/tamper refusal, and full-history
failure preserving the confirmed merge with no extra worker. Native generation,
authentication and capacity are labeled fixtures. No new model/provider call.

A separate [explicit local recall review](OFFLINE_BUILD_RECALL.md) now copies a
bounded note into ordinary suppressible memory for offline Ask. The archive alone
still grants no memory permission.

This is partial AOS-012-S6/X11 delivery. Legacy single-worker/Ask/Delegate and raw
candidate capture, automatic retrieval, known model identity where absent,
broader retention/suppression qualification, curated ALLOWED training-purpose examples,
queue/foreground scheduling, live qualification and full TC08/TC09/G3 remain
pending. Historical evidence and original gate requirements remain intact.
