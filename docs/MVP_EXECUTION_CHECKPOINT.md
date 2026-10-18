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

PR #84 merged0938b24 (resolve full SHA) after exacte71e67e CI38853379717
passed1291/45. Human-label corpus/scorer is on main. Local entailment observation
is separately implemented on task/research-local-entailment, including verified84.
At bf3cb42,24guards +2actualfold-observation checks PASS infrastructure; model
quality is NOT QUALIFIED. Held-out21/36correct; supported precision12/24=50%.
Claim support remains NOT_ASSESSED. All72 successful-run calls/predictions are
source-bound; earlier reporting failure retained with unknown completed-case
count. No model downloads/cloud inference/credentials/training. See evidence/
local-entailment-2026-10-16 and design35. Better verified semantic path, all original
research/policy/gates and R3/extensions remain required; do not promote this model.


### 2026-10-16 05:25 UTC — public native entailment preflight

PR85 merged41458fe after exact head59e8c00 CI38854342553 PASS1301/47liveexcluded;
actual local Qwen support precision50% remains unqualified. Native probe source
98927690d37bd0b73a07278957db6e142fb14389:118 guards PASS, two actual PUBLIC Claude
Haiku4.5 folds PASS104.09s;31/36 calibration,33/36 heldout,12/13supported precision,
one falseSUPPORTED. Evidence/native-entailment-2026-10-16 preserves actual hashes/
metrics and failed05e3284 init profiles14skills/43slash commands. Corrected launch
explicitly disables setting sources/slash/skills/MCP/hooks/memory/instructions,
checks immutable files and hostile markers. Four CLI processes attempted total,
72recordedpredictions, rejected-process inference count UNKNOWN; no SDK/private
payload/fallback/training. Successful observed overageFalse, actual cash/quota
UNKNOWN. Small preflight is not semantic/G2 certification; supportNOT_ASSESSED.


### 2026-10-16 05:30 UTC — explicit public-web policy component

Source63555c90aa642d24b39d909f7f19ca399e9c32fd:52 policy/actual disposablePG checks
PASS3.85s, Ruff/mypy186/11imports/secret scanPASS. PUBLIC-only explicit destination,
external-send action, separate provider permissions, all axes/scope/certificate
checks and owner reviewed revisions/revocation. Existing prechange canonical hash
fd00816f0a18bdda6726bfbbd9a8ea0014aed99b4373e1904b72adb014948540 preserved.
Evidence/public-web-policy-2026-10-16 includes clean source/artifact pins and initial
development collection failure (same test module basename, no tests executed;
renamed integration module). No network/provider call, live certificate, runtime
policy/grant, schema migration or release promotion. Search/disclosure/grants/
lease/budget/actual OS broker admission still required. Started from main41458fe,
independent of pending native preflightPR86; integrate verified main before CI.


PR86 merged307371587fc470b335db762163632449ab2efaaf after exacthead3e80b8c
CI38855712327 PASS1318/49liveexcluded (one upstream pypdf deprecation warning).
The public-web policy branch integrates that verified main before publication;
only appended checkpoint text conflicted, and both histories are preserved.


### 2026-10-16 — scoped connection declaration/review component

PR87 merged66cf31c after exactbb06fa4 CI38856594072 PASS1365/49; post-merge
main CI38857394253 also PASS. Current task starts from that freshly fetched main.
At clean b41ee6682e3a6ff33fbe282d5f4bc952272c07d1,81 focused contract/actual PG/
policy/setup checks PASS27.32s, Ruff/mypy189/11imports/secret scanPASS. Migration
0027_connection_reviews has immutable owner proposals/decisions/revisions and a
monotonic pointer with deferred exact review/version consistency. APIhead27 and
both actual schema snapshots1048lines were refreshed on unique owned PG32771.
Evidence/connection-reviews-2026-10-16 retains source/artifact pins and earlier
orphan-decision and old restore-guard failures without relabeling them.

Manifests constrain declared connector/config/account/root/origin/action/class/
budget/expiry; owner digest/version/policy review, real expiry/replay/concurrent
races/rollback/dumprestore/downgrade and event-last behavior tested. All outputs
remain DECLARATION_ONLY, conformanceUNVERIFIED and policyCURRENT/STALE. No actual
connector/credential/network/inference/API route is enabled. GrantBroker/capability
and root/account registry, lease/budget/approval bindings/revocation-before-future-
effect/reconciliation, secret/OS enforcement and onboarding UI remain required.
No complete AOS008S4/S5, TC05–08, R1/G1 or R3 pass follows from this component.

