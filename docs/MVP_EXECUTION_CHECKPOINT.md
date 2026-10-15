# Panestria MVP execution checkpoint

Updated 2026-10-15. Follow the revision-3 [main plan](PANESTRIA_PHASED_IMPLEMENTATION_PLAN.md)
and its active specification. The owner authorizes implementation through R3,
focused task branches with coherent owner-authored commits, exact-head CI,
review and sequential merge commits. Automatic continuation after usage resets
is authorized. Stop at actual R3 owner trial/acceptance; do not start R4–R7.

## Release truth

R0/G0 retains its source-bound accepted evidence. R1 remains in progress with
G1 not accepted; later gates and most original/extension work remain pending.
The catalog has 157 final G3 cases and 156 pretrial cases, excluding only the
actual 14-day trial/owner decision AOS-030-TC04. Preserve 38 AOS items and 114
slice envelopes. Component CI/live passes do not establish full case assertions,
release promotion or owner acceptance. The readiness AST inventory is navigation,
not a release evaluator. Sensitive profiles remain disabled in default launchers.

## Verified task history

All listed task PRs were reviewed and merged sequentially with merge commits.
Original specs, skills, archives, applied migrations and historical evidence
remain unchanged except additive active-schema/migration/interface updates.

| PR | Outcome | Exact-head default CI | Merge |
| --- | --- | --- | --- |
| #49 | Revision-3 plan/spec baseline | 437 / 34 live excluded | e1664f5 |
| #50 | Read-only readiness inventory | 454 / 34 | d22c9f2 |
| #51 | Legacy PRIVATE cloud denial | 467 / 34 | 2a4db7b |
| #52 | Immutable classification ledger | 471 / 34 | 2f8c983 |
| #53 | Canonical v2 memory/context compatibility | 482 / 34 | b22c46c |
| #54 | Bounded scoped OS key adapter | 516 / 35 | df48548 |
| #55 | Ciphertext vault, lifecycle and restore | 545 / 35 | bbe4268 |
| #56 | Ephemeral approved-field local context | 567 / 35 | 24f1dc0 |
| #57 | Paired browser v1/v2 cookie compatibility | 568 / 35 | 999251e |
| #58 | Explicit scoped owner profile API | 585 / 35 | 26343a5 |
| #59 | Explicit local key setup/reconciliation | 591 / 35 | d545fdb |
| #60 | Restricted Ask overlay/private receipt mode | 619 / 35 | e51df70 |
| #61 | Actual isolated OS-key/local-model qualification | 619 / 36 | edc1bb9 |
| #62 | Explicit audited local-read project setup | 626 / 36 | d5e9068 |
| #63 | Supported private-config local Ask server | 646 / 37 | e3ffc67 |
| #64 | Actual CPU-only admission without unused GPU probes | 649 / 37 | fa1b7b9 |
| #65 | Paired local Ask browser; actual model/cancel/render checks | 656 / 37 | 3e33f15 |
| #67 | Strict pinned native metadata/candidate compatibility | 718 / 37 | e7cb1b4 |
| #66 | Closed bounded research contracts, without fetch authority | 760 / 37 | 0152ed4 |
| #68 | Actual native proposal through verified, approved protected merge | 760 / 38 | 22a048d |
| #69 | Canonical Unicode and exact passage byte checks | 797 / 38 | 4603531 |
| #70 | Immutable scoped request metadata, atomic event and corrected retry race | 810 / 38 | 5ca8fbc |
| #71 | Public-unicast provider gateway and exact peer/scope checks | 854 / 38 | d987e6c |

Current verified main: d987e6c6b44fe9d415d8e9f335dc1493213d0483; latest CI
run 38813199573 at exact head 94bf2c1. PR #62's earlier run exposed an older Ask
downgrade test sharing newer audit data; a schema-only restored isolated guard
test fixed it without weakening audit-loss protection. PR #61 attempt 1 failed one proposal-demo
approval-flow test; isolated actual-PG/Docker reproduction and exact-head retry
passed. Root cause remains unconfirmed and is an R1/G1 follow-up, not a claimed
fix. Query Git/GitHub before continuing. Keep previous
merged branches historical; start new tasks at freshly fetched main or name an
explicit prerequisite. Preserve owner checkouts, review demo, services and DBs.

