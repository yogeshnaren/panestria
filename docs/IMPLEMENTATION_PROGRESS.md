# Implementation progress

Updated 2026-10-23 UTC. Build from the revision-3 [phased plan](PANESTRIA_PHASED_IMPLEMENTATION_PLAN.md).
The owner authorizes implementation, focused PRs and verified sequential merge
commits through R3. Stop at the real 14-day owner trial/acceptance; no R4–R7 work.
An implemented component or passing CI is not a release-gate pass.

## Current private phone component

[Private phone ingress](testing/PRIVATE_PHONE_INGRESS.md) now provides an explicit,
disabled-by-default TLS metadata observer with exact private peer/Host/Origin
checks, separate one-use pairing, canonical read-only device roles, one-hour
sessions and local owner device listing/revocation. A closed server-side allowlist
denies task/data mutation and raw artifacts despite a valid cookie or CSRF.
Desktop modes remain loopback-only; no owner listener, certificate or database
has been configured by this work. Migration0040 is required when deliberately
adopting this source. [Component evidence](../evidence/private-phone-ingress-2026-10-23/report.json)
distinguishes actual CLI/PG/TLS/cookies from synthetic CA/peer/clock fixtures and
records a detected remote-bearer mutation. The [phone observer view](testing/PHONE_OBSERVER_VIEWS.md) now supplies explicit
mobile labels, last-seen status, the canonical attention inbox/task timeline and
optional read-only PUBLIC Build evidence. A connected mobile-viewport journey
passed across actual test-server stop/restart, device offline/reconnect,
background-event clearing and canonical revocation. Its [source-bound evidence](../evidence/phone-observer-views-2026-10-23/report.json)
retains the initial unsafe agent-checkout permission failures and their correction;
native/auth/capacity and visibility are explicit fixtures. Initial CI also caught
a same-port server restart failure; stopped-socket reuse now preserves exclusive
live binding and the corrected five-case phone batch passes. Actual target-phone/
private-network trust, remaining adversarial/resource integration and TC08/G3
remain pending. No whole S4-S6 or owner acceptance is claimed.

## Current separately reviewed owner examples

The [curation workflow](testing/CURATED_EXAMPLES.md) now records exact separate
PUBLIC owner-origin, rights and validation attestations, with independent local
training-data-purpose consent. Same-Postgres immutable decisions, current policy,
original expiry, latest denials and withdrawal fence local packet export and
copied-file validation. Read-only inspection supports recovery. UNKNOWN origin
stays distinct; recorded exact-content model provenance cannot be cleared by
relabeling it in this project. No trainer/provider/reference-rights promotion.
[Evidence](../evidence/curated-example-rights-2026-10-23/report.json) preserves actual
PG/CLI/files with synthetic attestations, a detected withdrawal-guard mutation,
the stale schema snapshot failure/correction and four final connected passes.
Owner attestations are not legal/semantic certification. Existing Build archives
stay UNKNOWN/export DENIED; private/provider examples, broader capture and full
TC08/TC09/S6/G3/trial qualification remain open. Owner review DBs were not migrated.

## Current saved performance overview

The [runtime overview](testing/PERFORMANCE_OVERVIEW.md) now combines explicitly
selected private Ask/Build/research capture histories into one terminal view and
optional saved report. It preserves latest observations by owner/project/model/
source cohort, original sample denominators and UNKNOWN values. Distinct original
record inventory deduplicates repeated captures; no pooled benchmark or accuracy
is invented. [22 focused checks](../evidence/performance-overview-2026-10-23/report.json)
pass using actual filesystem/CLI and synthetic measurements, with no new inference.
Full tracing/exposure/resources/phone and cumulative acceptance stay open.

## Current confirmed Build recall integration

[Explicit local Build recall](testing/OFFLINE_BUILD_RECALL.md) now previews a
bounded confirmed PUBLIC archive note and requires exact owner/policy/duration
consent before adding ordinary unpinned memory. Existing offline Ask source,
privacy, retention and suppression rules apply. Concurrent import deduplicates;
stale review, suppression, expiry and owner correction refuse reimport. This
runs no provider/model and grants no training or task authority. The
[source-bound evidence](../evidence/offline-build-recall-2026-10-23/report.json)
retains three passing connected component checks and the first optional fixture
setup error. A subsequent actual cached CPU run retrieved the correct value43
but answered in a sentence despite a number-only request: its strict test FAILED
and is preserved. Default boundary checks pass; quality/latency qualification,
broader capture/rights and cumulative gates remain open. S6 and R3 stay IN_PROGRESS.

## Current background editing authority

[Background worker authority](testing/BACKGROUND_WORKER_AUTHORITY.md) now carries
the exact immutable queue run and worker claim through native launch, tools,
read-only monitoring, independent evidence publication and handoff/completion.
A fresh pinned scoped account observation is compared before disclosure and after
return. Withdrawal, expired original eligibility and foreground work stop future
effects; uncertain claims stay held. [Evidence](../evidence/background-worker-authority-2026-10-23/report.json)
retains original failures and six passing connected checks using actual disposable
PG/Git/MCP/Docker with explicit native/auth/hardware fixtures. The new guard did
not perform live inference, renew billing or enable background work. The [final integration guard](testing/BACKGROUND_FINAL_AUTHORITY.md) now also
checks the current queue/run before trusted assembly, each independent check,
publication and review creation. Actual returned checks remain historical after
withdrawal; a never-invoked final claim releases only through canonical
NO_DISPATCH proof. [Evidence](../evidence/background-integration-authority-2026-10-23/report.json)
preserves the incorrect new release expectation and its correction. Full
connection/secret boundaries, host/resource qualification, original gates and
owner trial remain pending. AOS-012-S5 and R3 stay IN_PROGRESS.


## Current delivery checkpoint

**R3 is building; the MVP has not reached candidate acceptance.** Historical
component sections below preserve what each source established. The current
remaining work is summarized here, so their older “next” notes do not reopen
already delivered components.

| Area | Usable implementation now | Remaining MVP acceptance/integration |
| --- | --- | --- |
| Ask | Offline terminal, approved encrypted profile/style/private examples, optional pinned local identity | Full quality/latency corpus and cumulative runtime qualification |
| Build | Canonical plans, scoped one/two-worker execution, conflicts/final-tree checks, finite repairs, exact owner review/merge | Broader adapter/DAG compatibility and complete B-1/gates |
| Delegate | Question/query staging, explicit collection, retained excerpts, local draft and owner claim review | Actual search is owner-deferred; qualified support/iterative planning and complete D-1/G2 remain |
| Personal platform | Reviewed quota queue, finite runner/controller, offline confirmed-result references, local profile/context and exact connection declaration review/revoke terminal | General authenticated account/root/secret lifecycle and actual conformance, remaining context/capture/rights integration and qualification |
| Visibility/resources | Activity/Build terminals, selected Mission Control modes, opt-in storage admission, saved Ask/Build/research metrics | Unified storage/resource notifications and remaining review/fleet/phone TLS/device integration |
| Release | Original source-bound observations and failures preserved | G1/G2/G3 not passed; paid SDKTC04 deferred, no14-day trial or owner acceptance |

The opt-in storage terminal integration is merged. A separate explicit local
[Mission Control storage mode](testing/MISSION_STORAGE_NOTICES.md) now supplies
owner host warnings/recommendations with fresh pairing and no cleanup authority.
Phone/device integration, broader resource inbox and host qualification remain open. The merged
[CI reduction](testing/CI_REQUIRED_COVERAGE.md) retains functional/security and
mutation-witness checks, conditions repeated legacy/restore regressions and avoids
rerunning an already-proven merge tree. The [connection declaration terminal](testing/CONNECTION_DECLARATION_TERMINAL.md)
now supplies private setup/serving, exact owner review/recovery and fresh-policy
revocation. The review service connects no account/folder/tool; general broker/enrollment,
phone, qualified Delegate and cumulative evidence work remain. Saved metrics are descriptive; unknown
accuracy/cost/time/source never becomes a passing gate.