### 2026-10-16 10:04 UTC — private native relay component

PR88 is merged at `164812362855ffaf4c0e89f420edc65722696f44`; exact PR head
`494b85d01bec0cc32f03b3c431e4e03a2c381fd3` CI38880978399 passed1434 default
checks/49 live excluded. Fresh-main task/native-egress-relay now adds the
standalone network-none loopback/private-UDS transport. Clean `c6fa589` passes74
focused checks plus one actual public TLS HEAD (no credential/auth/inference/SDK).
Four actual Docker tests include read-only/nonroot/resource/mount observations,
synthetic host sentinel and provider environment separation, host-loopback/direct
TEST-NET denial, forbidden CONNECT, replaced inode refusal and exact owned
shutdown. Earlier deadline/admission test timing failures remain recorded.
Evidence: evidence/native-private-relay-2026-10-16. Native launcher/profile/auth/
MCP integration, task/policy/grant/lease/budgets and conformance still pending.
No G1/G2/G3 acceptance or owner service change.

### 2026-10-16 10:20 UTC — native offline bootstrap component

PR89 merged at `07c6298b5b844145394c053c6701d4e0a8f720da`; exact PR head
`b483f3b73522ca8ec861d64491a96ba176fa6902` CI38884565048 passed1455 default
checks/50 live excluded in391.44s. Fresh-main task/native-bootstrap-capsule
adds closed credential-free version/help checks reusing the existing offline
DockerSandbox/seccomp envelope. At clean `1ae3209`, 63 focused checks pass,
including 32 new cases and 11 actual Docker synthetic-fixture cases. An explicit
actual metadata case passes with two pinned Claude version/help commands, no
auth/profile/gateway/inference/SDK. Snapshot/source mutation, pressure, deadline,
closed-output linger and cancellation after actual Running state reject cleanly.
Evidence: evidence/native-offline-bootstrap-2026-10-16. This is BOOTSTRAP_ONLY;
connected auth/container/proxy/MCP and current policy/grant/lease/budget still
pending. No native task certificate or G1/G2/G3 acceptance.

### 2026-10-16 10:38 UTC — reconcile lost sandbox create replies

PR90 merged at `d0bbd89a7f7a5a49a383cd61b64a369798ea97a9`; exact PR head
`a4f95071e9135179590fa4c0a2db8993ef4fcdec` CI38886468295 passed1487/51 live
excluded in371.48s. The independent task/sandbox-create-reconcile fetched current
main before branching and integrated verified PR90/main before qualification.
Actual Docker plus an injected lost create reply exposed a stopped-container
leak; the original failure is preserved. Launch nonce/profile/image/attempt/name/
purpose/exact-ID reconciliation now removes only observed owned resources and
keeps missing/uncertain outcomes truthful, with no implicit start or retry.
Clean `4abb61d` passes115 focused default checks (29 new), seven actual OS probes
and one actual native metadata case (two version/help commands, no auth/model).
Evidence: evidence/sandbox-create-reconciliation-2026-10-16. A stale planned OS
node caused an initial zero-test exit4; corrected actual nodes passed, and the
plan/catalog mapping/live-required annotation is aligned without status promotion.
The nonce is in memory; durable launch intent/controller-death recovery and all
remaining native/grant/R1/R2/R3 scope are still pending. Owner state unchanged.

### 2026-10-16 11:24 UTC — durable sandbox launch intent

PR91 merged343a84e6577ed691fcd487d54ff866aa0b3bfc29 after exacta7b5470 CI38888539870
passed1516/51 live excluded in467s. The dependent task/durable-sandbox-launch began
from explicit PR91, then fetched and fast-forwarded to verified main before its
implementation commits. New immutable same-PG intent/event admission precedes
Docker create; actual registered-check controllers use the fenced factory. Lost
commit acknowledgment permits zero creates, and start-time lease release denies
execution. Reconstruction reads protected historical scope and reconciles exact
owned resources without retry/task completion.
Clean ec9a43fb68dd5f9da05ad8ac69e184ea09276dd0 passes170 focused checks in217.81s,
including46 new cases/six actual SIGKILL windows and actual admission/dump/restore.
Original34PASS/9FAIL profile witness mismatch and35PASS/1FAIL test-API error stay
separate in evidence/durable-sandbox-launch-2026-10-16. APIhead28/schema1078lines
match actual unique disposable PG32772. DBOS docs rechecked; full workflow/native/
other lifecycle/grant/R1–R3 gates still pending. No inference/credentials/owner
checkout/database/service changes or MVP acceptance.

