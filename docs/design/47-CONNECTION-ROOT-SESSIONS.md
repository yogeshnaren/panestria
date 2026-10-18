# Scoped connection root handles

This is the descriptor-resolution prerequisite for MVP-X09 / AOS-008-S4–S5,
starting from verified main `fc0c52c` (PR97). It has no live connector, API, CLI,
UI, policy or worker wiring. [ADR0004](../../adr/0004-connection-root-lifetime.md)
defines process-local identity and deliberate reenrollment after loss. Connection
reviews remain DECLARATION_ONLY and conformance remains UNVERIFIED.

## Identity and input boundary

Only trusted controller setup can construct `ConnectionRootSession` for a
canonical Actor and explicitly enroll an existing absolute private directory.
The root must be owned by the current UID, mode0700, a real directory and linked.
The helper never discovers folders or creates/chmods owner directories. The
256-bit random reference maps only to a held descriptor, not to a stored locator.
At most16 roots are held per session; all later operations recheck owner/project.
Unknown/foreign/removed/closed references refuse. A reference collision refuses
without replacing the original handle or leaking its new descriptor.

Identity is the opened directory object. Renaming the root or its parent keeps
the same object; creating a new directory at the previous path cannot retarget
the reference. It is not a pathname-following watch. Another session, restart,
restore or reenrollment issues fresh references. Old declaration roots remain
unavailable; do not guess continuity from a path or device/inode pair. Setup must
obtain a new owner review containing the fresh refs before actual runtime use.
No marker, raw locator registry, new DB schema, task state machine or audit event
is introduced. This does not prevent an owner/admin from changing their own host.

## Descendant resolution and bytes

Only the verified Linux x86-64 ABI is supported (syscall437, three uint64 fields).
Enrollment forbids symbolic/magic links in every path component, including the
root. The explicit root can be on its own filesystem. Descendants additionally
use BENEATH and NO_XDEV, so absolute/parent escapes and mount crossings refuse.
Unknown ABI, unavailable libc/syscall/flags and containment uncertainty refuse
without weaker retries or an `openat` fallback.

Names use exact UTF-8 POSIX components: no absolute relative-path requests,
empty/dot/parent components, repeated/trailing slash, backslash, NUL/control,
surrogate, over255-byte component, over64 components or over4095 bytes. Text
length is bounded before encoding/splitting. No Unicode normalization or URL
decoding: distinct actual filenames stay distinct.

Resolve to O_PATH/CLOEXEC/NOFOLLOW first. A returned final symlink is still
rejected by descriptor type. Only an owner-owned, single-link regular file on
the root device, without group/world writes and within the explicit byte cap,
can reach a readable open. FIFO/socket/device/directory objects never reach I/O.
The readable descriptor is reopened from this process's private held descriptor
entry, never from a second unvalidated worker pathname; identity is rechecked.

Two bounded reads of that exact object must agree in length and SHA256. Each
requests at most max_bytes+1; total requested data is at most twice that bound.
max_bytes is a strict integer1..64MiB, not a promise to allocate only64MiB:
first-pass assembly has temporary chunk/join overhead. A second fresh contained
relative lookup plus type/link/size/mode/UID/GID/device/inode/mtime/ctime checks
must match before returning immutable bytes and their hash. Snapshot repr hides
content. Errors expose stable codes, not paths or OS messages. No automatic
persistence, indexing, event, subprocess argument or telemetry contains content.

The original metadata-only implementation missed an actual same-length rewrite
with restored mtime during clean qualification `de5789d`. Its195-case run was
194PASS/1FAIL and remains immutable evidence. The two-read content check fixes
that observation; a separate real-file/injected-coarse-timestamp regression
proves timestamp fields alone cannot determine this result. Two agreeing reads
are conservative observations, **not an atomic filesystem snapshot** against an
arbitrary concurrent writer or historical provenance proof.

## Resource lifetime and limits

Session operations serialize. Removal closes only the selected owned descriptor;
close/context exit/GC close remaining owned handles. All temporary descriptors
close on success or error. Forked use refuses before acquiring a potentially
inherited lock and closes child copies on first use; it does not claim immediate
at-fork closure. CLOEXEC prevents an exec from retaining roots, even if subprocess
close_fds is disabled. An actual owned controller SIGKILL leaves no handle or
locator file to recover; a new session refuses its old reference. It preserves
the original files and requires explicit fresh enrollment.

Lock acquisition has a5-second busy refusal. This is **not hard interruptible
I/O**: ordinary filesystem reads and path lookup can stall, and close can wait
for an operation. Before a live broker uses it, add scoped execution lifecycle,
deadline/cancellation/resource accounting and current authority checks. Do not
present byte bounds or O_NONBLOCK as a wall-time guarantee. A malicious trusted
host/controller can bypass a Python helper; workers must never receive handles
or raw locator access in the eventual OS envelope.

## Observed verification

At clean `dda07c3dfee4e37a1131201c1cf3e5f7f7053113`,196 checks pass17.86s:
80 new filesystem/interface cases and116 existing declaration/real PostgreSQL/
policy cases. No selected live tests are excluded. Ruff, mypy199 source files,
11 import contracts, secret scan and source diff checks pass. Exact raw XML,
source/artifact hashes and earlier dirty/clean observations are in
[the evidence report](../../evidence/connection-root-sessions-2026-10-18/report.json).
The earlier193-pass source `d227c83` and196-pass source `92a8015` remain distinct.

Owned PUBLIC fixtures cover root/parent replacement, Unicode identity, alias/
hardlink escapes, FIFO/socket/directory, concurrent swaps and8 read-time
mutations, cleanup, fork/exec and actual controller death/restart. `/proc` mount
crossing and `/dev/null` type rejection are low-level known-system **metadata
only** probes: no target content is read and neither path is a private-root
enrollment. Coarse timestamps, foreign UID and missing libc/unknown architecture
are explicitly injected seams, not certificates for other systems. Unknown
resolve flags are actually rejected by the current kernel. No bind mount is
created; no arbitrary mount filesystem or hard-I/O-latency qualification exists.

Reproduce the final component qualification with:

```bash
uv run --frozen pytest tests/integration/test_connection_roots.py tests/unit/test_connection_contracts.py tests/integration/test_connection_reviews.py tests/unit/test_public_web_policy.py tests/integration/test_public_web_policy_store.py --junitxml=/tmp/connection-root-qualification.xml
```

Primary API evidence: [openat2](https://man7.org/linux/man-pages/man2/openat2.2.html),
[open/O_PATH](https://man7.org/linux/man-pages/man2/open.2.html) and
[Python OS descriptors](https://docs.python.org/3.12/library/os.html), checked
2026-10-18 alongside actual local syscall headers/runtime. No third-party
application code, new dependency, provider/model/SDK/auth/image download or owner
configuration/service/database change is involved.

## Still required for runtime connections

Enrollment is not authorization to read. A GrantBroker must intersect the exact
owner-reviewed declaration with independently verified capability/account,
configuration/root/origin/action/class/purpose, current policy, lease, byte/call/
cash/wall budgets and any approval. Recheck before future effects, invalidate
stale queued approvals and reconcile in-flight effects without replay authority.
Do not compose BudgetService.reserve's event append with later entity locks;
preserve the existing global event-lock-last rule. Treat unknown cash and quota
observations separately; read does not grant send/spend or training rights.

Scoped owner onboarding, reconnect/review/revoke UI, private locator setup,
narrow secret injection, contained native auth/proxy/MCP conformance, broker
lifecycle and full TC05–TC08 still remain. This primitive completes none of those
gates and does not promote G1/G2/G3 or start the owner trial.
