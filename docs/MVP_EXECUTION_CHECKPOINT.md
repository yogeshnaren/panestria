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
| #72 | Scoped protected bytes, actual process interruption and bounded locks | 888 / 38 | 62765d0 |
| #73 | Internal bounded MCP registered-check protocol, fixture authority only | 936 / 38 | 0e01e82 |
| #74 | Actual private bounded Unix socket and stdio relay, fixture authority only | 983 / 38 | 435d95f |
| #75 | Actual durable required read check, policy/lease fencing and report proof | 1010 / 38 | 848414b |
| #76 | Actual pinned PUBLIC subscription MCP read conformance | 1059 / 40 | f933999 |
| #77 | Bounded public HTTPS transport; actual TLS and downgrade denial | 1114 / 43 | 9f54d73 |

Current verified main: 9f54d73b75f52a834186697913fde606f69c766f; latest CI
run 38822704320 at exact head ec96f0e. PR #62's earlier run exposed an older Ask
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

1. Finish `task/research-isolated-reader` with exact-head CI/review. Fixed strict
   UTF8/text and HTML tokenization now runs in actual nonroot/read-only/network-none
   Docker. At f60fc1a, 31 new checks pass (14 actual container/TLS cases, 17 explicit
   parser/controller guards), plus 134 existing research checks. Actual public
   HTTPS bytes feed the reader and retain raw/text/runtime hashes. Evidence:
   evidence/isolated-research-reader-2026-10-15. PDF remains UNSUPPORTED; HTML is
   tokenizer text without CSS/rendered-table/raw-byte mapping claims. Bytes/text
   stay in memory; durable scoped fetch/source/claim records, protected SourceStore
   lookup, PDF reader and citation/support authority remain next R2 obligations.
   No usable source/citation status or G2/R3 promotion follows from these pieces.
   Protected research bytes are merged, with 34 actual filesystem/process and 79
   contract/text checks plus three existing Build checks. Source/claim metadata,
   actual retained-fetch/reader/SourceStore authority remain next R2 obligations.
   #70's CI retry race and all corrected/historical observations remain recorded.
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

## PDF runtime prerequisite in progress

`task/research-pdf-bundle` is stacked on explicit PR #78 including its CI image
setup correction. At 3bc45f, 13 checks pass: 12 real dependency/filesystem guards
and one actual read-only Docker import/configuration. Pypdf 6.20.1 is frozen and
its minimal BSD source/license bundle is pin-verified before staging. Evidence:
evidence/pdf-runtime-bundle-2026-10-15. No PDF input was parsed, no source/citation
status is enabled, and PDF remains UNSUPPORTED until isolated parser integration
and its resource/malformed/active/encrypted/scanned/table cases are qualified.

## Verified reader follow-up — 2026-10-16

PR #78 merged 0fdebdd541db7e8707d8a71ebbb3d56e8c04f6d9 after exact fd8bc21
CI 38847227775 passed 1144/44 live excluded. First CI lacked the pinned image;
second ran all reader cases successfully but failed the unchanged CI command
allowlist. The reviewed setup command is now listed explicitly; no worker pull
permission or assertion was removed. Failed observations remain in its report.
PR #79 merged 6df98db after exact e7c0683 CI 38847828741 passed 1157/44, with
current reader main included. The dependency bundle's 13 source-bound checks
remain historical and do not themselves prove PDF extraction.

Static PDF extraction is now separately implemented on task/research-pdf-extraction.
At clean dbe4952, 77 component checks pass: 21 new actual Docker PDF cases, 13 new
injected protocol guards and 43 existing reader/bundle checks. Evidence:
evidence/pdf-extraction-2026-10-16. Source-bound checks verify extraction and its
limits only; no SourceStore or source/citation/support authority follows. Actual
immutable source records, retained-fetch composition, privacy/admission, protected
passage resolution and full R1/R2/R3 gates remain work. No owner trial started.

PR #80 merged c03737abab6aca533b865f98926f753d519e3f60 after exact 2a572bc
CI38848382391 passed1191/44 (one upstream synthetic add_js deprecation warning).
The isolated PDF reader is now on main; its source-bound 77 checks remain scoped
component evidence. No provider/model/image download was used.

Source metadata is implemented separately on task/research-source-records,
starting at fetched main and including verified #80. Migration0024 has immutable
full request scope, exact pinned artifact associations with deferred set checks,
same-transaction event publication and guarded downgrade. At clean f611b83,
25 actual source metadata/private-byte/restore/corruption cases PASS. Earlier
7d19eaf passed63 source/request/schema/launcher cases; observations stay separate.
Evidence: evidence/research-source-records-2026-10-16. Every returned record/byte
result explicitly requires actual fetch authority. No source API or citation
pass is enabled. SourceStore actual retained-fetch/reader provenance composition,
protected passage authority, configured search, semantic support and Delegate
controller remain next; R1 gaps and R3/extensions/gates also remain unfinished.

PR #81 merged f714c57fdf89e0354196ec17d2a5bca8070334be after exact a01c66a
CI38849282344 passed1216/44. New source provenance task includes verified main81.
At a114b93, 100 default component checks plus one actual public TLS→isolated reader→
PG/CAS→offline exact quote pass. Generic metadata-only source IDs cannot resolve.
Reader results bind raw SHA/size; immutable capture proof and every retained byte
are rechecked. Results are EVIDENCE_PRESENT only, retaining HTML/PDF limitations.
An event-lock review issue was repaired before publication and requalified with
an actual no-entity-write-after-event-lock guard. Evidence and pre-fix observations
remain separately bound in evidence/research-source-provenance-2026-10-16.

SourceStore only retains already-admitted broker observations; it performs no
network request or permission grant. Actual public-web policy/lease/admission,
outbound query/disclosure accounting, search, claims/support and Delegate remain
required. Retention count/raw bytes are serialized separately. Full R1/R2/R3,
extensions, trusted gate evaluator and actual owner trial remain unfinished.

PR #82 merged c1592ee9cf69a2648e97f43ade91aab170a5ba95 after exact0297e8e
CI38851014658 passed1250/45. The source provenance/retained lookup component and
its separately scoped actual TLS evidence are on main.

Claim evidence is now implemented separately on task/research-claim-evidence,
including verified main82. Migration0026 retains scoped immutable payload/report
pins and only successfully verified capture-bound passages. At clean04b8f09,
127 checks PASS:27 new deterministic claim cases +100 existing source/schema/
launcher cases. Evidence/research-claim-evidence-2026-10-16. Wrong/partial evidence
blocks whole-claim pass and unresolved lineage is RESTRICTED. Fresh offline checks
can invalidate stale source availability without overwriting history. All semantic
support remains NOT_ASSESSED, including draft OPINION and unrelated genuine text.
Actual support/contradictions/calibration, public-web policy/disclosures/search,
Delegate, remaining R1/R3/extensions/gates and owner trial remain unfinished.

PR #83 merged 7521e26 (resolve full SHA) after exact39875f3 CI38852418587
passed1277/45. Deterministic claim evidence is on main; semantic support remains
NOT_ASSESSED. An independent entailment corpus task includes verified main83.
At source3a9067f, 14 fixture/provenance/projection/synthetic-scoring checks PASS.
The72 public human-labeled SNLI cases retain exact source revision/SHA/license and
attribution. No model calibration has run and no release pass is inferred.
Evidence/entailment-corpus-2026-10-16. Actual local/approved-model calibration and
semantic integration remain next, with all original R2/R3 obligations retained.
