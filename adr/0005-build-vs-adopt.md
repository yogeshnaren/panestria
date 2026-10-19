# Build vs adopt: existing agent projects, languages and self-improvement

**Date:** 2026-10-18. **Status:** proposed design record; no code, dependency or
release gate changes. **Owner direction recorded from chat on 2026-10-18** (see
section 7). **Applies to:** R3 supervision patterns, R5 surfaces, R6 adaptation
(AOS-025, AOS-034, AOS-035, AOS-036) and the language policy for all phases.

Panestria's differentiator is its guarantee layer: a durable PostgreSQL/DBOS
kernel with fencing and effect reconciliation, independent trust/privacy/autonomy
policy, OS-level sandboxing, effect-digest-bound approvals, independently verified
merges, and hash-retained research evidence. Several neighbouring projects already
ship pieces of the *surfaces and learning loops* the SOTA plan intends to build.
This record decides, per project and per capability, whether to adopt, adapt,
borrow an idea, evaluate, or build. It does not authorize SOTA work: R4–R7 still
need MVP acceptance and a separate owner decision.

## 1. Method and its limits

Sources were each project's README or architecture page, read on 2026-10-18.
Star counts, security reputations and benchmark gains came from the projects'
own text or third-party write-ups and were **not independently verified**. No
upstream source code was read, built or run, and the Harness² and Meta-Harness
papers were not read. Every "adopt" below therefore starts with the REA/source
investigation the phased plan already requires (license, pinned version, source
inspection, security review, a minimal tested integration) before any dependency
lands. No upstream application code is incorporated by this record.

Decision vocabulary:

| Verdict | Meaning |
|---|---|
| ADOPT | Use as a pinned dependency or format behind a Panestria-owned adapter. |
| CLIENT | Run alongside as an untrusted caller of the scoped kernel API. |
| BORROW | Re-implement an idea or pattern in Panestria. Credited in [CREDITS](../docs/CREDITS.md). |
| EVALUATE | Run a predeclared comparison before choosing. |
| BUILD | Panestria owns it because a core invariant cannot be delegated. |
| REJECT | Not suitable for this platform. |

## 2. Decisions per project