[Research capture](testing/RESEARCH_RUNTIME_METRICS.md) now saves existing retained
draft lifecycle/token measurements and canonical collection receipt counts, with
latest exact owner judgments in a separate OWNER_REPORTED scope. It starts no
model/search request and changes no database state; missing semantic accuracy,
cash, model-only timing and runtime build source remain UNKNOWN. Source-bound
component checks and original collection errors stay preserved. Full tracing,
exposure, resources and domain/release qualification remain open.

The [initial public fetch grant integration](testing/PUBLIC_FETCH_CONNECTION.md)
now binds anonymous PUBLIC HTTPS GET to an exact reviewed declaration and existing
certified policy/contract/lease checks. Every hop checks its exact origin/current
revision; durable calls/application-byte reservations span goals and survive
uncertainty. A new private template command supports separate proposal/consent;
missing or exhausted grants stop before a new search, and collection stops when
capacity is spent. Anonymous service identity is not authenticated account
onboarding. The [component evidence](../evidence/fetch-connection-grants-2026-10-23/report.json)
uses actual disposable PG/HTTP/CLI/CAS/reader with synthetic HTTPS/certificates;
actual search/runtime qualification, general accounts/roots/secrets and full
S4/S5/TC05–TC08/G2/G3 remain open. Historical plans/certificates are not upgraded.
The first full task CI caught missed joint fixtures and the local startup schema
pin; originals remain retained. The correction preserves exact wrong-schema
refusal and adds no timeout or permission bypass.

The latest Mission Control delivery now provides distinct explicit offline Ask,
PUBLIC Delegate question staging, PUBLIC Build plan staging and separate exact
plan review/acceptance. Canonical pending plan/action review discovery connects
the browser to retained records without a shadow queue or automatic dispatch.
The separate [explicit finite Build mode](testing/MISSION_BUILD_RUN.md) now
connects an accepted PUBLIC plan to durable request/claim/return facts, existing
one/two-worker execution, cancellation and protected final review. Its original
component evidence uses declared native/runtime fixtures, not live qualification.
See [the inbox guide](testing/MISSION_REVIEW_INBOX.md) and
[plan review guide](testing/MISSION_PLAN_ACCEPTANCE.md). All remain component
outcomes: qualified Delegate execution/support, full dispatch/other review
families, remaining personal-platform/phone/resource work, original cumulative
gates and the real owner trial still prevent R3 acceptance.

The [Build review recovery correction](../evidence/build-review-recovery-2026-10-22/report.json)
now distinguishes an in-flight consent request from a settled read/error state.
Pending requests hide the protected preview and expose busy/UNCONFIRMED status;
recovery inspects canonical state after settlement, with no decision retry or
optimistic consent. A deterministic actual browser/PG/Git check retains one later
explicit approval and a separate owner merge. Native/auth/capacity remain fixtures;
this corrects the observed CI failure without granting a release pass.

The owner explicitly resumed implementation through R3 on2026-10-20. The current
Build path has canonical plans/handoffs, admission, conflict handling, independent
final-tree checks, exact owner merge, supported one/two-Claude execution, local
drafts and finite reviewed revisions (PRs127/132–143). Historical actual native
and CPU observations remain bound to their original sources; current runtime
qualification is separate.

Recent usable outcomes are [goal discovery/review/progress](testing/BUILD_REVIEW_TUI.md)
(PR144/146), [opt-in runtime measurements](testing/RUNTIME_BUILD_METRICS.md) (PR147),
[before-claim storage warnings/deferral](testing/STORAGE_AWARENESS.md) (PR148), and
[offline confirmed-result references](testing/OFFLINE_BUILD_REFERENCES.md) (PR149).
Delivered queue components include the [reviewed quota-aware queue](testing/BACKGROUND_WORK_QUEUE.md):
it records exact intent and honest eligibility. The [finite runner](testing/BACKGROUND_RUN.md)
now runs one selected eligible job serially, yields new claims to foreground Ask/held
work, reuses verified handoffs on explicit resume, and retains uncertain claims.
The finite `background next`/`run-next` commands now inspect/select one unstarted
reviewed candidate by declared priority and reported reset, then re-admit it
through that same runner. No timer, automatic resume, fallback or merge is enabled.
The [finite polling controller](testing/BACKGROUND_QUEUE_CONTROLLER.md) now lets
the owner explicitly enable bounded ticks/jobs without manually choosing each
item. Idle ticks perform no provider probe or event write; held review/foreground
capacity waits, while a selected-item denial or failure ends the controller.
No installed scheduler or actual live controller has been enabled.
One [actual queued subscription job](../evidence/background-owner-journey-2026-10-21/report.json)
now completes two serial Claude workers, final checks, exact scripted test-owner
merge, saved metrics and offline references. It uses the owner's reported disabled
extra usage and explicit bounded UNKNOWN-quota policy; no provider-attested billing
or full S5/S7 qualification is claimed. The [account-link workflow](testing/BACKGROUND_ACCOUNT_LINK.md) observes the pinned private Claude login without inference and separately links scoped pseudonymous identity after exact owner review. Actual metadata confirmed a personal Pro login; this is not quota, billing or runtime qualification. Full Delegate support, personal-
platform integration, Mission Control/phone, resource/quality instrumentation and
cumulative gates/real owner trial remain required. A queue candidate is not a
provider permission, and a component/CI pass is not MVP acceptance.
Deliver usable slices and required evidence; avoid unrelated test expansion.

The reproduced intermittent native stop is now addressed by
[read-only authority observations](design/74-READ-ONLY-AUTHORITY-OBSERVATIONS.md).
Monitors no longer serialize through task-row write locks; claim/launch/publication
checks remain locked. The 82 affected connected cases pass with unchanged timeouts.
Current full CI and actual runtime qualification are separate from that component evidence.

| Phase/outcome | Delivered behavior | Remaining acceptance work |
| --- | --- | --- |
| R0 durable synthetic kernel | Historical accepted candidate/G0 evidence preserved | Do not reopen accepted R0 |
| R1 offline Ask | Keyboard Ask TUI with readiness, question/answer, receipts and cancellation; explicit first-run command generates private stable settings; actual CPU terminal/model journey plus historical GPU Ask/restart/pressure observations | Other TUI task screens and cumulative G1 qualification |
| R1 access and one-worker Build | Owner CLI submits bounded PUBLIC work through Claude/Bash; keyboard review shows canonical checks/diff and separately confirms exact merge/cancellation; actual subscription journey retained at its recorded source | Qualify the selected stable runtime/cumulative candidate; owner review remains |
| R1 paid SDK | Owner selected subscription/local-only operation | AOS-016-TC04 deferred, **not passed**; original gate intact |
| R2 query planning, collection and draft | Dedicated owner policy prepare/confirm, new question staging, admitted search/fetch/read, exact retained excerpts, request-scoped diagnostics, private export and bounded local answer drafts with retained citations | Broader iterative planning, qualified synthesis/support, actual service/runtime and complete D-1/G2 |
| R3 complete MVP | Bounded one/two-worker native Build with final review; local proposals, progress/goal TUI, opt-in runtime/storage observations, offline confirmed references and one actual finite queued subscription journey; no accepted MVP release | Broader DAG/adapter qualification; Delegate support, profile/context/connections, automatic background scheduling/rights flow, Mission Control/phone/resources and cumulative gates/real owner trial |

## Usable research path and its boundary

1. [Prepare and confirm a dedicated PUBLIC-web project](testing/OWNER_RESEARCH_POLICY.md):
   display an exact pending grant and separately confirm it as owner, with both
   joint certificate stores revalidated. Existing Ask projects cannot be widened.
2. [Stage a PUBLIC question](testing/OWNER_RESEARCH_SUBMISSION.md): retain the
   question, contract/checks and limits atomically in canonical records, with
   acknowledged private CAS bytes first. It stays CREATED with no I/O or grant.
