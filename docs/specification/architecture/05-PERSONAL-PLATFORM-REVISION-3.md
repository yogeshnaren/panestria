# Personal platform specification — revision 3

**Revision:** personal-platform-3, 2026-10-15. **Role:** active, additive build contract with the [phased implementation plan](../../PANESTRIA_PHASED_IMPLEMENTATION_PLAN.md). **Inspected code baseline:** `7f39028a278df6b5b06d1d60df8a0d09c5b56073`. These requirements are planned work, not implementation or acceptance evidence.

The initial deployment is one Linux workstation and one primary owner, with an explicitly enabled private read-only phone companion. R0 remains accepted for its original scope. R1 is in progress, with live obligations pending; R2/R3 are not accepted. The complete MVP ends at R3 plus its gate, 14-day trial and owner acceptance. R4–R7 implementation needs a separate owner decision.

## Authority and preservation

For new work read: the phased plan → this revision and common requirements → selected item/extension plan → current implementation and source-bound evidence. This revision wins over older active planning text on the specific deltas below. Existing obligations remain required. Frozen references, original archives, attached skills and historical evidence are unchanged. Do not use an original downloadable ZIP as a claim that it contains this revision.

The 38 AOS items retain their IDs and primary phases. MVP-X01–X06 remain baseline obligations. New MVP-X07–X14 deliver by R3 even where their owning AOS item originally ships in R1. Historical G0 results are not relabeled or invalidated by this new scope. G1/G2 retain their existing manifests; G3 requires the baseline 124 cases **and 33 new cases, 157 total**. The catalogs contain 93 original plus 21 new slice envelopes. Missing new cases or future node paths are incomplete, never runtime proof.

The canonical check types remain `trusted-command-ref`, `git-diff-path-check`, `policy-decision`, `artifact-exists`, `human-review`, `citation-check`, `rubric-review`. Added case IDs extend their owning AOS case sequence; no second verifier vocabulary or new task-state enum is introduced.

## MVP-X07

### Encrypted owner profile and canonical classification

**Owner:** AOS-011; related AOS-002/007/009/017. **Slices:** AOS-011-S4–S6. **Cases:** AOS-011-TC05–TC08. Sensitive profile mode remains disabled until the boundary passes its checks.

The classification decision is [ADR 0003](../../../adr/0003-personal-platform-classification.md): PUBLIC < INTERNAL < CONFIDENTIAL < RESTRICTED are canonical authorized data classes. UNKNOWN is a deny-only diagnostic, not an authorized goal class. Derived data inherits the strictest applicable source and policy constraints. Runtime PRIVATE is a legacy input, not a synonym chosen silently; unresolved legacy records have effective RESTRICTED treatment with an audited resolution path. Do not rewrite immutable historical rows or relax a contract's egress restriction.

Proposed interfaces are `ProfileVault.read/write(actor, profile_ref, expected_revision)`, `ProfileContext.select(actor, purpose, allowed_fields)` and `ClassificationResolver.resolve(source_ref)`. Use the existing owner/project/actor and UnitOfWork contracts; a model cannot supply its own authority.

An additive PostgreSQL design stores immutable profile revision metadata and an authenticated encrypted blob: owner/project/profile identity, revision/schema version, ciphertext/nonce, opaque key reference, associated-data identity, provenance, classification and retention. The wrapping key is outside the database, backup and worker environment, using an evaluated OS-backed secret store. Locked/missing keys deny sensitive reads and writes. Nonce/key handling uses a vetted authenticated-encryption library, never custom cryptography. Test tampering, cross-scope substitution, rotation and encrypted restore.

Start with a small bounded profile and owner-approved examples. Restricted plaintext must not enter ordinary PostgreSQL FTS, general embeddings, trace payloads, temporary files or model/worker caches outside its scope. The local trusted broker decrypts and selects fields for authorized local inference; remote agents do not receive the raw restricted profile. Retain source/consent/correction/suppression lineage and honest backup/derivative erasure limits. Encryption at rest does not authorize plaintext egress or protect against an already compromised host administrator.

