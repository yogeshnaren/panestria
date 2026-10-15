# AgentOS v0.6.1 — Complete Production Build Specification Pack

**Date:** 2026-10-15 · **Active revision:** personal-platform-3 over preserved planning-fixes-1 · **Status:** R0 accepted; R1 in progress/live gate pending; R2/R3 draft implementation; R4–R7 planning only.

**Purpose:** There are 38 active build specs: original IDs AOS-001–037 with AOS-027 split into 027a/027b. Original source archives and the frozen architecture remain preserved. The full SOTA architecture is preserved as an unchanged reference; R0–R7 gates specify **when** capabilities ship, not what to remove.

Build from the [main phased plan](../PANESTRIA_PHASED_IMPLEMENTATION_PLAN.md) and [active revision-3 contract](architecture/05-PERSONAL-PLATFORM-REVISION-3.md). Eight added R3 obligations extend the original 31 MVP items with 21 slices and 33 cases; the full MVP gate now requires 157 scenarios. Original archives/reference architecture remain historical, checksum-preserved source rather than updated downloadable revision-3 bundles.

## Read first

- [Change log and settled planning fixes](CHANGES-planning-fixes-1.md)
- [Common requirements](COMMON-REQUIREMENTS.md)
- [Canonical acceptance types and skill migration](architecture/04-ACCEPTANCE-CHECKS-AND-SKILL-MIGRATION.md)
- [Original skills archive](attachments/agentos-skills-v0.1.0.zip) and [observed inspection/test report](attachments/SKILLS-INVENTORY.md)
- [Checklist planning template](templates/IMPLEMENTATION-CHECKLIST.md) for AOS-001/004


- [Frozen full target architecture](references/AgentOS_v0.6.1_Architecture_Baseline.md) — unchanged v0.6.1 source.
- [Architecture invariants, asset provenance, ADRs](architecture/00-DECISIONS-AND-INVARIANTS.md)
- [Canonical database, API, task and event contracts](architecture/01-CANONICAL-DATA-AND-API-CONTRACTS.md)
- [Portable Agent Skills and MCP integration](architecture/02-AGENT-SKILLS-AND-INTEROPERABILITY.md)
- [Full SOTA target coverage](architecture/03-SOTA-CAPABILITY-BLUEPRINT.md)
- [Reusable per-item implementation planning prompt](templates/IMPLEMENTATION-PLAN-PROMPT.md)
- [Change-request template](templates/SPEC-CHANGE-REQUEST.md)

## Stage/release build specifications

| Release | Role | Entry |
|---|---|---|
| **R0** | Accepted kernel proof; historical evidence retained | [Build specification](releases/R0-KERNEL-PROOF.md) |
| **R1** | IN_PROGRESS personal alpha; G1/live evidence pending | [Build specification](releases/R1-PERSONAL-ALPHA.md) |
| **R2** | DRAFT research alpha: safe Delegate | [Build specification](releases/R2-RESEARCH-ALPHA.md) |
| **R3** | DRAFT expanded MVP: multi-agent, personal profile, quota capture and read-only phone | [Build specification](releases/R3-MULTI-AGENT-ALPHA.md) |
| **R4** | DRAFT Adaptive quota and compute | [Build specification](releases/R4-R7-SOTA-EXPANSION.md) |
| **R5** | DRAFT Context and desktop | [Build specification](releases/R4-R7-SOTA-EXPANSION.md) |
| **R6** | DRAFT Evaluated adaptation | [Build specification](releases/R4-R7-SOTA-EXPANSION.md) |
| **R7** | DRAFT Portable public distribution | [Build specification](releases/R4-R7-SOTA-EXPANSION.md) |

## Active backlog: 38 specs (original AOS-027 split into two)