3. [Propose queries locally](testing/LOCAL_RESEARCH_QUERY_PLAN.md) from the staged PUBLIC question: one bounded retained intent, up to three reviewable queries, private collection-compatible export and separate model-free inspection. One actual cached CPU journey produced valid proposals with measured tokens/request latency; quality and web authority remain unassessed.

4. [Explicitly collect selected queries](testing/OWNER_RESEARCH_COLLECTION.md):
   validate the current joint runtime, reviewed web policy, scope, capabilities,
   zero API cash, lease and deadline. Connect existing search→fetch→isolated
   reader→retained source excerpts. Stop further queries when capacity is spent.
5. [Inspect/export privately](testing/RETAINED_EVIDENCE_BRIEF.md): resolve actual
   snapshots and exact quotes; show fetch/search errors, UNKNOWN receipts,
   reservations and stop/attempt state. HTML is inert and source text untrusted.

6. [Draft locally](testing/LOCAL_RESEARCH_SYNTHESIS.md): one explicitly retained
   CPU model answer draft from up to four bounded PUBLIC passage prefixes. Typed
   claims cite controller IDs; immutable input/output receipts and current policy,
   source, task version/epoch checks fence publication and replay. Private review
   exports preserve omissions and unassessed support.

7. [Review draft claims as owner](testing/OWNER_CLAIM_REVIEW.md): exact bound
   templates, per-claim judgments/citations, separate digest confirmation,
   immutable private corrections and model-free inspection. Judgments remain
   OWNER_REPORTED; they grant no model qualification, task PASS or training rights.

A normal collection stops at **VERIFYING**, goal ACTIVE, with **NOT_ASSESSED**
factual support. Collection generates excerpts. The separate synthesis command generates an
unverified answer draft; neither grants a goal/check PASS. Ambiguous receipts stop in RECONCILING and cannot automatically redispatch.
Late cancellation is preserved; an expired unreplaced attempt may only be fenced
lost. A crash between acknowledged activation phases remains visible and needs
inspection/reconciliation rather than a hidden retry loop.

The connected owner checks use actual disposable Postgres, loopback HTTP, private
CAS, fixed Docker reader and CLI. **HTTPS and qualification certificates are
explicitly synthetic fixtures**. They do not prove installed SearXNG/upstreams,
public TLS, OS qualification or verified factual support. Search setup was
explicitly deferred by the owner. No service, engine, credential, provider/model,
download or paid call is silently selected by this work.

## Guided owner research review

The [claim-review terminal](testing/RESEARCH_CLAIM_REVIEW_TUI.md) now shows the
exact retained question/passages/claims and lets the owner enter verdicts,
controller-source citations and bounded rationales. Full scroll review, validation
and a separate exact-digest confirmation reuse the existing private immutable
review service; cancellation/source changes fence saving and uncertain writes
cannot retry from that view. It starts no model/search request. Judgments remain
OWNER_REPORTED / NOT_QUALIFIED, with no task/training authority. [Physical PTY and
canonical evidence](../evidence/research-review-terminal-2026-10-23/report.json)
uses real disposable PG/CAS/reader and declared synthetic model/fetch setup.
This closes the manual-JSON review interaction gap; qualified automatic support,
planning/runtime/search and the complete Delegate/release gates remain open.

## Current Build integration