## MVP-X08

### Portable charter, style and model context

**Owner:** AOS-017; related AOS-011/016/024. **Slices:** AOS-017-S4–S6. **Cases:** AOS-017-TC05–TC08.

An editable `StyleProfile` holds approved language/audience/detail/formatting preferences and example references with provenance and classification. An assistant charter requires honesty, calibrated uncertainty, reliability, respectful disagreement and correction. It cannot alter policy. User communication preferences, assistant behavior and optional goal-specific coaching are separate; no hidden psychological diagnosis or autonomous goal to change the user.

Use cognition as an engineering analogy: planner/executive control, bounded working context, attributed episodic memory, reviewed procedural skills, attention/resource control and independent verification. No brain-equivalence claim is required to ship useful behavior.

`ContextCompiler` produces bounded, source-linked, privacy-filtered packs for an eligible model/harness. A local presentation pass may apply restricted style preferences only if it preserves facts, numbers, citations and uncertainty; otherwise abstain. Evaluate readability and owner preference with output length/latency rather than minimizing tokens alone. Tables and diagrams are selected for usefulness. Style skills are versioned reviewed candidates; executable scripts require their own grants. Data-free approved rules can be exported; private examples cannot silently cross to ChatGPT, Claude, Gemini or other clients.

A `ModelManifest` identifies immutable model/runtime/tokenizer/template/quantization/tool/modality/context capabilities and capacity/license/evaluation references. Application-owned memory/profile data remains portable. Active attempts stay pinned; replacement tests compatibility, context reconstruction and rollback before changing new-work defaults. Embeddings and KV caches are not universally transferable. Full adaptive selection is R4; weight adapters may require retraining in R6.

## MVP-X09

### Connection grants and the secret boundary

**Owner:** AOS-008; related AOS-007/009/010/024/028. **Slices:** AOS-008-S4–S5. **Cases:** AOS-008-TC05–TC08.

`ConnectionGrant` binds owner/project, connector and version, account/roots/origins, allowed actions, data classes, budget, expiry/revocation and conformance evidence. Read/write/send/delete/spend are independently authorized. Resolve directory roots and test symlink/alias escape. Selecting a folder or installing a client does not import chats, credentials, agent lists or all application permissions.

`GrantBroker.authorize` and the existing policy/lease checks run at admission and again before future effects. Revocation affects queued and future actions, invalidates stale approvals and reconciles in-flight effects. Use opaque secret handles and narrow injection by the trusted broker; workers do not inherit broad homes, environment, browser profiles, Docker sockets or provider auth directories. Secret scanners supplement effective mount/tool/egress enforcement. Unknown or uncertified adapter capability remains unavailable.

The setup UI shows the exact grant, whether it is certified/expired/revoked and how to disconnect. Initial supported adapters remain explicitly selected. App automation and capability discovery expand separately in R5/R6.

## MVP-X10

### Verified progress and bounded long-horizon repair

**Owner:** AOS-025; related AOS-006/027a/027b/029. **Slices:** AOS-025-S4–S5. **Cases:** AOS-025-TC05–TC08.

`ProgressLedger` links immutable requirement/non-goal/plan versions, milestones, candidate hashes and check/evidence references. Execution status, verified outcome and owner acceptance are separate. Worker narrative, a heartbeat or edited acceptance tests cannot establish completion.

`RepairPolicy` bounds attempts, repeated failure fingerprints, wall time, resources and cost within the approved goal. A new scope/privacy/tool permission or material budget change follows the corresponding authorization flow. Semantic/rubric review supplements deterministic checks at appropriate milestones; correlated models can still be wrong. A stall exposes the reason and remaining work, then terminates or escalates honestly.

Milestone handoffs contain compact source/evidence/model/plan references and clean artifacts rather than an ever-growing transcript. DBOS and the same PostgreSQL database own durable state/event transitions. External process/inference/Git actions retain intent, receipt and reconciliation; exactly-once database commits do not make every external action exactly once. Final verification and approval bind the integrated candidate.

## MVP-X11

