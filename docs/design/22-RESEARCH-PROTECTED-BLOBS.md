# Protected research bytes before source publication

Selected partial AOS-013-S1/S3 outcome: bounded, scoped protected bytes that a
future trusted fetch/reader controller can bind to immutable source metadata.
Prerequisite: current main through request storage #70. No web fetch, source ID,
claim, citation or privacy permission is granted by this file store.

The existing BuildEvidenceStore supplies the repository's pattern of atomic
content-addressed publication and hash recheck. Its 256 KiB cap and Build-specific
reports are not research storage. Keep it unchanged; implement the research store
in kernel with a 2 MiB cap, owner/project UUID directories and stable directory
descriptors. Open directories/files without following symlinks. Require private
owner-only directories, regular owner-only finalized files, one link and exact
hash/size. Reject unsafe existing targets; never overwrite or silently repair a
published blob. Model/reader workers must not receive the store or its descriptors.

Serialize cooperating writers with a directory flock and per-instance thread
lock, with a five-second total lock-wait deadline. This bounds lock contention;
it does not claim to interrupt an unresponsive kernel/filesystem operation.
Write a deterministic per-digest private pending file, fsync, chmod 0400,
publish with a no-replace hard link, remove only that pending name and fsync the
directory. Publication returns only after hash/size recheck. An interrupted pending
file has no valid artifact store key. A retry of the exact digest may remove its
owned single-link partial, or finish unlinking a complete two-link pending file
only after proving both names are the same inode and match the requested bytes.
Never scan/delete arbitrary files or remove a finalized artifact. Existing unsafe
links or ambiguous pending state deny and remain for explicit repair.

The scope is protected plaintext on a local Linux filesystem, not encryption,
profile-vault use, retention permission or protection from malicious same-user
host software. Future SourceStore must check actor/task/artifact metadata,
classification and actual retained authorized-fetch provenance before returning
a usable passage. A matching content hash alone cannot establish those facts.
No database migration, route, model/provider call or release case promotion.

Verify real filesystem bounds/permissions, symlink/hardlink/FIFO rejection,
corruption, cross-project lookup, concurrent writers, descriptor stability after
path replacement, and interruption before/after link publication. Run existing
Build evidence tests because the original primitive remains an independent path.
