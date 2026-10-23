# Reviewed confirmed Build excerpts in ordinary local memory

R3 AOS-012-S6 now connects the existing confirmed PUBLIC Build archive to the
existing MemoryService and offline Ask. Archive capture alone grants no recall.
This is a local reference integration, not automatic learning or training.

`OfflineBuildRecall` reads a complete archive with existing hash, scope, contract,
final-check and historical merge validation. It builds a maximum1536-byte UTF-8
note with original reference/goal/candidate/evidence hashes, confirmation time,
up to160 bytes of intent and256 bytes of diff. Shortened fields are labeled;
the full diff hash and original archive remain available. It copies neither
native logs nor credentials. Binary/non-UTF-8 text refuses import.

Prepare is read-only. The exact review hash binds the owner/project, reference,
current policy version/hash, whole note, local-reference purpose and retention
period. Both current logical read/edit permissions must PERMIT PUBLIC/local.
Confirmation requires the explicit local-recall flag and reconstructs the same
review; changed policy, archive or duration refuses it. The current project
policy share lock precedes memory writes. A scoped transaction advisory lock
serializes import of the same reference. PostgreSQL stores the source, revision
and memory item atomically using ordinary MemoryService; no new schema/state.

The item is unpinned, untrusted, PUBLIC and retained for the reviewed1–365 days
(default30) from confirmation. All historical revisions are inspected before
insertion: an exact active replay returns the existing identifiers and expiry
without renewal, events or another item. Suppression, expiry, ambiguity or an
owner correction refuses reimport. Separate explicit suppression needs the
expected row version and matching historical source in the same owner/project.
It remains possible after policy revocation and preserves archive/history.

No new ContextCompiler or Ask authority is introduced. Existing scoped relevance,
privacy, token budget, retention, conflict resolution, source revalidation and
retrieved/included usage records govern whether the note reaches offline Ask.
An untrusted note cannot supply tools, approval, verification or training rights.
Its URI/hash describes the imported historical reference; it is not a signature,
fresh runtime qualification or proof that arbitrary future advice is correct.

The copied memory is independent of the archive after import. Archive removal or
correction does not erase consented memory history; use ordinary memory correction
or suppression. Expiry prevents future retrieval and does not delete storage.
The local-reference purpose and training DENIED remain explicit. There is no
training exporter or universal future connector-purpose enforcement in this
component; any later export needs independent rights and destination review.

The CLI loads private scoped settings and the memory database without constructing
OwnerBuild, Git, runtime certificates, native authentication or a model. Recall
itself runs no inference. Existing offline Ask separately admits its configured
local runtime. See the [owner guide](../testing/OFFLINE_BUILD_RECALL.md) and
[source-bound observations](../../evidence/offline-build-recall-2026-10-23/report.json).
Actual cached CPU retrieval returned the correct changed value in a sentence,
but failed the explicit number-only instruction. That strict test remains failed;
no quality, model, release or automatic-training pass is claimed.