### 2026-10-16 14:58 UTC — owner quota observation input

PR92 merged `d20361e39c887482aa3ecdea8a55c0b1287357fa` at11:36:27 after exact
`7e18c9c` CI38893797407 passed1562/51 live excluded525.17s. Freshly fetched main
starts the independent task/quota-observations branch. Clean `cdf3e35` passes172
focused checks in214.59s, including67 new quota cases; one existing live case is
excluded. Actual head29/schema1126lines refreshed on unique owned PG32773.
Evidence/quota-observations-2026-10-16 retains source/artifact pins and original
HTTP status/test-expectation failures. Owner input/read/current APIs preserve
source/account/model/window, explicit times/reset, stale/unknown and decimal units;
actual PG races/rollback, HTTP session revocation and dump/restore are tested.
All responses remain OBSERVATION_ONLY; provider/estimate lanes are synthetic
fixtures, not actual telemetry. AOS012S5–S7 queue/reserves/billing eligibility/
offline capture, full grant/native/semantic/R1–R3 gates and trial remain pending.
No provider/native/model/SDK or owner state changed. No release case promoted.

### 2026-10-16 — dependent owner quota CLI

The task/quota-owner-cli branch names PR93/task/quota-observations as its explicit
prerequisite after fetching current main. Shared request models move from API
into contracts unchanged; report/show/current use held private token/input files,
bounded numeric loopback HTTP and validated/redacted output. Clean source in
`evidence/quota-cli-2026-10-16/report.json` passes89 focused checks in9.40s (28 new),
including one actual owned uvicorn HTTP→API→Postgres roundtrip and exact listener
shutdown. Static checks pass. Original69PASS/2FAIL input-mode fixtures and corrected
71PASS stay separate; no guard weakened. No provider/native/model/SDK/owner-state
change or release promotion. UI/actual supported telemetry/queue/capture/full
native/grants/R1–R3 gates and trial remain required.

### 2026-10-18 — native input framing prerequisite

PR94 merged `a65400c5c5d4164f9994e02cd28c58583ea3723f` after exact `a9ac576`
CI38923007712 passed1657/51 live excluded. Main remains at that verified commit.
The agent-owned temporary checkout and unpublished Oct16 frame work disappeared;
cause is unknown. Approval review had also become unavailable because of account
usage, so the publication command never ran. Usage/review availability recovered,
and a fresh independent clone/branch starts from verified main. The owner checkout
remains untouched. No original missing JUnit file is invented or relabeled.

Fresh clean `58b56a36e5388ef982d351cc8793d7fb20f3a9a8` passes41 focused checks
in8.30s, including six actual fixed synthetic parser containers. Ruff/mypy198/
11 import contracts/secret scan/diff check pass. Evidence is source-bound in
`evidence/native-input-frame-2026-10-18`; design44 specifies the wire protocol,
scope and next integration work. All input stays opaque data. Production runner,
profile, gateway and launcher are unchanged; the host-stage controller-crash gap
is still open. This is not native task conformance or G1/G2/G3/R3 acceptance.
No provider/model/vendor CLI/SDK/credentials or owner database/service changes.

### 2026-10-18 — explicit sandbox stdin transport

PR95 merged `238025b168083179f5737719552b0515679d22bc` after exact `d13a524`
CI39089580257 passed1698/51 excluded/one upstream warning437.92s. The dependent
`task/sandbox-framed-stdin` started from explicit PR95, then fetched and merged
verified main with original commits preserved. Closed profile hashes remain
stable; framed input gets a distinct profile binding, inspected effective flags
and single-selector bounded nonblocking input/output with EOF and exact cleanup.

Clean `c1963e29a2577e14b71f6aa9aad0303abacf930b` passes211 focused checks in75.40s,
20 existing live cases excluded;38 new cases include16 actual Docker resource
cases and one actual PG widening denial. Ruff/mypy198/11 imports/secret/diff pass.
Earlier clean206/210 results remain bound to their original sources, before
review added attach-client/exited-state and output-capture guards. Raw evidence
and fixture limits: `evidence/sandbox-framed-stdin-2026-10-18`; design45.