Canonical plans/consent/handoffs merged in [PR127](https://github.com/yogeshnaren/panestria/pull/127) with passing exact-head CI39385719878 and verified merge tree.
Accepted plan-node verification now binds checks and literal paths to immutable membership; intermediate NODE_VERIFIED results cannot request, dispatch or complete a protected merge. The unique final task still requires every goal check and exact owner approval. [Component evidence](../evidence/plan-task-verification-2026-10-20/report.json) preserves the scratch-permission failures and the scoped correction. Durable ready-node admission and verified handoff/completion are now implemented: [commands](testing/PLAN_SCHEDULER.md), [source-bound evidence](../evidence/plan-scheduler-2026-10-20/report.json). Across accepted plans, claims cap at two, overlapping paths wait, expiry retains capacity, and protected intermediate handoffs unlock dependencies. Capacity/identity fixtures do not qualify native dispatch. [Final-tree integration](testing/FINAL_TREE_INTEGRATION.md) now connects actual protected sibling results, conservative conflict stops, complete independent final checks and the existing owner review/merge path. [Evidence](../evidence/final-tree-integration-2026-10-20/report.json) includes actual owner-approved protected Git CAS, individually-passing/combined-failing checks, conflicts and cancellation fencing. [Plan lifecycle](testing/PLAN_LIFECYCLE.md) now fences every goal task on cancellation and preserves immutable no-dispatch/confirmed-final release proofs, with [actual component and backup/restore evidence](../evidence/plan-lifecycle-2026-10-20/report.json). Policy revocation does not prevent withdrawal or historical final release. Unknown/claimed processes retain capacity. [Owner plan staging](testing/PUBLIC_PLAN_STAGING.md) now creates a new PUBLIC zero-cash goal, exact checks and frozen proposal without manual SQL, with [actual atomic/replay/CLI evidence](../evidence/public-plan-stage-2026-10-20/report.json). It grants no execution and still requires separate exact plan acceptance. The [native fork/join driver](testing/NATIVE_PLAN_EXECUTION.md) now connects two actual Claude workers and the existing final review path (PR137 merged at `263fa95`). Its [source-bound evidence](../evidence/native-plan-execution-2026-10-20/report.json) retains the initial failures and the passing corrected actual two-worker journey. The accepted assignment now takes priority over the shared goal; independent checks caught attempted sibling edits before the correction. Canonical plans/handoffs use project share guards for read paths so two verifier publications do not upgrade shared locks. Final conflicts are retained canonically and visible in owner status. Direct local proposals and physical-return recovery are now delivered. [Finite same-contract revisions](testing/BOUNDED_PLAN_REVISIONS.md) add fresh exact review without resetting the original budget or relabeling failed history. Broader worker compatibility, qualified planning/repair and requirement/evidence progress remain pending. The actual synthetic demonstration does not complete the full B-1 suite, G3 or human acceptance.

The [Build progress command](testing/BUILD_PROGRESS.md) now saves a private consistent
snapshot and shows a terminal bar of final required checks. It separates current
execution, source-bound verdicts, owner merge and release acceptance. Missing or
altered evidence cannot retain a PASS score, and worker heartbeats cannot advance
it. Repair budgets, held/unknown capacity and repeated unchanged failures remain
visible. The existing Build terminal now loads it with p or a fourth Tab view, without starting workers or changing the exact approval flow. This is partial X10/S4 delivery, with semantic/non-goal assessment, controller repair policy and a unified cross-mode Mission Control still pending.

## Bounded private style examples

[Encrypted owner examples](testing/PRIVATE_STYLE_EXAMPLES.md) now extend the
existing explicit profile editor and restricted offline Ask selection. A small
owner-supplied set retains profile-local refs/ciphertext provenance; it grants no
fact, policy or training authority. The terminal requires scroll-to-end review
and acknowledgment before its separate one-attempt save. Empty examples preserve
legacy bytes, wider profile fields remain intact and correction/suppression
fences a pinned request. [Source-bound evidence](../evidence/private-style-examples-2026-10-22/report.json)
retains the initial zero-case operator error and failed PTY transcript assertion,
the corrected connected checks and one actual cached CPU/PG/crypto request.
Synthetic keys remain explicit; style quality, OS-key/runtime qualification,
cross-harness compatibility and complete S4/TC08/G3 remain open.

## Saved observations from existing Ask requests

[Ask runtime metrics](testing/ASK_RUNTIME_METRICS.md) now reads an exact scoped
canonical receipt and saves allowlisted timing/token/cash metadata into the same
private history used by Build. Ordinary and protected profile cohorts remain
separate; missing/incomplete values and accuracy stay unknown. No prompt, answer,
profile/example value or private content hash is copied. Capture performs no
inference, retry or canonical mutation, and full storage refuses growth.
[Source-bound checks](../evidence/ask-runtime-metrics-2026-10-22/report.json)
use actual PG/HTTP/CLI and declared synthetic key/model/capacity fixtures. This
is partial AOS-029-S2 delivery, not a benchmark, automatic instrumentation,
exposure dashboard or release qualification.

## Project activity terminal

The [opt-in owner storage terminal](testing/OWNER_STORAGE_TERMINAL.md) now
connects private notification settings and existing read-only probes to that
activity view. A warning banner and scrollable recommendations show timestamps,
estimates, unknown values and owner options. Sampling is coalesced and paced;
opt-out/change/shutdown fence publication, and a stalled read starts no second
collector. No cleanup or backup change is exposed. This is terminal-only;
browser/phone host-data consent, persistent history, other write paths and real
host-budget/whole-gate qualification remain pending.

The [project activity terminal](testing/PROJECT_ACTIVITY_TERMINAL.md) now shows
canonical Ask, Delegate, Build and kernel activity for one configured owner/project.
Standalone `activity init/serve/tui` requires no model/cache; its loopback server
mounts no job or approval mutations. The existing Ask terminal opens the same
metadata view with F4/t while preserving its request. Counts, attention and held
Build claims remain observations, with stale/auth failure handling and no content.
[35 connected checks](../evidence/project-activity-2026-10-21/report.json) passed
using real PostgreSQL/HTTP/CLI/PTY and explicit inference fixtures. This is partial
AOS-028 backend/terminal delivery, not React/SSE, phone or release acceptance.

## Local repair draft from stopped Build work

The [local repair command](testing/LOCAL_BUILD_REPAIR.md) now drafts one offline
replacement from canonical stopped tasks/checks, physical-return proof and the
remaining cumulative envelope. It preserves the original contract/inventory,
rechecks the source before publication and requires separate canonical revision
review/acceptance/run/final merge. Held/unknown work, overbudget output and
repeated unchanged failed candidates stop before publication or another model
turn as applicable. [Connected evidence](../evidence/local-build-repair-2026-10-21/report.json)
uses actual CLI/PG/Git/MCP/Docker with explicit model/native fixtures. This is
partial S3/X10 delivery, not qualified repair accuracy or a persistent autonomous
repair loop. General planning quality and original gates remain.

## Durable repair turns and budget

The [repair command](testing/LOCAL_BUILD_REPAIR.md) now records an acknowledged
Postgres intent before each model turn and a protected byte-bound outcome after
return. New directories, processes or plan versions cannot reset the goal's
finite1–2 model-turn cap. Each intent permanently reserves360 seconds against
the original cumulative wall budget; rejected and unknown attempts remain
charged. This is conservative capacity accounting, not measured latency or an
OS interruption guarantee. Unknown return blocks new model/revision work;
`plan repair-turns` and Build progress show it without releasing capacity.
[42 connected checks](../evidence/repair-draft-intents-2026-10-21/report.json)
include concurrency, replay without another model call, lost acknowledgment and
actual backup/restore of the event/index/downgrade guards. Model/native/capacity
identities are explicit fixtures. This closes the persistent accounting gap;
qualified repair accuracy, automatic repair and original G3 acceptance remain.

## Explicit encrypted style editor

The [profile style terminal](testing/PROFILE_STYLE_TERMINAL.md) now lets an owner
edit bounded communication preferences, separately approve local-context use,
review and save through the existing encrypted API at an exact version. Other
fields/expiry remain preserved and undisplayed; a lost write acknowledgment
never repeats the write. This client enables no profile service, key or model.
Default Ask/activity launchers still leave sensitive mode disabled. The separate
[qualified profile service](testing/QUALIFIED_PROFILE_SERVICE.md) now provides explicit opt-in setup using existing keys. The separate
pinned Ask selector is described below. [Connected checks](../evidence/profile-style-terminal-2026-10-21/report.json)
use synthetic keys and real PG/crypto/HTTP/PTY, with no inference. This is partial
AOS-017-S4, not completed personal-platform or style-quality qualification.

## Explicit profile Ask terminal

The [profile Ask terminal](testing/PROFILE_ASK_TERMINAL.md) now pins an approved
profile row/fields/purpose for the existing restricted offline Ask path. It
checks configured scope before disclosure, displays the selection, validates
omitted private response hashes and supports cancellation/receipt recovery
without repeat inference. Transient receipt errors preserve the original
request; canonical resource UNAVAILABLE is visible. [Connected observations](../evidence/profile-ask-terminal-2026-10-21/report.json)
use synthetic keys/model/capacity with actual PG/crypto/HTTP/PTY. Default profile
services remain disabled; the separate qualified launcher is described below. Real quality
and original gates remain pending.

## Qualified personal-mode launcher

`profile qualify` now runs fixed actual isolated OS-key/CPU/physical-HTTP checks
from a clean source and retains an expiring proof bound to source, installed
versions, OS boot and trusted binaries/libraries. `profile serve` requires that
exact proof, explicit restricted-offline intent, existing offline Ask settings
and exact existing key handles. It reuses the exclusive loopback/model lifecycle;
normal launchers stay profile-disabled. Key use and answer publication recheck
qualification; suppression remains available after expiry without loading a key.
The [operator guide](testing/QUALIFIED_PROFILE_SERVICE.md) connects the style and
profile Ask terminals. [Original observations](../evidence/qualified-profile-service-2026-10-21/report.json)
include one actual cached CPU response with an isolated synthetic OS keyring and
four passing connected fixture checks. No owner key/service was configured.
This is supported opt-in component delivery; private examples, context/model
compatibility, connections, quality/resources and original gates remain pending.

## Read-only event timeline

The [activity timeline](testing/ACTIVITY_EVENT_TIMELINE.md) now connects keyboard
goal selection to canonical state and bounded content-free event pages. The same
fixed metadata endpoint reuses existing SSE cursors/reconnect/resync and checks
authority before delivery, including cached frames. It retrieves no event payload,
trace or plaintext fingerprint and offers no mutation routes. Actual scoped
PG/HTTP/SSE/PTY checks and the existing large-cursor/OpenAPI regressions are
retained in [source-bound observations](../evidence/activity-event-timeline-2026-10-21/report.json).
This is partial AOS-028 integration; React/client reconciliation, cross-mode intake/
evidence, private phone scopes and original gates remain pending.

## Next concrete delivery

The [Mission Control observer](testing/MISSION_CONTROL_OBSERVER.md) now adds an
explicit local React/TypeScript/Vite production dashboard with generated OpenAPI
types, separate same-origin pairing, project activity and goal timelines. It uses
existing metadata/SSE APIs and canonical JSON reconciliation; disconnect/resync,
large decimal cursors, expiry and auth revocation remain explicit. It never starts
work or grants completion/approval. The physical Chromium/PG/CLI journey and its
initial logout-lifecycle failure are retained with their original sources. This
is partial AOS-028-S1/S3; three-mode intake, artifact/diff/test evidence, exact
full approval inbox/dispatch, Firefox/phone/TLS/device qualification and cumulative
release evidence remain pending. Original scope/gate requirements are unchanged.

The [protected Build progress panel](testing/MISSION_BUILD_PROGRESS.md) now reuses
the canonical progress service with an explicitly selected existing read-only
store. It shows final required checks, source/report references, held/unknown
capacity and owner merge separately from release acceptance. Actual Chromium,
PG/Git/Docker checks demonstrate zero → verified → UNCONFIRMED after synthetic
protected bytes are corrupted. Native/auth/capacity remain explicit fixtures;
this is no new live qualification or whole AOS-028/G3 pass. The default observer
still reads no protected store and cannot submit work or approve a merge.

The [explicit PUBLIC Build review mode](testing/MISSION_BUILD_REVIEW.md) now
shows the exact protected diff, complete bounded independent report records and
canonical merge preview. A separate session purpose and opt-in root permit exact
CSRF-protected approval/denial records, without mounting generic mutation routes
on the observer. The browser must confirm the digest; stale/changed/expired
content cannot create consent. Offline response ambiguity remains UNCONFIRMED,
with no automatic POST retry. A physical browser journey records consent while
the task remains WAITING_APPROVAL/goal ACTIVE; only the existing separately verified
owner Build CLI performs and confirms the final Git effect. The actual malicious
baseline HTML is inert text; the failed hostile-required-output fixture and its
unchanged verifier rejection remain preserved in
[source-bound evidence](../evidence/mission-build-review-2026-10-22/report.json).
Native/auth/OS/capacity identities are explicit nonlive fixtures. This is partial
AOS-028-S2/S3, no full approval inbox/intakes/dispatch UI or G3/trial pass. The
owner's historical review server on8770 remains unchanged.

The [offline Ask input](testing/MISSION_OFFLINE_ASK.md) now selects the production
dashboard explicitly through the existing local Ask launcher. Its separate
session purpose, one-model lifecycle, RESTRICTED/no-profile questions, literal
memory-only answers, measured receipts, cancellation and uncertain-response
recovery reuse the canonical Ask controller. A receipt with no completed usage
measurement remains unavailable, never zero. The physical Chromium/HTTP/PG
journey checks completion, cancellation, disconnect/recovery and model failure,
with exactly four submitted inference turns and no automatic redispatch/fallback.
Model/process/hardware identities are explicitly nonlive fixtures; runtime and
release qualification remain separate. Default local Ask and the8770 observer
retain their existing modes. This closes the Ask intake portion of AOS-028-F01,
not the three-mode item, G3 or the real owner trial. Original failed observations
and their fixes are indexed in
[source-bound evidence](../evidence/mission-offline-ask-2026-10-22/report.json).

The [distinct PUBLIC Delegate input](testing/MISSION_RESEARCH_INTAKE.md) now stages
an owner-confirmed question using an explicitly selected frozen contract/bounds
and the existing research CAS/submission service. It stores the original required
checks and creates canonical CREATED goal/task/request records without execution,
leases, network or a model. Separate session/config binding, same-transaction
policy/authentication fences and no automatic POST retry preserve that boundary.
Actual browser/HTTP/PG/CAS checks recover one injected post-commit lost response
by reading the same goal, with no duplicate event/request or task attempt.
The input is useful independently of deferred search setup, but does not complete
Delegate collection/synthesis/support or the original R2/R3 gates.

Build input, separate exact plan acceptance and canonical plan/action review
discovery are now delivered in PRs172–174. The current correction distinguishes
acknowledged pre-commit refusals from uncertain commits; its evidence is linked
below. Do not reopen those delivered input/discovery components as new work.

The explicit finite foreground Build handoff is now implemented: see
[design91](design/91-MISSION-FINITE-BUILD-RUN.md), [operator steps](testing/MISSION_BUILD_RUN.md)
and [source-bound component checks](../evidence/mission-build-run-2026-10-22/report.json).
Do not reopen plan staging, acceptance or this one-shot handoff as new tasks.
Next, inspect AOS-017-S5/S6 and the active MVP-X08 scope to connect the existing
reviewed charter/style/model-context records across supported local modes.
The [shared local charter setting](testing/SHARED_LOCAL_CHARTER.md) now connects
ordinary and profile Ask to the same data-free rules with pinned context packs;
this opt-in component does not complete paired style fidelity or ModelManifest
compatibility/replacement. Continue those actual S5/S6 gaps rather than reopening
this local setting or silently exporting private context to another client.
The separate [lossless local presentation](testing/LOSSLESS_LOCAL_PRESENTATION.md)
pass now handles supported plain paragraph layouts with exact content-byte
retention or abstention and saves descriptive timing/length observations. It
does not qualify semantic rewriting, factual support, readability quality or
owner preference. Those S5 quality cases and S6 compatibility remain open.
The [pinned local model manifest](testing/PINNED_LOCAL_MODEL_MANIFEST.md) now
connects the supported CPU/raw-text Ask launcher to retained immutable model,
runtime, containing-tokenizer, template, quantization and capability metadata.
Prepare/claim/provider/completion and canonical receipts retain the exact pin;
incompatible replacement refuses while original memory/context survives rollback.
Actual cached CPU startup/Unix-socket inference/PG/ASGI and one-call receipt replay
passed on the recorded source. This is partial S6 delivery: broad replacement,
other local modes, model/style quality and original gates remain pending. Do not
reopen this supported Ask identity path as another metadata-only task.
The [local Build model pin](testing/LOCAL_BUILD_MODEL_PINS.md) now extends exact
identity to opted-in JSON plan/repair drafts. Public identity export performs no
inference; the selected digest enters the request before durable repair intent,
and actual startup/returned identity must match before proposal publication.
Canonical replay preserves the original identity after new-work settings change.
Source-bound component checks and a separate actual cached CPU JSON journey cover
this path. Research query/synthesis identity and broader S6/quality still remain;
do not reopen completed Ask/Build pinning as new metadata work.
The [research model pin](testing/LOCAL_RESEARCH_MODEL_PINS.md) now connects the
same optional JSON expectation to query/synthesis STARTED intents, actual local
dispatch, retained outputs and model-file-independent inspection/replay.26
connected checks and one actual existing-cache CPU synthesis journey pass on
their recorded sources. The latter retained a cited draft with201 input/46
output tokens and9.54s controller time including startup/stop; support remains
NOT_ASSESSED and its request-state/HTTPS observations were explicit fixtures.
Supported CPU Ask/Build/research identity hooks are implemented; general model
replacement/quality qualification and the other R3 platform/gate gaps remain.
Preserve purpose/classification/model-compatibility and current authority checks;
avoid replacing retained contracts with a second prompt store. Other review
families, full fleet/dispatch integration, connections, resources/phone and finite
release qualification remain. Existing keyboard Ask, research and Build terminals
remain usable; [setup](testing/LOCAL_ASK_SETUP.md),
[Build review](testing/BUILD_REVIEW_TUI.md) and
[Mission Control instructions](testing/MISSION_CONTROL_OBSERVER.md) describe their
separate settings/scopes. Actual search setup is still owner-deferred. Qualified
research planning/support, remaining resource budgets, phone/device evidence and
real owner trial are open; never fabricate certificates or refresh stale consent.

## Explicit finite Build execution from Mission Control

The separately enabled `--build-run` mode now stages/reviews/accepts an exact
PUBLIC plan and offers a separate bounded subscription start action. Request and
controller claim commit before native dispatch; request replay preserves the
original nonce/deadline and cannot adopt a claimed run. Startup, polling, reload
and another nonce cannot restart it. Cancellation reuses canonical plan fencing,
including after policy revocation, and leaves uncertain physical claims held.
Configured storage warnings/deferral are visible without path disclosure or
cleanup. The existing exact protected diff/check/consent panel remains separate
from final owner CLI merge. [Original checks](../evidence/mission-build-run-2026-10-22/report.json)
retain fixture setup/assertion failures and corrected source-bound results. Actual
PG/Git/HTTP/Chromium/MCP/Docker reach two handoffs and WAITING_APPROVAL with one
start POST after a lost reply and no protected-ref change. Native auth/inference,
certificates and capacity are explicit fixtures. No owner service was upgraded;
8770 remains its prior observer. This is partial AOS-028 delivery, not current
live qualification, complete dispatch/fleet scope, an original gate or R3 acceptance.

## Shared local assistant charter

An explicit private `assistant_charter: true` setting now uses the existing fixed
data-free charter in ordinary offline Ask and the existing selected profile Ask
path. General context metadata retains renderer/version/hash; an active prepared
request claims its exact original bytes even when the compiler setting changes.
Private structured style includes one charter and reserves only the actual
overlay byte delta. Mandatory content refuses when it cannot fit. Default false
preserves the original general renderer and enables no profile, key, cloud path,
private export or model replacement. [Source-bound observations](../evidence/local-charter-context-2026-10-22/report.json)
use actual PG/crypto/config/HTTP with explicit non-live provider/process/key/capacity
fixtures and preserve the initial Unix-socket fixture failure. These are context
binding/consent component checks, not paired factual/style quality, owner
preference, actual model latency or an original gate. [Guide](testing/SHARED_LOCAL_CHARTER.md),
[design92](design/92-SHARED-LOCAL-CHARTER-CONTEXT.md). S4/S5/S6 and R3 remain in progress.

## Lossless local layout and saved observations

An independent private `lossless_presentation: true` setting now enables a bounded
layout pass for an existing approved STRUCTURED_RESPONSE_STYLE profile request.
It adds plain-paragraph bullet markers only when the inverse recovers every
original byte; code/tables/markup/ambiguous/partial output abstains unchanged.
Actual profile revalidation after model return fences publication. The canonical
receipt saves formatting time, UTF-8 before/after length and content word/paragraph
counts without private preference values, text or a new unkeyed hash. Original
generation usage is distinct, one inference call remains one, and factual support,
readability quality and preference stay NOT_ASSESSED. [Connected paired evidence](../evidence/lossless-presentation-2026-10-22/report.json)
uses real PG/crypto/HTTP with explicit local provider/key/capacity fixtures, including
late actual profile withdrawal and no-repeat receipt recovery. No owner service
was changed; full S5 semantic quality, S6 compatibility, original gates/trial remain.

## Pinned CPU model identity through Ask

The [manifest guide](testing/PINNED_LOCAL_MODEL_MANIFEST.md) and
[design94](design/94-PINNED-LOCAL-MODEL-MANIFEST.md) describe the optional private
setting. It records public artifact/runtime identities in the existing immutable
context pack, checks the exact digest before inference and before completion,
and shows the original model identity in the receipt without retaining answers
or private profile text. Tokenizer equivalence stays unknown beyond its identified
GGUF container; evaluation remains NOT_EVALUATED. There is no automatic model
replacement, download, new credential, cache transfer or cross-client sharing.

[Source-bound observations](../evidence/pinned-model-manifest-2026-10-22/report.json)
retain28 connected checks and one actual existing-cache CPU journey. The live
case observed one generation (97 input/2 output tokens,3.16s generation time),
canonical identity/replay and owned model cleanup. This single observation is not
a latency distribution, factual/style assessment, physical TCP/profile key-store
qualification or cumulative release pass. S5 quality, remaining S6 replacement/
mode compatibility, private examples/connections, Delegate/phone/resources and
the original gates/real trial remain required. Owner checkouts/services/caches
were preserved; the historical8770 observer remains unchanged.

The [Build model extension](testing/LOCAL_BUILD_MODEL_PINS.md) adds a usable
`local model-manifest` export and optional private planner selection, without
chat/profile export or new permissions. [Its evidence](../evidence/local-build-model-pins-2026-10-22/report.json)
preserves the new fixture generator/state failure and correction, actual committed
repair-intent identity/budget/replay checks, legacy defaults and a separate actual
existing-cache CPU JSON generation. It remains proposal-only, with original
finite repair charges/current authority and separate owner review unchanged.
Actual query/synthesis/general replacement qualification, S5 semantic quality,
remaining platform integration, original gates and real owner trial stay open.

The [research extension](testing/LOCAL_RESEARCH_MODEL_PINS.md) reuses the same
private expectation and public identity export for local query/synthesis work.
Its [source-bound evidence](../evidence/research-model-pins-2026-10-22/report.json)
retains a command collection error separately from26 passing component checks
and a separate actual cached CPU synthesis observation. The actual model produced
a retained cited draft; canonical replay made no second call. It did not qualify
actual HTTPS/search, factual support, private profile keys or a release gate.
New optional artifact metadata preserves legacy canonical bytes by omitting
None. Current model-selection files are read only for genuinely new intents;
history remains independently readable. Full S6 replacement/compatibility, S5
quality, other personal-platform/resource/phone work and original acceptance
requirements remain open.

The full Delegate gate still requires adversarial briefs, qualified semantic
support/contradiction handling, an actual authorized public brief and Ask/Build
independence. Current entailment preflights do not qualify support authority.
Do not repeat unchanged paid/model probes or tune against the held-out evidence.

## Evidence and merge trail

PRs [112](https://github.com/yogeshnaren/panestria/pull/112),
[113](https://github.com/yogeshnaren/panestria/pull/113),
[114](https://github.com/yogeshnaren/panestria/pull/114),
[115](https://github.com/yogeshnaren/panestria/pull/115),
[116](https://github.com/yogeshnaren/panestria/pull/116) and
[117](https://github.com/yogeshnaren/panestria/pull/117) and
[118](https://github.com/yogeshnaren/panestria/pull/118) merged sequentially with
passing exact-head CI, reviewed parents and complete tested trees. Their verified
main endpoint is `cfe09d0463af039b50fb52eab51920037df3a19f`. Subsequent task evidence
remains separately bound to its source; no old report is relabeled:

PR [119](https://github.com/yogeshnaren/panestria/pull/119) added the keyboard Ask
application at merge `7a0e5eb3363d267806221287e3038db0f81a43d7`, after exact-head
CI `39187924099` passed on `bc49faac139141715d8d52234e7a09d3cefc264c`.
Its merge parents and full tested tree were verified. The initial CI failure
was a PTY assertion that read only the first part of a valid redraw; the fix
waits for the complete response. Original failure and live observations remain
source-bound in the terminal report. This did not require another provider probe.

PR [120](https://github.com/yogeshnaren/panestria/pull/120) added private first-run
settings at merge `988324f99ba8496b20e658fc19fe121cb812d9c6`. Exact-head CI
`39188961298` passed on `e368f770e8081d275e70740d368a47235ff8b2ec`; merge parents
and full tested tree were verified. No owner configuration/database was created
by that validation. Current terminal-review observations remain separately
source-bound; provider probes were not repeated for UI changes.

- [Local cited draft synthesis](../evidence/local-research-synthesis-2026-10-18/report.json)
- [Keyboard Ask TUI](../evidence/local-ask-tui-2026-10-18/report.json)
- [First-run CLI](../evidence/local-first-run-2026-10-18/report.json)
- [Build review terminal](../evidence/build-review-tui-2026-10-18/report.json)
- [Owner policy reviews](../evidence/owner-research-policy-2026-10-18/report.json)
- [Owner collection](../evidence/owner-research-collection-2026-10-18/report.json)
- [Owner question staging](../evidence/owner-research-submission-2026-10-18/report.json)
- [Joint runtime](../evidence/shared-research-runtime-2026-10-18/report.json)
- [Admitted fetch](../evidence/admitted-research-fetch-2026-10-18/report.json)
- [Retained evidence inspection](../evidence/retained-research-brief-2026-10-18/report.json)
- [Durable search](../evidence/search-admission-2026-10-18/report.json)

The [R1 owner CLI](testing/OWNER_BUILD_CLI.md),
[operator qualifier](testing/BUILD_RUNTIME_QUALIFICATION.md),
[actual native Bash evidence](../evidence/r1-native-bash-build-2026-10-18/report.json),
[offline GPU evidence](../evidence/r1-offline-qualification-2026-10-18/report.json)
and [process-memory evidence](testing/MODEL_PROCESS_MEMORY.md) remain available.
Certificates are source/runtime-bound: historical native proof is not current
qualification after package changes. Cold TTFT2.04s, warm offline Ask p95.129s,
1.86GB VRAM, restart/pressure and separately observed RSS/PSS are observations at
those sources, not a current cumulative G1 pass or a hardware partition guarantee.

[Phase](phase-tracker.json) and [slice](implementation-slices.json) trackers retain
IN_PROGRESS for partial work. Progress is usable behavior plus remaining
acceptance gaps, not a PR/test count or an invented completion percentage.

## Personal-platform integration: explicit encrypted structured style

[Structured profile style](testing/STRUCTURED_PROFILE_STYLE.md) now connects a
closed language/audience/detail/formatting preference contract to approved encrypted
communication data and restricted offline Ask. Renderer2 binds exact ciphertext,
source, request and policy; a fixed assistant charter stays separate from private
preferences. Ordinary Ask and legacy profile renderer1 keep their behavior. The
migration permits v2 audit without rewriting history and refuses lossy downgrade.

[Source-bound checks](../evidence/structured-profile-style-2026-10-18/report.json)
include actual crypto/PG, legacy Ask/restore, schema guards and one actual CPU
model prompt with synthetic keys. This is an S4 component; private-example
provenance, style/faithfulness and owner-preference evaluation, model compatibility,
TUI style editing and the remaining R3 integrations are unfinished. No owner
profile/key/service was created or migrated, and no gate/owner acceptance promoted.

Research synthesis PR [123](https://github.com/yogeshnaren/panestria/pull/123)
merged at `54118ec21109de34f80fcd474f9f54614c84195b` after exact-head CI39192849084
passed on5146b47f99b4a6c7328f45e6618f83d4b5d8f9d6 (2047 default tests;56 live
excluded). Expected parents and complete tested tree were verified. Its actual
CPU observation remains separately source-bound; no historical qualification
was relabeled for the merged package.

## Storage visibility and owner recommendations

The [storage CLI](testing/STORAGE_AWARENESS.md) adds read-only capacity reports,
explicit Docker/Timeshift/directory probes and opt-in terminal monitoring. It
warns about pressure, reserves, growth, large selected components and observed
backup-policy changes. Unknown/shared estimates stay distinct. Recommendations
never delete data, prune Docker or alter backups. Monitoring defaults off,
suppresses unchanged warnings and respects settings revocation.

[Component evidence](../evidence/storage-awareness-2026-10-18/report.json) records
54 selected checks, static checks and actual read-only host observations.
This is partial AOS-018-S4/MVP-X13 delivery. Unified notifications, automatic
large-write admission, persistent growth attribution and actual host qualification
remain pending. Original specs and G1/G2/G3 gates are preserved. Private machine
diagnosis and system logs are kept out of Git.

## Two-worker prerequisite delivered: bounded Build DAG preflight

AOS-025-S1 now supplies [typed task proposals and a private-file CLI](testing/BUILD_PLAN_PREFLIGHT.md)
with deterministic dependency layers, exact goal/inventory bindings and conservative
retry-inclusive budgets. [Source-bound checks](../evidence/build-plan-preflight-2026-10-18/report.json)
cover valid independent branches/join and refusal of cycles, scope, path, capability,
check and budget violations. S1 is complete as a pure proposal component; AOS-025
remains IN_PROGRESS. It does not launch a worker or confer current authority.

Next within this track: direct local proposal and immutable canonical plan/task
bindings/handoff (S2), then bounded revisions/repair (S3), two-worker admission and
conflict handling (026), and final integrated-tree verification/approval (027b).
Personal-platform charter/context, grants, quota useful-work/capture and Mission
Control/phone/resource integration remain separate unfinished R3 work. No G3 or
owner acceptance is claimed by the preflight.

Structured-style follow-up validation keeps actual local failures visible in
[the compatibility report](../evidence/structured-profile-style-2026-10-18/compatibility-report.json):
source-graph head assertions and observed0032 schema snapshots are corrected;
38 checks passed,4 failed and1 errored on host runtime-start/termination timing.
The actual incremental memory-pressure check passed without relaxing the cgroup
cap or classifier. At that source the feature remained draft pending qualification. PR125 has since
merged separately; that does not retroactively qualify these original failures.
Original CPU/style evidence remains at its recorded source. No gate is promoted.

## Canonical plan and handoff storage component

[Plan storage](testing/CANONICAL_BUILD_PLAN.md) retains exact scoped version1
proposals, owner consent and canonical CREATED DAG references atomically.
Handoffs resolve actual current protected candidate/check/attempt evidence; notes
remain advisory and runtime qualification is NOT_ASSESSED. Accepting a plan grants
no execution, completion or merge authority.

[Source-bound PG/Git/CAS observations](../evidence/canonical-plans-2026-10-18/report.json)
cover scoped immutability, concurrent consent, rollback and fenced handoff; an
initial fixture transition error and its correction remain recorded. The older
style downgrade guard also preserves the new schema. This is partial AOS-025-S2;
direct local proposals, revisions/repair, two-worker admission/conflicts and
final-tree verification remain pending. PR125 has since merged separately; its older host timing failures remain
unqualified observations at their original sources.

## Native two-worker delivery evidence

PR137 connects inventory declarations, explicit accepted-plan execution, scoped native contexts, verified handoffs, final-tree checks and exact owner review. At clean `6a1f39c`, 8 affected default checks passed, 11 actual OS/subscription qualification checks passed, and one actual two-Claude journey passed in22.29seconds. The two native disclosures preceded both returns; actual Docker tools edited separate files; wrong approval digest failed; the exact protected merge completed and all plan claims released. A prior 36-case compatibility run at clean `ca357e3` passed. Original failed native protocol and sibling-scope runs are preserved in the report, not promoted into passes. Default fixture checks are separate from real native evidence. Paid SDKTC04 remains DEFERRED. Full revision-3 code/integration and cumulative release qualification still remain; the real owner trial has not started.

## Direct local plan proposals

The [offline planner](testing/LOCAL_BUILD_PLANNER.md) now produces bounded editing assignments and a trusted compiled final verifier without a graph runtime, DB writes or worker admission. It preserves private frozen inputs/response/model/token/latency/proposal records and requires separate canonical stage/accept. [Evidence](../evidence/local-build-planner-2026-10-20/report.json) at clean `256be15` records39default checks and one actual CPU-model draft PASS19.63s (17.46s generation,560input/95output tokens). Original invalid graph output and a fixture error are retained, not promoted. This is the direct proposal component of AOS-025-S2; general planning quality, canonical bounded revisions/repair, qualified inventory and cumulative TC02/G3 still remain. Next concrete task is physical-return reconciliation and finite repair/version admission; uncertain work must not be retried merely because a lease expired.

## Final-controller recovery boundary

[Final integration tracking](testing/FINAL_INTEGRATION_RECOVERY.md) adds a committed invocation before trusted assembly/checks. Plan cancellation therefore retains active verification capacity, and an uncertain cleanup receipt cannot publish PASS, approve, release or redispatch. Historical return remains separate from current acceptance. PR139 merged at `8a46cfc` after all six exact-head CI checks. This is the prerequisite for safe failed-work release and bounded repair; physical UNKNOWN/native recovery and the full cumulative gate remain pending.

## Confirmed-return capacity release

The [owner return-release command](testing/RETURNED_BUILD_RELEASE.md) now distinguishes confirmed stopped failures/withdrawn final reviews from UNKNOWN work, retains immutable receipt-bound proof and grants no retry, PASS or merge. Actual [component and populated restore evidence](../evidence/returned-build-release-2026-10-20/report.json) records4core cases and28overlapping restore/readiness/canonical-plan cases at their actual sources. The new0036head/snapshots were captured from actual disposable PostgreSQL; owner databases/services were preserved. The next concrete AOS-025 outcome is finite same-contract plan version/repair accounting after safe release, while true unknown or unproven verifier work remains held. G3 and the real owner trial remain open.

## Local proposal execution bridge

A controller-compiled one-edit plan can now use the existing native run and final-review path alongside two independent edits. This closes the small-goal gap between the local draft format and execution; no synthetic second editing task is needed. [Observed bridge behavior](../evidence/local-plan-native-bridge-2026-10-20/report.json) covers compiler→canonical stage/separate acceptance→real scoped tools→complete final checks→scripted exact owner merge, plus unsupported dependent-graph refusal. Provider/model/auth/capacity observations are fixtures in this component, not new live qualification. General DAGs/second adapters and full R3/G3 remain pending.

## Storage warnings now guard new native-plan work

[Opt-in Build storage admission](testing/STORAGE_AWARENESS.md#connect-storage-policy-to-canonical-native-build)
now checks actual device capacity before inventory materialization and each new
worker/final-verifier claim. Initial/changed CLI warnings precede new work;
critical/unknown/mismatched/reserve-risk observations defer without new claims.
The planning write estimate is not an OS cap or disk reservation.

[Actual component observations](../evidence/build-storage-admission-2026-10-21/report.json)
show unchanged canonical state under initial deferral, private-policy revocation,
real verified handoffs retained when pressure stops final work, and explicit
resume without rerunning completed workers. Native/auth/capacity are fixtures.
No deletion/pruning/backup-setting change. Other write paths, growth attribution,
unified inbox and actual host qualification remain pending AOS-018-S4/S5/X13.

## Opt-in measurements from actual Build runs

[Runtime Build capture](testing/RUNTIME_BUILD_METRICS.md) now saves private
canonical invocation lifecycle p50/p95, protected receipt availability and
independently confirmed final required-check fractions using the existing
performance-history format. Normal-return native-plan capture is explicitly
opt-in; manual capture is available for an existing goal. UNKNOWN invocations
supply no returned-latency sample, and accuracy/actual cash stay UNMEASURED.

[Source-bound component checks](../evidence/build-runtime-metrics-2026-10-21/report.json)
verify actual PG/CLI/MCP/Docker/storage behavior with labeled native/auth/capacity
fixtures. Full history refuses growth without changing the canonical outcome or
launching another worker. No raw prompt/code/response/credential logging or
storage pruning. This is partial AOS-029-S2; cross-mode instrumentation, qualified
quality, resource/token/cash/exposure views and G3 remain pending.

## Confirmed Build results retained for offline reference

[Offline Build capture](testing/OFFLINE_BUILD_REFERENCES.md) now saves exact
contract/diff/final-check evidence only after a canonical PUBLIC Build reaches
independent confirmation and exact owner merge. Automatic capture is explicitly
opt-in; manual capture can retain an already confirmed goal. A copied private
archive can be inspected, including its escaped diff, without DB/Git/native
credentials. Capture failure leaves the confirmed merge intact.

[Actual component observations](../evidence/offline-build-reference-2026-10-21/report.json)
cover scope, byte integrity, deduplication, standalone restore and full-history
refusal with labeled native/auth/capacity fixtures. The purpose is owner-local
reference; training eligibility remains UNKNOWN and export DENIED. No automatic
knowledge promotion, provider/model identity invention or training. This is part
of AOS-012-S6; the useful-work queue, other capture modes, rights-reviewed eligible
examples, retention/retrieval integration and G3 remain pending.

New [schema2 captures](testing/OFFLINE_BUILD_REFERENCES.md) retain the original
canonical request/configuration hashes and distinguish recorded requested model
alias from CLI-reported startup model. Missing original observations stay unknown;
old archives are unchanged and readable. [Source-bound checks](../evidence/offline-invocation-identity-2026-10-23/report.json)
cover actual process/PG/Git/Docker/archive/recall behavior with synthetic native
identity frames. This is one S6 metadata outcome, not full model-context
reconstruction, live model qualification or R3 completion.

## Quota-aware queue intent without implicit dispatch

[Background queue review](testing/BACKGROUND_WORK_QUEUE.md) now drafts private
requests from accepted PUBLIC plans, records exact owner-reviewed intent in the
existing immutable event ledger, and supports replay-safe enqueue/withdrawal and
bounded scoped inspection. Quota windows/lanes and matching-unit regular-use
floors remain separate; explicit unknown best effort cannot erase earlier
observed exhaustion. Current task/held-capacity/Ask state protects foreground
eligibility. There is no parallel authoritative task-state store.

[Component observations](../evidence/background-queue-2026-10-21/report.json) use
actual PG/CLI/races/rollback and a real held lease, with explicit synthetic quota/
billing/capacity values and zero native/provider launches. A scheduling candidate
has execution authority NONE and runtime/account/no-spill qualification NOT_ASSESSED.
Actual authenticated binding, one-job dispatch/reservation/yield/reconciliation
remain next; AOS-012-S5/full TC06/07/10/G3 are not complete.

## Explicit PUBLIC Build plan input

The [Build intake](testing/MISSION_BUILD_INTAKE.md) now imports or pastes an existing
PUBLIC zero-cash contract/proposal/inventory bundle and stages it through the
canonical service. A separate session/mode, exact PUBLIC acknowledgment, bounded
body and same-transaction session/current-policy fences preserve scope. The UI
shows retained validation and pending consent, recovers a lost reply by plan UUID
without another POST, and grants no acceptance, task, attempt or worker execution.
Existing plan acceptance/run/final merge remain separate owner workflows.
[Connected component observations](../evidence/mission-build-intake-2026-10-22/report.json)
retain initial failures and passing browser/transaction results with their actual
source identities. Physical HTTP/PG/CLI/Chromium uses declared fixture inventory
and explicit reply-loss injection, with no intake execution. Exact-head CI must
pass before merge; full inbox/dispatch, qualified Delegate, phone and original
R3 gates remain pending.

## Explicit plan review and acceptance

The separate [plan review mode](testing/MISSION_PLAN_ACCEPTANCE.md) adds a fresh
session purpose and exact owner acknowledgment of the retained PUBLIC plan. It
reuses canonical digest/expiry/current-policy/membership guards and atomically
creates CREATED tasks and one acceptance. It cannot schedule workers, infer or
merge. Ambiguous acceptance is inspected by UUID without automatic retry;
intake-only sessions still cannot accept. [Connected observations](../evidence/mission-plan-acceptance-2026-10-22/report.json)
retain five passing acceptance/intake/OpenAPI cases and two passing corrected-label
cases at distinct original sources. They use actual PG/HTTP/CLI/Chromium with
explicit lost-reply/expired-consent fixtures and no inference. Exact-head CI must
pass before merge; full inbox/dispatch and R3 gates remain open.

## Canonical pending-review discovery

The [review inbox](testing/MISSION_REVIEW_INBOX.md) shows latest unaccepted plans
and pending action approvals for open goals from retained canonical records.
Bounded expiry/ID pagination remains valid after resolution; metadata includes
expired records without claiming decision eligibility. Reads are transactionally
read-only and add no events. Selection fills the existing explicit plan inspection
form and cannot replace an uncertain operation; action approvals open their goal.
It grants no generic decision or dispatch. Failed/stale/auth-lost views hide rows.
[Connected observations](../evidence/mission-review-inbox-2026-10-22/report.json)
retain three passing canonical/browser/OpenAPI cases and a passing lost-reply
navigation case at its original source. These use actual PG/HTTP/CLI/Chromium
with explicit seeded task/inventory/lost-reply fixtures and no inference.
Exact-head CI must pass before merge. Other review families/full dispatch,
remaining revision-3 obligations and real owner trial remain.

## Correctable intake validation failures

A confirmed pre-commit Build rejection now unlocks correction with the original
plan UUID and a fresh acknowledgment; malformed canonical goal documents return
a bounded validation refusal. Unknown COMMIT/rollback acknowledgments and
post-commit read failures remain unconfirmed and require inspection, with no
automatic stage/accept retry. The marker describes this request, not absence of
an older plan. [Five connected cases](../evidence/mission-intake-rejections-2026-10-22/report.json)
pass with actual PG/HTTP/CLI/Chromium, declared inventory and explicit lost-ack
fixtures, including both existing uncertain reply-recovery regressions. Two
combined inbox/rejection browser regressions also pass after integrating current
main, preserving the uncertain ID guard. Exact-head CI must pass before merge;
no runtime or R3 release qualification.