| Project | License | Verdict | Used for | Why / limits |
|---|---|---|---|---|
| [GEPA](https://github.com/gepa-ai/gepa) | MIT | **ADOPT** (R6) | Candidate generation for prompts, context packs, skills, routing and configs from retained traces. | Most mature of the optimizers: PyPI package, adapters, DSPy integration. Gains in its README are the authors' own. Needs an evaluator and traces, which Panestria's retained records provide. Reflection calls are model calls and must obey egress and classification policy. |
| [Meta-Harness](https://github.com/stanford-iris-lab/meta-harness) | MIT | **EVALUATE** (R6) | Code-level harness search with a filesystem of prior candidates, scores and traces. | Its own README says the cleaned code "has not been tested beyond verifying that it runs", and its examples assume a Claude Code wrapper. Promising for code-level changes, immature as a dependency. |
| [Harness²](https://github.com/google-research/harness2) | Apache-2.0 | **EVALUATE + BORROW** (R6) | Propose–Probe–Compose probing and a persistent, evidence-backed lesson library across tasks. | Research code: 3 commits, no releases, "not an officially supported Google product". Its README states executor network access is unrestricted and the Codex sandbox is disabled, and neither the README nor project page describes safeguards against harmful edits or how it validates without ground truth. Can only run inside Panestria's sandbox and egress controls. |
| [Hermes Agent](https://github.com/NousResearch/hermes-agent) | MIT | **CLIENT** + **BORROW** | Messaging gateway, cron, voice and terminal front end over the MCP/scoped API (already planned); ideas for memory nudging, FTS5 session recall and skill creation. | Preferred over OpenClaw by the owner. Its agent-written skills have no evaluation gate; Panestria's R6 gate stays authoritative. Do not fork Hermes (existing decision in the specification). |
| [OpenClaw](https://github.com/openclaw/openclaw) | MIT | **DEFER** | Only as an additional CLIENT if Hermes lacks a needed channel. | Very large, fast-moving and designed around host-level tool access. Same client contract as Hermes if ever used: no transport grants permission. |
| [Agent Skills format](https://agentskills.io/specification) | open spec | **ADOPT** | Skill packaging (`SKILL.md`, `scripts/`, `references/`, `assets/`, progressive disclosure) and the `skills-ref` validator. | Already required by AOS-036. `allowed-tools` is experimental; Panestria's capability manifest, not that field, remains authoritative. Verify validator license and language before use. |
| [Firstmate](https://github.com/kunchenguid/firstmate) | MIT | **BORROW** (credited) | Supervision patterns for R3, listed in section 4. | Bash/tmux, file-based state and a self-documented merge race. Panestria keeps its own durable kernel and approvals. |
| [Sandcastle](https://github.com/mattpocock/sandcastle) | MIT | **BORROW** (credited) | Branch strategies and parallel-planner-with-review pattern for the two-worker scheduler. | TypeScript library whose unattended runs default to permission-bypass flags, and no durable task state. Not a runtime dependency. |
| Anthropic brain/hands/session ([Managed Agents](https://www.anthropic.com/engineering/managed-agents)) | n/a | **BORROW** (validation) | Confirms durable event log, disposable sandbox and credentials kept out of the sandbox. | Adds two lessons to apply: provision sandboxes lazily, and never prune context irreversibly (keep the full log). A hosted product, not reusable locally. |
| [Evo 2](https://www.broadinstitute.org/node/5561006) | Apache-2.0 (per NVIDIA) | **REJECT** for the platform | At most a biology specialist-pack candidate under AOS-034 manifests. | A DNA foundation model, unrelated to agent orchestration. |

Already decided elsewhere and unchanged: DBOS (durable execution), LangGraph
(bounded planning subgraph only, never authoritative state), Postgres (canonical
state).

## 3. Capability-level build vs adopt

| Capability | Decision | Reason |
|---|---|---|
| Kernel, policy, approvals, verification, research evidence, canonical memory and classification | **BUILD** | These carry the core invariants (provenance, privacy class, exact approval). Delegating them to a framework would move authority outside Panestria. |
| Messaging channels, mobile and desktop chat surfaces (R5) | **CLIENT** (Hermes first) | Do not rebuild 20 channel connectors. Clients get a scoped API token and are untrusted inputs. |
| Voice (STT/TTS), engines | **ADOPT** an engine behind a Panestria adapter | Engine choice needs the usual ADR and benchmark. Capture stays opt-in and visibly controlled. |
| Skill format and registry packaging | **ADOPT** format, **BUILD** registry/trials | Format is interoperable. Signing, scanning, trials and promotion are Panestria's. |
| Prompt/context/skill/routing optimization (R6) | **ADOPT** GEPA, **EVALUATE** alternatives | See section 6. |
| Supervisor wake logic, worktree pooling, busy-state detection (R3) | **BORROW** | Re-implemented against durable kernel state. |
| Mission Control | **BUILD** (TUI first, then web) | Owner prefers a TUI before a GUI. |
| Memory frameworks (Mem0, Honcho, etc.) | **EVALUATE** as optional retrieval candidates only | They cannot hold canonical memory because source links and privacy labels must remain in Panestria's records. |
| Local inference engines | **ADOPT** (separate processes) | Engine comparison is already scoped to AOS-032. |

## 4. What is borrowed, and where it lands

From **Firstmate** (credited in [CREDITS](../docs/CREDITS.md)):

| Idea | Panestria destination |
|---|---|
| Zero-token watcher that wakes the supervising agent only for actionable events | AOS-025/026 supervisor wake queue, driven by durable kernel events rather than files. |
| Busy/idle/unknown/dead classification from harness lifecycle signals instead of rendered text | AOS-024/026 worker liveness, per adapter, with "unknown" kept distinct from "dead". |
| `ship` versus `scout` task types (scout never pushes) | AOS-025 task contract: a read-only investigation type with no merge effect. |
| Merge bound to the live head; teardown refuses dirty or unlanded worktrees | AOS-027b; Panestria's effect-digest binding already goes further. |
| Pooled, reusable worktrees with slot ownership checks | AOS-026 worktree pool. |
| Away-mode record kept verbatim, with only mechanical limits enforced by code | Owner autonomy record in the policy model; words are evidence, limits are enforced. |
| Declared waits not escalated as wedges | AOS-026 stall detection. |

From **Sandcastle** (credited):

| Idea | Panestria destination |
|---|---|
| Explicit branch strategies (`head`, `merge-to-head`, `branch`) | AOS-026/027b; only per-task branches are permitted for concurrent work. |
| Parallel-planner and parallel-planner-with-review templates | AOS-025/026 two-worker plan, with the review step run by the independent verifier. |
| Warm sandbox reuse across runs | AOS-008/026 as an optimization, never sharing a worktree between tasks. |
| Sandbox-provider abstraction | Already present in Panestria's sandbox profiles; keep provider-neutral. |

From **Hermes** (credited): periodic memory nudges, FTS5 plus summarized session
recall, natural-language scheduling into a durable job. Each lands as a Panestria
feature with its own provenance and privacy handling, not as a Hermes dependency.

Anything Panestria already does more strictly than these projects (exact
approvals, protected merge, reconciliation of lost replies) is not weakened to
match them.

## 5. Language policy

Python 3.12 remains the default and the language of record for the kernel, policy,
workflows, API, memory, research, verification, evaluation and the GEPA
integration. The owner's experience and the existing import-boundary and typing
gates make a rewrite a net loss. Other languages are allowed where they produce a
measured or demonstrable benefit.

**Rules for any non-Python component**

1. It runs as a separate process behind a versioned protocol defined by the
   existing JSON contracts. No FFI into the kernel and no direct database access:
   the kernel stays the only authority for task state.
2. It needs a predeclared reason: either a measured improvement on a named hot path
   (say, at least 2x at equal correctness, recorded with raw numbers) or a
   concrete safety property such as memory safety on untrusted input or a small
   static binary in a minimal sandbox image. "Faster in general" is not enough.
3. It ships with its own CI lane: pinned toolchain, lockfile, lint and type or
   clippy checks, dependency audit and license check, and an equivalent of the
   import-boundary contracts. It appears in the R7 SBOM.
4. Python remains the reference implementation until the replacement passes the
   same contract tests.

**Candidates**

| Language | Candidate | Condition |
|---|---|---|
| Rust | In-sandbox helper and native tool-gateway data path; egress relay and fetch-broker data path; parsers for untrusted web/PDF content inside the reader sandbox | Prototype against the current Python path; adopt only if rule 2 holds. Today's reader is already OS-isolated, so the argument is defence in depth and image size, not a fix for a known flaw. |
| Rust | Supervisor watcher and process supervision daemon (Firstmate-style) | Only if measured idle CPU or wake latency of the Python asyncio version is unacceptable. |
| Rust | High-volume event or trace pipeline | Only after measurement shows the Python path is the bottleneck. |
| TypeScript | Mission Control web UI (AOS-028, React) with a client generated from `docs/api/openapi.json` | Planned. Contracts generate the types so the two sides cannot drift. |
| TypeScript | Terminal UI | Default to a Python TUI first (one language, owner experience); revisit if the web UI later shares components worth reusing. |
| Any | Inference engines (vLLM, llama.cpp, Ollama and similar) | Separate processes chosen by the AOS-032 benchmark, not by this policy. |

Not recommended: rewriting the kernel, policy engine or verifiers in another
language; running Sandcastle or Firstmate as a runtime dependency.

## 6. Choosing among GEPA, Meta-Harness and Harness²

All three improve the text and code *around* a fixed model. They differ in what
they can edit, how they judge, and how mature they are.

| Criterion | GEPA | Meta-Harness | Harness² |
|---|---|---|---|
| Edits | Text parameters, code, configs, via adapters | Whole harness code, via a coding-agent proposer | Eight components including guardrails, skills, scripts, plugins |
| Judging | User-supplied evaluator plus textual feedback | Task scores and traces on disk | Execution evidence at task level; benchmark judging afterwards |
| Maturity (from READMEs) | Package, adapters, integrations | Cleaned research code, "not tested beyond running" | 3 commits, no releases |
| Safeguards documented | Not a focus; relies on the evaluator | Not documented | None described |
| Fit with Panestria | Evaluator and traces already planned | Needs a sandboxed proposer | Needs sandbox and egress control |
| Primary value | Candidate generation with few rollouts | Code-level changes | Lesson library and probing idea |

**Decision.** Start R6 with GEPA as the candidate generator. Run Meta-Harness and
Harness² as time-boxed experiments against the same frozen replay corpus only
after GEPA has produced a baseline. Do not wait for them. Whatever generates a
candidate, **Panestria owns the evaluator, the held-out set, the safety suite and
the promotion gate**, and the optimizer cannot modify any of them.

Predeclared bake-off protocol (record before running):

- Same frozen replay corpus, dev/held-out split, rollout/token budget and local or
  approved model for every optimizer, at least three seeds.
- Metrics: held-out gain, cost per accepted gain, dev-to-held-out gap (overfit),
  safety-suite regressions, diff size and reviewability, completeness of the
  evidence trail, and whether it runs unchanged inside the sandbox and egress
  rules.
- Decision rule: pick the optimizer whose held-out gain exceeds the baseline's
  confidence interval with no safety regression. If none do, keep the baseline
  and record the negative result. Small samples are reported as uncertain, not as
  wins.

**Improving on Harness² regardless of which optimizer wins.** Adopt its two ideas
and add what it lacks:

- Keep a persistent, evidence-linked **lesson library** in Panestria's learning
  records: each lesson cites the traces, corrections and outcomes behind it.
- Use **probing** as a trial stage: run candidates in disposable worktrees under
  the sandbox before any replay.
- Add the missing parts: a held-out validation gate, versioned rollback,
  an isolated evaluator, spend budgets, and an immutable record of why each change
  was made.

## 7. Self-updating policy (owner direction and one recommended floor)

**Owner direction (2026-10-18):** Panestria should apply improvements to its own
guardrails, skills and plugins without waiting for sign-off. The owner must be
notified and able to review and reverse each change, and every change should carry
metrics and reasoning.

This changes the draft R6 text, which says tools, new permissions, standing
instructions and external effect policy require owner approval, and the AOS-025
non-goal "no autonomous policy mutation". The original specifications are
preserved unchanged. This section is the recorded amendment proposal, with parent
AOS-036, destination R6, reason above, and it needs the owner's explicit
confirmation of the floor in 7.1 before R6 planning relies on it.

### 7.1 The one place I recommend keeping an approval

A self-improving system that can *loosen its own guardrails* can reward-hack its
way past the controls that make it safe. A notification arrives after the effect,
so it cannot undo exposure, egress or spend. I therefore recommend that
Panestria never auto-apply a change that **widens authority**. Everything else is
auto-applied and notified.

| Tier | Examples | Handling |
|---|---|---|
| **A — auto-apply, notify** | System and context prompts; tool guidance; skill content and scripts that stay inside currently granted permissions; memory-compaction parameters; bounded routing weights; **tightening** a guardrail (an added check, a stricter refusal); self-authored plugins whose declared permissions are a subset of what is already granted | Passes the promotion rules in 7.2, then goes live on a canary. Owner gets a notification. |
| **B — owner approval** (the floor) | Anything that widens authority: new or broader permissions, egress destinations, privacy-class access, autonomy level, budget or spend limits, credential or secret scope, relaxing or removing a guardrail or approval requirement, loosening a sandbox profile; installing an external plugin, tool or MCP server; editing policy-engine, verifier, check-definition or held-out evaluation code, or the promotion gate itself | Proposed with the same evidence package, held until the owner approves. |

The owner may later move specific B-items to A with a recorded, scoped decision.
The line is a recommendation, not something I will enforce without their say.

### 7.2 Conditions for auto-applying any change

- The candidate beats the incumbent on the frozen and held-out sets by a margin
  and confidence bound set **before** the run, with a minimum sample size. Below
  the minimum it is recommended, not applied.
- The full safety, privacy and injection fixtures show no regression.
- It first runs in a sandboxed trial, then on a canary (a task fraction or time
  window) with automatic rollback if success rate, cost per verified success,
  correction rate or safety checks cross predeclared limits.
- It stays within an improvement budget and a promotion rate limit (maximum per
  week, with a cool-down after any rollback).
- The change is versioned and reversible by one command.
- The optimizer has no write access to the evaluator, held-out data, safety suite
  or promotion rules.

### 7.3 What the owner sees for each change

A notification record, shown in the inbox and in a digest:

- **What:** the exact diff and the component affected, with its tier.
- **Why:** the traces, corrections and outcomes that motivated it, linked to
  retained evidence.
- **Evidence:** metrics before and after with sample sizes and uncertainty, the
  safety-suite result, the canary outcome, and the cost of producing it.
- **Control:** one-command revert and a "revert and pin" action that records the
  owner's rejection as a standing constraint and a negative example for future
  candidates. A switch to pause all auto-updates.
- **Audit:** immutable promotion and rollback events in the canonical event log.

### 7.4 Risks that remain

Optimizers overfit small replay sets; labels and judges can be contaminated; an
accumulation of many small tier-A changes can drift behaviour even when each
passes; notification fatigue can make review nominal. Mitigations are periodic
re-evaluation against the original baseline, a cap on cumulative drift from the
last owner-reviewed version, and a digest that groups changes by effect. These
reduce risk; they do not remove it.

## 8. Consequences

- R5 shrinks: channels, voice front ends and phone surfaces become clients or
  adopted engines, and Mission Control stays the owner-facing surface.
- R6 gains a named starting point (GEPA) and a bounded comparison instead of an
  open "select an eval toolkit".
- A new multi-language footprint appears only behind the rules in section 5.
- Credit obligations exist from the first borrowed idea (see
  [CREDITS](../docs/CREDITS.md)).
- Nothing changes for R1–R3 gates. The Firstmate and Sandcastle patterns land in
  R3 work only as ordinary task PRs.

## 9. Follow-ups, none started

1. Owner confirms or edits the tier boundary in 7.1.
2. At R6 entry: REA source investigation of GEPA, then Meta-Harness and Harness²,
   covering license, pinned versions, a source read, an egress review and a minimal
   sandboxed integration.
3. Validate `skills-ref` license, language and behaviour against Panestria's
   capability manifest.
4. Prototype the first Rust candidate (in-sandbox helper) only after R3 is stable.
5. Hermes client conformance case when the MCP front end exists.
6. If any upstream code is ever copied, add its license text under
   `third_party/` and a `NOTICE` entry in the same PR.