### Quota-aware useful work and automatic offline capture

**Owner:** AOS-012; related AOS-006/010/011/026/029. **Slices:** AOS-012-S4–S7. **Cases:** AOS-012-TC05–TC10. This is an MVP capability; it does not depend on completing R4's sophisticated forecasting or R6's trainer.

`QuotaObservation` contains provider/account reference, model/window scope, remaining value and unit when supplied, reset time when supplied, source, observed-at/freshness and confidence. Sources distinguish provider-reported, owner-reported, estimated and unknown. An owner report of “40% remains, resets tomorrow” is usable evidence immediately; record it accurately and resolve its reset time with a timezone. A percentage is not a fixed request/token count. Assess simultaneous session/weekly/model limits independently and account for usage in other clients.

`BackgroundWorkPolicy` versions approved projects/categories, preferred providers/models, regular-use reserve, per-job turn/output/wall/resource bounds, background concurrency, data scope, billing route and cash cap. Start with one bounded background job. Prefer valuable architecture critiques, implementation proposals, bug investigations, test design and research where that provider helps. Increase urgency as reset approaches, update observations through supported means, and yield to foreground work. An answer stays a proposal until its evidence/acceptance permits promotion.

An unknown/stale balance does not mean zero, unlimited or no work. A standing policy can permit conservative bounded best-effort work without a fabricated expiring-capacity or savings figure. Observed exhaustion pauses that route until new eligibility evidence/reset, without retry storms. Supported observations improve precision; no private-endpoint scraping or credentials-as-API-keys assumption is required. Quota units, avoided cash, actual cash and forecasts remain different measures.

No-extra-spend mode requires evidence that the approved subscription route cannot spill into paid API/extra usage. If that boundary is unknown, deny that mode; never change account settings, enable paid usage or switch providers implicitly. A zero API cap does not itself prove the provider's subscription overflow behavior. Existing paid smoke-test permissions are not blanket background spending consent.

`BackgroundWorkItem` references an existing scoped goal/task and immutable policy/model/context. Use existing task/attempt states with explicit waiting/denial reasons, not a parallel authority store. Enqueue, reservation, state and events follow the existing transaction/lease/outbox design. Reconcile ambiguous inference outcomes before repeating a potentially paid request.

`OfflineResult` retains protected input/output references or content, task/context/model/version identity, timestamps, sources, classification, validation, permitted-purpose evidence and retention/deletion lineage. Pipeline: raw candidate → review/verification → approved reference/skill/knowledge item → separately eligible training example. Unverified teacher output is not truth; a model-generated architectural suggestion does not rewrite the approved plan automatically. Eligible retained knowledge can support offline retrieval before any weights change.

`TrainingEligibility` is independently ALLOWED/DENIED/UNKNOWN with provider/agreement/data-rights evidence and purpose. Only ALLOWED, consented, verified examples enter training exports, with development/holdout separation, deduplication and derivative lineage. Current Anthropic consumer terms restrict developing/training competing models; output ownership is not automatic permission to train an external model. Resolve the applicable agreement and purpose before that lane. Ordinary authorized work and reference retention must not be presented as a workaround for a prohibited training purpose. Actual post-training/promotion remains R6.

## MVP-X12

### Private read-only phone companion

**Owner:** AOS-028; related AOS-009/008/029. **Slices:** AOS-028-S4–S6. **Cases:** AOS-028-TC05–TC08.

Reuse responsive Mission Control for owner task/worker status, permitted evidence and a minimal attention inbox. Show last-seen/stale/disconnected information. Read-only device scope denies job submission, approval, writes, grant changes and restricted profile export on the server, not merely by hiding buttons.

The API stays loopback-only by default. A separately enabled private TLS ingress profile terminates authenticated device access through reviewed private networking/proxy configuration, with application authentication, session revocation and exact Host/Origin rules. Private network membership alone is insufficient authentication. Do not silently enable public ingress, wildcard CORS or arbitrary LAN binding. Test actual target phone/browser/network compatibility as separately scoped live evidence.