| ID | Release | Status | Deliverable | Depends on |
|---|---|---|---|---|
| [AOS-001](specs/AOS-001.md) | R0 | COMPLETE | Repository scaffold, developer toolchain, CI and local services | — |
| [AOS-002](specs/AOS-002.md) | R0 | COMPLETE | Goal contracts, tasks, attempts and database migration v1 | AOS-001 |
| [AOS-003](specs/AOS-003.md) | R0 | COMPLETE | DBOS-backed durable single-task execution and recovery | AOS-002 |
| [AOS-004](specs/AOS-004.md) | R0 | COMPLETE | Synthetic worker, isolated Git workspace and deterministic verification | AOS-003 |
| [AOS-005](specs/AOS-005.md) | R0 | COMPLETE | Minimal goal/approval API and CLI end-to-end synthetic slice | AOS-003, AOS-004 |
| [AOS-006](specs/AOS-006.md) | R1 | IN_PROGRESS | Lease fencing, retry bounds, outbox and external-action reconciliation | AOS-003 |
| [AOS-007](specs/AOS-007.md) | R1 | IN_PROGRESS | Independent project trust, data privacy and autonomy policy model | AOS-002 |
| [AOS-008](specs/AOS-008.md) | R1 | IN_PROGRESS | Sandbox profiles, mount validation and enforceable outbound controls | AOS-004, AOS-007 |
| [AOS-009](specs/AOS-009.md) | R1 | IN_PROGRESS | Loopback API authentication, host/origin hardening and approvals | AOS-005, AOS-007 |
| [AOS-010](specs/AOS-010.md) | R1 | IN_PROGRESS | Hardened Claude Code worker adapter and hostile-repository tests | AOS-004, AOS-008, AOS-009 |
| [AOS-011](specs/AOS-011.md) | R1 | IN_PROGRESS | Source-linked personal memory schema and five-stage use events | AOS-002 |
| [AOS-012](specs/AOS-012.md) | R1 | IN_PROGRESS | Routing outcomes, corrections and cloud-exposure event contracts | AOS-002, AOS-007 |
| [AOS-013](specs/AOS-013.md) | R2 | DRAFT | Research source snapshots, hashes, passage spans and claim evidence | AOS-002, AOS-008 |
| [AOS-014](specs/AOS-014.md) | R1 | IN_PROGRESS | OpenTelemetry correlation, canonical event replay and SSE | AOS-003, AOS-012 |
| [AOS-015](specs/AOS-015.md) | R1 | IN_PROGRESS | Hardware probe integration and versioned capability manifest | AOS-001 |
| [AOS-016](specs/AOS-016.md) | R1 | IN_PROGRESS | Local inference adapter and warm/cold/pressure benchmarking | AOS-011, AOS-015 |
| [AOS-017](specs/AOS-017.md) | R1 | IN_PROGRESS | Offline Ask and source-scoped memory interaction | AOS-011, AOS-016 |
| [AOS-018](specs/AOS-018.md) | R1 | IN_PROGRESS | Offline, degraded-mode and foreground-resource safety tests | AOS-015, AOS-016, AOS-017 |
| [AOS-019](specs/AOS-019.md) | R2 | DRAFT | Search abstraction and SSRF-safe web retrieval broker | AOS-008, AOS-009, AOS-013 |
| [AOS-020](specs/AOS-020.md) | R2 | DRAFT | Quarantined web reader and immutable source provenance | AOS-013, AOS-019 |
| [AOS-021](specs/AOS-021.md) | R2 | DRAFT | Deterministic source citation and exact quotation verifier | AOS-020 |
| [AOS-022](specs/AOS-022.md) | R2 | DRAFT | Claim-support adjudication, contradiction and uncertainty labeling | AOS-021, AOS-016 |
| [AOS-023](specs/AOS-023.md) | R2 | DRAFT | Bounded Delegate planner, research brief output and R2 gate | AOS-019, AOS-020, AOS-021, AOS-022 |
| [AOS-024](specs/AOS-024.md) | R3 | DRAFT | Codex supported CLI adapter and contract suite | AOS-004, AOS-008, AOS-010 |
| [AOS-025](specs/AOS-025.md) | R3 | DRAFT | Build task DAG and bounded LangGraph reasoning/replan | AOS-003, AOS-016 |
| [AOS-026](specs/AOS-026.md) | R3 | DRAFT | Concurrent two-worker scheduler, worktree conflict control and admission | AOS-006, AOS-010, AOS-024, AOS-025 |
| [AOS-027a](specs/AOS-027a.md) | R1 | IN_PROGRESS | Single-worker verification and protected merge approval | AOS-004, AOS-009, AOS-010 |
| [AOS-027b](specs/AOS-027b.md) | R3 | DRAFT | Integrated multi-worker verification and protected merge | AOS-027a, AOS-026 |
| [AOS-028](specs/AOS-028.md) | R3 | DRAFT | React Mission Control task views, approvals and event replay | AOS-005, AOS-014, AOS-017, AOS-023, AOS-027b |
| [AOS-029](specs/AOS-029.md) | R3 | DRAFT | OTel/Phoenix tracing, cost/usage confidence and exposure dashboard | AOS-012, AOS-014, AOS-028 |
| [AOS-030](specs/AOS-030.md) | R3 | DRAFT | A-1/D-1/B-1 acceptance, chaos and two-week dogfood gate | AOS-017, AOS-018, AOS-019, AOS-020, AOS-021, AOS-022, AOS-023, AOS-024, AOS-025, AOS-026, AOS-027b, AOS-028, AOS-029 |
| [AOS-031](specs/AOS-031.md) | R4 | DRAFT | Provider subscription entitlement telemetry and consented quota-aware routing | AOS-012, AOS-026, AOS-029 |
| [AOS-032](specs/AOS-032.md) | R4 | DRAFT | Controlled inference engine comparison: Ollama, vLLM and SGLang | AOS-015, AOS-016, AOS-031 |
| [AOS-033](specs/AOS-033.md) | R4 | DRAFT | Adaptive quota/resource governor and optional secure API gateway | AOS-026, AOS-031, AOS-032 |
| [AOS-034](specs/AOS-034.md) | R5 | DRAFT | Provenance-aware context compiler, hybrid RAG, voice and quick desktop UX | AOS-011, AOS-017, AOS-029 |
| [AOS-035](specs/AOS-035.md) | R5 | DRAFT | Sandboxed computer use and authorized desktop/browser integrations | AOS-008, AOS-019, AOS-034 |
| [AOS-036](specs/AOS-036.md) | R6 | DRAFT | Offline evaluation, gated improvement, skill registry and memory lifecycle | AOS-012, AOS-013, AOS-021, AOS-022, AOS-034 |
| [AOS-037](specs/AOS-037.md) | R7 | DRAFT | Portable open-source release, multi-machine evaluation and sustained operations | AOS-001, AOS-002, AOS-003, AOS-004, AOS-005, AOS-006, AOS-007, AOS-008, AOS-009, AOS-010, AOS-011, AOS-012, AOS-013, AOS-014, AOS-015, AOS-016, AOS-017, AOS-018, AOS-019, AOS-020, AOS-021, AOS-022, AOS-023, AOS-024, AOS-025, AOS-026, AOS-027b, AOS-028, AOS-029, AOS-030, AOS-031, AOS-032, AOS-033, AOS-034, AOS-035, AOS-036 |