## Runtime qualification and current setup task

Branch task/profile-runtime-qualification starts from explicit PR #60 and includes
verified main. A new live test uses actual Secret Service + PostgreSQL + paired
ASGI HTTP handlers + actual constrained local model, with synthetic content only.
It asserts network/mount/log/core-dump isolation, one bounded successful model
call, no profile plaintext/fingerprint persistence, and suppression before any
subsequent inference. It preserves all pre-existing model resources rather than
reaping them. See [scope and commands](testing/PROFILE_RUNTIME_QUALIFICATION.md).

The observed component pass does not enable profiles or complete TC06–TC08.
Source-bound evidence lives in evidence/profile-runtime-2026-10-15. Exact-head
CI, review and merge completed in PR #61.
Earlier source-bound key/vault/context/CLI evidence stays intact in evidence/.

## Exact next work

1. Finish the scoped protected-byte task (`task/research-blobs`) after exact-head
   CI/review. At source bdfca98, 113 focused checks passed (34 actual filesystem/
   process checks + 79 contracts/text); three existing Build evidence checks also
   passed. Actual child exits around publication, exact-byte retry, cross-process
   lock contention, 2 MiB limits, unsafe links/nodes/permissions and corruption are
   covered. It provides protected plaintext, not encryption or fetch authority.
   Source-bound reports are in evidence/research-blobs-2026-10-15. Next: immutable
   source/claim metadata plus actual retained broker fetch/reader/SourceStore
   integrity before any usable citation or Delegate route. AOS-013 stays partial.
   #70's first CI exposed a real secondary unique-index retry race; all-constraint
   conflict arbitration and 24 concurrent pairs corrected it. The passing exact
   CI has 810 tests; failed CI and earlier source-bound checks remain preserved.
   #71 also rejects site-local/documentation/zone/mapped addresses that older
   runtime flags can classify as global; 53 targeted + 2 actual Docker/TLS checks
   are preserved, alongside full default CI. No full AOS-008/G1 promotion.
   The temporary agent checkouts disappeared during the allowance wait; cause is
   unknown. Published changes/evidence were recovered into an independent clone
   at /tmp/panestria-pr-integration. Preserve owner checkouts, legacy Git worktree
   references and services. Do not assume an old demo is running from a missing
   temporary directory. Local Ask services are explicit opt-in; profiles stay off.
2. Complete explicit opt-in local profile setup/launcher, full key lifecycle and
   encrypted restore/forgetting/grant boundaries and whole privacy cases. The
   ordinary ContextCompiler stores metadata/digests, not prompt bodies; profile
   values must bypass its search/fingerprint path. Preserve the v1 Ask contract.
3. Reconcile remaining R1 source/live/gate gaps, then original R2 Delegate and R3
   two-worker Build plus all revision-3 extensions in dependency order. Quota-aware
   useful work/offline capture, grants, progress, phone and resource obligations
   remain MVP scope. Do not disappear them into a SOTA backlog.
4. Run all 156 pretrial cases with actual required evidence before candidate
   freeze. Only then begin the actual 14-day owner trial/acceptance checkpoint.

## Execution boundaries

Use disposable uniquely named test databases/containers and exact cleanup.
Preserve owner DB ports 55432/55438 and demo 8871; R1 tests own their fixture on
55439. No provider calls, owner keyring changes or paid inference were needed
for these privacy components. Existing Claude Code/Anthropic and USD1-total
synthetic SDK smoke permissions remain scoped; no new provider credentials,
implicit fallback, paid background overflow, reset credits or training.
Continue independent work while live prerequisites wait. Checkpoint before
usage exhaustion; resume automatically without asking again. Never manufacture
evidence, a release pass or the actual owner trial. Sources under the mirrored
ChatGPT project's sources directory remain read-only.