Gateway/launcher/registered-command interface migration and actual gateway crash
proof remain next. The demo's reviewed apply.py reads the old request file and
needs explicit migration; do not silently recreate staged files. Current framed
transport alone does not remove that resource or certify native/grant/G1/G2/G3.
No provider/model/vendor CLI/SDK/auth or owner database/service changes.

### 2026-10-18 — memory gateway and actual controller recovery

PR96 merged `0aeacd5254d3ffe1607a4388a39199378d7abed9` after exact `a18ed587`
CI39090575864 passed1736/51 excluded/one upstream warning510.93s. The dependent
memory-input task began at explicit PR96 then fast-forwarded verified main before
its own commits. Gateway snapshots now stay in bounded memory and stdin, with
versioned registry/profile bindings, proper Python main-module identity and
explicit demo writer migration. Durable authorities automatically supply their
fenced runner factory; there is no host-input stage or file-mode fallback.

Clean `d71ec94` passes289 focused default checks/22 live excluded121.47s. Final
fixture-only `493078f` passes13 explicit synthetic OS cases17.99s, including eight
actual gateway/controller SIGKILL windows with/without lease release. Production/
runtime hashes are unchanged between sources. Ruff/mypy198/11 imports/secret/diff
pass. Evidence/native-memory-input-2026-10-18 preserves exact sources and original
invalid-test-column/module-identity failures separately; design46 defines limits.

Scoped recovery keeps UNKNOWN, prevents another claim, preserves task/approval
state and unrelated matching-attempt resources. No provider/model/vendor CLI/
SDK/auth or owner state changed. This fixes only gateway input staging; other
lifecycles, autonomous liveness, full connected native/grants/semantic/R1–R3 gates
and owner trial remain required. Do not promote this to native or release authority.

## 2026-10-18 connection-root component

PR97 actually merged `fc0c52c9f7d333529a76112d829b8f968b8fb313` after exact
`63e2a5c` CI39091516491 passed1752/51 excluded/one upstream warning543.19s.
Its entire merge tree matched the tested head. The next focused branch starts
from that freshly fetched main with no open PRs or owner-checkout changes.

ConnectionRootSession now provides controller-only owner/project-scoped ephemeral
descriptor enrollment, contained reads and exact cleanup. ADR0004/design47 define
object identity, fresh references/review after loss and no persisted raw locator.
Root enrollment is not a runtime read permission. No connector/API/UI/worker is
wired. Clean `dda07c3` passes196 component checks17.86s (80 new), Ruff/mypy199/
11 imports/secret/source diff pass. Evidence/connection-root-sessions-2026-10-18
keeps all raw observations and source pins, including a real clean-source
same-size rewrite miss at `de5789d` corrected by a second bounded content hash.

Actual controller SIGKILL, fork/exec, namespace replacement and file races use
owned PUBLIC fixtures. No provider/model/SDK/auth/image/owner service or schema
changes. This is not atomic filesystem snapshotting or hard interruptible I/O.
Actual GrantBroker/current authority/budgets/approval/account/capability/purpose,
onboarding/secret boundary, other lifecycles and R1–R3 gates remain unfinished.

## 2026-10-18 connection progress records

PR98 actually merged `1017708f1c1c351d3bcfeb9658709c14cdcff0e6` after exact
`222f154` CI39093271920 passed1832/51 live excluded/one upstream pypdf warning
497.94s. The guarded merge verified currentmainfc0/exacthead/checks/16-file scope/
original source and artifact pins/all six owner authors; both parents and the
entire resulting tree match the reviewed base/head. No runtime connection or
release gate was enabled.

The next documentation-only branch begins from freshly fetched main1017708.
It corrects stale MVP-X09/AOS-008-S4 NOT_STARTED records to IN_PROGRESS and links
original declaration/root component reports in the slice/phase/backlog and main
plan. S5 remains NOT_STARTED, all33 extension cases remain NOT_RUN, G3 retains
157 cases/156 pretrial, R0 remains accepted and R1–R3 acceptance stays pending.
No code, tests, historic evidence, gate manifests or original archives change.
Source docs clarify logical read-request bounds, not physical disk/readahead or
hard elapsed-time claims. Runtime broker/account/capability/source-purpose/
current-authority/budget/approval/lifecycle/secret/onboarding remain outstanding.
