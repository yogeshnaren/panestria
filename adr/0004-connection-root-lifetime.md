# Connection roots have process-local descriptor identity

**Date:** 2026-10-18. **Status:** implemented prerequisite; live connector
enablement remains pending. **Applies to:** MVP-X09 / AOS-008-S4–S5.

The connection declaration names opaque root references, not paths. A path or
device/inode pair cannot establish arbitrary identity continuity after process
loss, restore or inode reuse. Persisting a raw private folder locator in ordinary
task events would also expose more metadata than the declaration needs.

Use a trusted-controller `ConnectionRootSession`, with explicit existing private
directories, owner/project scope, random 256-bit references and held directory
descriptors. No locator, descriptor number or inode mapping is persisted. A
reference selects the pinned directory object: renaming it does not redirect it
to a replacement at the old pathname. Removal/close invalidates the reference;
restart, another session and reenrollment cannot recover it. Forked use refuses
and closes that child's copies; close-on-exec prevents inheritance across exec.

After restart or restore, setup must explicitly enroll roots again and obtain a
new owner-reviewed declaration containing the fresh references before runtime
use. Replaying a historical approval cannot substitute this enrollment. Do not
silently match an old grant by path, device/inode or newly found folder. No
durable registry, marker in an owner's folder or second task state store is
introduced. This conservative first implementation trades automatic reconnection
for truthful identity; persistent enrollment requires a separate reviewed design.

Linux x86-64 `openat2` provides descendant containment with all four explicit
resolution constraints. Unknown ABI, unsupported syscall/flags or uncertainty
refuses without a weaker fallback. An `O_PATH` descriptor is checked for a
single-link, owner-owned regular file before reopening that exact held object
through the process's private descriptor entry. Size/type/link/identity/change
and fresh relative lookup checks precede returning bounded snapshot bytes. Two
bounded reads of the held object must agree on length and content hash; metadata
alone missed an actual same-length rewrite in qualification. Total read requests
are bounded by twice (max_bytes + 1), not one pass. This observes agreement and
does not provide an atomic snapshot against an arbitrary concurrent writer.
Special files never reach a readable open. Root locators and snapshots stay out
of automatic diagnostics, DB writes, events and worker arguments.

This internal primitive is **not** a GrantBroker, certified account, policy check,
classification/purpose consent, approval, budget reservation or runtime permit.
It has no API/CLI/UI/worker integration. Readable regular files can block on a
stalled filesystem despite `O_NONBLOCK`; interruptible I/O/lifecycle and fresh
authority checks must be designed before exposing a live connector. Host owner
and trusted controller remain trusted; this cannot establish historical file
provenance or defeat a malicious host kernel/admin.

Primary interfaces checked against the [Linux openat2 manual](https://man7.org/linux/man-pages/man2/openat2.2.html),
[open manual](https://man7.org/linux/man-pages/man2/open.2.html) and
[Python descriptor APIs](https://docs.python.org/3.12/library/os.html).
The local x86-64 header declares syscall437 and three uint64 fields (24 bytes).
No upstream application code or new dependency is incorporated. No new Linux7.2
flag is assumed. Actual component evidence and remaining gaps are recorded in
the focused design document; this ADR changes no accepted release gate.