Do not cache restricted data in a service worker or put sensitive content in notifications. In-app status/inbox is MVP; reliable background push, remote approvals and native wrappers are R5 candidates with explicit data/OS/relay constraints. A workstation must stay online for work to advance; reboot recovery is durable, but phone access does not create an independent executor.

## MVP-X13

### Measured lightweight resources and foreground protection

**Owner:** AOS-018; related AOS-015/016/026/029. **Slices:** AOS-018-S4–S5. **Cases:** AOS-018-TC05–TC08.

Reuse the attached checksum-gated hardware probe and existing native serving/runtime. Record controller, database and model idle/active/peak CPU/memory separately, RSS/PSS/VRAM, disk growth, queue latency, cold/warm first output, verified-success cost and foreground interference. Set host-specific qualification budgets before acceptance and preserve raw measurements. A simulated preset or an estimate cannot establish observed performance.

Use detected Linux cgroup/service/container CPU/RAM/process/I/O capabilities and PSI where available. Bound queues/contexts/worker concurrency, protect controller recovery, load specialists on demand and use event-driven supervision. Model roles need not be separate resident models/processes. CPU/RAM cgroups are not guaranteed per-model VRAM partitions; observe/reserve device memory and fail admission honestly under pressure. Advanced engine/cache/quantization tuning belongs in R4 after paired measurements, not a new OS or inference implementation.

**Owner storage clarification, 2026-10-18:** Opt-in storage notifications are
required in R3. Show capacity, available/reserved bytes and bounded component/
growth observations with source/time/confidence. Keep Docker-wide logical/shared/
reclaimable estimates separate from physical allocation and Panestria attribution;
denied/unknown measurements stay unknown. Handle backup scope/schedules without
double-counting shared snapshot bytes. Warn about large components, low reserves
and expected large writes; integrate with admission and local notifications.
Present keep/defer, inspect, backup-scope/target review, cache-candidate review and
capacity expansion/migration options with scope, uncertain reclaimable range,
rebuild/offline/restore impact and protected dependencies. **Agents must not delete
storage, prune caches/volumes or change backup settings as remediation.** The owner
performs any chosen cleanup. Initial [terminal visibility](../../testing/STORAGE_AWARENESS.md)
is partial delivery; unified notifications and operation preflight remain pending.

## MVP-X14

### Reuse, REA evidence and comparative engineering

**Owner:** AOS-030; related AOS-008/025/028/029. **Slices:** AOS-030-S4–S5. **Cases:** AOS-030-TC05–TC07.