## How to use the package

1. Start with the current phased plan/tracker and an unfinished authorized slice. R0/AOS-001–005 are accepted; do not restart them from historical starter prompts. Inspect the actual repository and original skill inventory when relevant.
2. Supply the [implementation plan prompt](templates/IMPLEMENTATION-PLAN-PROMPT.md), the chosen `specs/AOS-NNN.md`, and shared contract files to the planning agent.
3. Use a checklist for AOS-001/004 and full template for AOS-002/003/005; map applicable requirements to exact files/tests and about one developer-day per slice. Review it before implementation.
4. Implement one tested vertical slice at a time; verify crash/security gates before any real files or cloud credentials are exposed.
5. Mark status `implemented` only after observed evidence (CI + live checks where required), not because the spec is complete.
6. Review draft release scope before planning R1–R7; advance based on tested gates. Later SOTA expansions R4–R7 remain first-class target requirements.

## What differs from the unchanged v0.6.1 master

- A **release-sequencing addendum**, not a silent master rewrite: R0 synthetic kernel (AOS-001–005), R1 offline Ask plus one Claude Code Build worker, R2 safe Delegate, R3 Codex and two workers.
- AOS-027a ships single-worker verification/approval in R1 (deps 004,009,010); AOS-027b ships integrated multi-worker verification in R3 (deps 027a,026).
- Portable Agent Skills standard and post-R1 MCP-server integration are architectural decisions, with actual attached source/checksum/smoke evidence and pending production integration.
- Web search is configured explicitly (SearXNG or approved API), and its queries are outbound disclosures.
- All seven skills and hwprobe.py are attached; supplied checksums pass, 16 smoke assertions and five simulated presets pass, and seven format validations were skipped. Exact source hashes and integration gaps are recorded; no live provider or hardware benchmark was claimed.
- The repository/package/CLI namespace is Panestria; AgentOS remains the historical architecture codename. Public distribution naming/availability still needs its R7 checks.

## Production maturity language

**Build specification complete** means the feature is designed with types, boundaries, tests, failure modes and rollout criteria. It does **not** mean code is implemented, tests were run, a vendor subscription is eligible, hardware latency has been achieved, or security controls have been independently audited.

**Later SOTA epics** AOS-034–037 preserve required capabilities and gate criteria but must be subdivided into narrower build specs once implementation evidence and real target-platform constraints exist. Do not invent a fully frozen technology/API decision for a future provider.

## Verification references

- DBOS: https://docs.dbos.dev/python/tutorials/workflow-tutorial
- DBOS recovery determinism: https://docs.dbos.dev/architecture
- Claude CLI: https://code.claude.com/docs/en/cli-reference
- Anthropic use restrictions: https://code.claude.com/docs/en/legal-and-compliance
- OpenAI sign-in plan terms: https://openai.com/policies/sign-in-with-chatgpt-terms/
- MCP protocol: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/basic/index.mdx
- SearXNG: https://docs.searxng.org/dev/search_api.html
- Skills: https://agentskills.io/specification

---

*All design recommendations are versioned proposals. Vendor and hardware claims must be verified against the versions installed during implementation.*

## Revision-3 additions and precedence

[The active specification](architecture/05-PERSONAL-PLATFORM-REVISION-3.md) defines encrypted local profiles/classification, portable style/model context, connection grants, verified progress, quota-aware useful work/offline capture, read-only phone access, measured resources and REA-informed reuse. [The change record](CHANGES-personal-platform-3.md) identifies scope and preservation. Backlog implementation status comes from the phase tracker; older per-spec draft headers remain historical where superseded. New work is NOT_STARTED/NOT_RUN; documentation is not acceptance.
