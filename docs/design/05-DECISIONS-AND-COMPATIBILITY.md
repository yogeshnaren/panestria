# Detailed-plan decisions and compatibility spikes

The repaired specs and historical architecture are preserved. This user-requested detailed design resolves implementation choices and calls out deltas; Cursor must not hide them by editing originals. Record these as ADRs in the implementing repository before their affected slices.

| Decision | Rationale / implementation consequence | Validation |
|---|---|---|
| D01 namespace panestria | One distribution and package/CLI matching repo; original src/agentos examples remain historical | Install/import/CLI/version tests |
| D02 one PostgreSQL DB + DBOS datasource | State/event/tracked result atomic; separate schemas are ownership, not two task stores | Crash before/after commit; datasource/enqueue API probe |
| D03 identity seq with serialized commit | Global task+goal replay; decimal string at JSON/JS boundary | Delayed writer, gap/rollback and >2^53 fixtures |
| D04 approval consumption relation | Decision and effect consumption are distinct; one effect per exact request | Approve/deny/consume races, changed hashes/actor/project |
| D05 continuation state | Explicit WAITING_APPROVAL→VERIFYING for post-worker merge; no repeated worker after approval | Crash at contract vs merge wait |
| D06 Docker backend + separate verifier | Concrete Linux driver; no credential/network in candidate-code checks | Inside-process filesystem/network/cgroup probes; no unconfined fallback |
| D07 native credential/tool separation spike | Native shell/file tooling cannot read harness login state; edit-only pilot does not certify shell tier | Synthetic credential sentinel; live adapter/OS compatibility gate |
| D08 API bearer vs browser session | Explicit local owner identity and anti-CSRF; same-origin built UI | Host/Origin/missing-header/session/CSRF negative matrix |
| D09 scoped FTS, no raw-prompt retention by default | Useful memory with honest provenance and suppression; richer hybrid lifecycle later | Cross-project, stale/suppressed fact and consent fixtures |
| D10 canonical UTF-8 byte offsets, NFC quotes | One reproducible source/quote coordinate convention; legacy lower-case matcher unsuitable | Non-ASCII boundary, quote edits, re-extraction version |
| D11 SearXNG proposed search frontend | One explicit provider, no silent paid/off-device switch; upstream queries still egress | Instance JSON config/rate-policy probe and query ledger |
| D12 direct typed planner first | Bounded DAG without forcing graph infrastructure; LangGraph adapter only for a measured loop | Cycle/scope/budget/replan tests and output-contract parity |
| D13 independent required test bundle | Worker cannot weaken tests or self-approve | Tampered checks/new tests vs protected fixture tests |
| D14 conservative caps and explicit currency | Cash cap zero until consent; task budgets and API reservation cannot be inferred from plan quota | Concurrent reservation and unknown usage denial |
| D16 canonical approval fields | Historical payload_hash/effect_hash source-clause spelling means effect_digest; active JSON/DB/DTO has only effect_digest | Schema/legacy-field rejection and UI exact-preview tests |
| D17 decimal money at public boundary | max_api_usd is a decimal string (up to six fractional places), normalized for hash/accounting; old prose/YAML numeric examples are migration inputs, not canonical JSON | Reject boolean/NaN/raw float ambiguity and preserve integer micro-USD cap |
| D15 HTML/text R2 scope | No arbitrary JS/PDF execution in reader; unsupported/incomplete visible | MIME/truncation/bomb fixtures and brief uncertainty |

Current documentation checks on 2026-10-11 are source evidence only. Pin exact installed versions with a manifest containing component, resolved version/digest, source URL, supported capability, fixtures/live outcome and operator approval. No latest-version strings or GPU throughput estimates are prefilled.

| Spike | Owner / stage | Required observation | Fail-closed result |
|---|---|---|---|
| DBOS datasource + atomic client enqueue | execution / 003 | Same transaction session, tracking/launch/migration APIs and supported isolation retry | Pause durable admission integration; explicit fallback outbox ADR only |
| Native CLI modes/auth/config/tool isolation | brokers/sandbox / 010,024 | Exact binary modes and sanctioned auth, combined flag behavior, no host auth exposure | Disable affected live worker; synthetic/offline paths remain usable |
| OS backend on actual Ubuntu/kernel/VPN | sandbox / 008 | Effective mounts/UID/cgroups/process and pinned egress policy | Capability unavailable, never host fallback |
| Hardware/local model placement | resources / 015,016,018 | Real VRAM/RAM/power plus model license/latency/quality | Explicit CPU/degraded/no-model state; no hidden cloud |
| Search JSON/policy/retention | research / 019 | Configured SearXNG/API access, consent/quotas/source storage | Delegate setup-required/unsupported provider |
| Independent support judging | verification / 022 | Labeled corpus, safe local model or explicitly eligible route | UNKNOWN/abstain; no fabricated support |
| Phoenix/UI footprint and security | telemetry/UI / 028,029 | Local redacted traces, correct browser auth/reconnect, acceptable resource use | Trace export off or UI error; task truth unaffected; unresolved required UI gate blocks G3 |

Remaining account, pricing, CLI and hardware facts must be rechecked when implementation runs. Planning is authorized here; live vendor use, credential provisioning, OS provisioning and public publishing need their actual scoped user actions. No implementation result is claimed by this document.

## Revision 3 settled planning additions and pending proof

[ADR 0003](../../adr/0003-personal-platform-classification.md) settles classification direction; migration and enablement remain unimplemented. [The active specification](../specification/architecture/05-PERSONAL-PLATFORM-REVISION-3.md) settles R3 owner profile/style, connection grants, verified progress, basic quota/offline capture, private read-only phone and resource/reuse scope. Key-store availability/recovery, native no-extra-spend route proof, actual phone TLS/session deployment, model/context compatibility and target-host budgets need implementation spikes and observed evidence. Their unavailable outcomes disable only the affected capability, preserve independent work and cannot be reported PASS. Rich voice, training, graph/coaching and remote action expansion remain later.