For material reuse/recreation use [Reverse Engineer Anything](https://github.com/morluto/rea)'s investigation workflow: define the feature/question and authorized target, choose source or artifact/runtime evidence, pin identities, retain findings/limitations, select the smallest useful piece, and prove behavior/security/resource compatibility plus rollback. Its [skill](https://github.com/morluto/rea/blob/main/.agents/skills/reverse-engineer-anything/SKILL.md) routes complete source repositories to normal inspection and uses REA engines when packaged/runtime evidence is needed. Tool installation is not an unconditional build dependency or a grant to execute a target.

Keep findings inside the permitted data boundary: local analysis can still send evidence to a remote agent model. REA's license does not grant rights to examined code. Preserve licenses and distinguish reusable source from independently reconstructed behavior. Keep the Python core minimal/readable/typed in one distribution with import boundaries; retain useful browser TypeScript and optimized native runtimes instead of rewriting them. Evaluate consolidation of duplicate custom/server plumbing with parity tests rather than an unconditional rewrite.

A small reviewed Ask/Delegate/Build/style corpus measures task success, independent verification, correction/approval burden, cost, latency and resource use. Record versions, actual sample size and uncertainty. “SOTA” is an evidence-seeking target, not a consequence of a release name or the number of agents.

## R4–R7 preserved expansion

| Phase / owners | Required expansion beyond MVP | Qualification and tradeoffs |
| --- | --- | --- |
| R4 / 031–033 | Rich supported quota telemetry, reset/availability forecasts, adaptive reserve/value scheduling; qualified model replacement; matched engine/quantization/context/cache/offload/affinity experiments; thermal/battery/foreground resource adaptation. | Compare verified-success cost/latency and foreground impact; preserve eligibility/privacy/cash boundaries and reproducible rollback. The MVP queue already works without these optimizers. |
| R5 / 034–035 | Rich portable context/style skills, hybrid retrieval and conflict handling; voice input and separate TTS; desktop quick capture; private push/approved remote actions; per-app browser/desktop/IDE/office/note integrations and specialist packs. | Reuse a stable, independently qualified Byzantium capture/ASR/transcript/evaluation boundary through a versioned adapter. Panestria owns authorization/routing. Protocol mocks do not qualify real speech; voice identity is not authentication; ambient capture is opt-in. TTS is a separate component. |
| R6 / 036 | Labeled replay/holdout/shadow/canary improvement; permitted distillation and optional local LoRA/QLoRA; capability/skill discovery; memory compaction, forgetting and derivative purge; optional user-selected coaching and graph experiments. | Compare prompting/retrieval/skills before training; keep personal facts removable; graph databases need measured query/retrieval benefit over typed PostgreSQL relations. Candidates cannot edit their graders, policy or promotion criteria. Preserve evidence, consent and rollback. |
| R7 / 037 | Multi-user/multi-host trust and recovery, broader CPU/GPU/Apple platforms, optional federation, signed distribution/SBOM/installer/upgrade/encrypted restore, maintained security response and independent review. | Separate user identities/keys/caches/host principals; platform-specific sandbox conformance, fresh install/restore and sustained trial. One-owner MVP is not proof of adversarial multi-user isolation. |

The [coverage register](../../FULL_TARGET_COVERAGE.md) retains all 35 original capability rows and 16 pillars. Product inspirations include Dots' responsibility continuity, firstmate's crew/worktree/event-driven supervision, Grok Bot's routines and Muse's goal/status experience. These are evaluation/reuse targets, not automatically integrated providers or evidence that their internal source/memory is portable. Prefer useful verified local ownership over an unsupported claim to beat frontier reasoning on small hardware.

## Implementation, evidence and rollout

Use the selected [extension slice handoff](../../cursor/prompts/MVP-REV3-SLICE.md) and manifest entry. Proposed interfaces/paths here are implementation ownership, not assertions that files exist. Inspect and narrow each roughly one-day envelope; update exact assertions/node IDs and register any split. Privacy/schema/crypto/egress/approval changes get full failure analysis; low-risk wiring gets a concise checklist.

Additive migrations follow the actual Alembic head, preserve applied history and test real disposable PostgreSQL. State/event/tracked result share the DBOS datasource transaction; external actions remain outside it with receipts. Workers never receive DB or vault keys. A new JSON schema, policy or transport version requires compatibility and stale-client/record tests. Extension code may be implemented with fixtures while independent live prerequisites remain pending; live enablement and release promotion still need actual conformance.

Each feature begins disabled or synthetic, exposes truthful setup/denial/cancellation states and rechecks authority. On failure stop admissions, retain history/evidence/receipts and restore the prior compatible version or forward-repair schema. Never erase confirmed effects, fabricate coverage or treat missing live tests as optional after registering them as required. Register these 33 cases in the gate evaluator: an old 124-case evaluator cannot pass revision-3 G3. Finish the 156 pretrial cases before freezing the R3 trial candidate. AOS-030-TC04 records the subsequent 14-day trial and owner decision; final G3 requires all 157 cases and remains incomplete during the trial. MVP acceptance and SOTA authorization are two separate owner records.

Current source starting points, rechecked for implementation: [Claude limits](https://support.claude.com/en/articles/11647753-how-do-usage-and-length-limits-work), [Anthropic consumer terms](https://www.anthropic.com/legal/consumer-terms), [Linux cgroup v2](https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html), [PSI](https://docs.kernel.org/accounting/psi.html), [vetted AEAD primitives](https://cryptography.io/en/latest/hazmat/primitives/aead/), [REA](https://github.com/morluto/rea).
