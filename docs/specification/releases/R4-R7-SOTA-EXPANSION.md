# R4–R7 Expansion Specification — Preserve the Full SOTA Target

**Planning status:** DRAFT — release scope requires review before implementation planning; revision planning-fixes-1.

These releases expand a working platform; **none are removed from the target**. Adoption is gated by actual quality/resource/security evidence rather than a desire to collect frameworks.

## R4 — Advanced routing and compute (AOS-031–033)
- Subscription entitlement contract: plan usage only through officially supported routes; read-only trustworthy telemetry, background consent and conservative UNKNOWN states.
- Quota forecaster, budget reservation, hard eligibility filters before value-based optimization.
- Benchmark same model/quantization when technically possible using Ollama, vLLM and SGLang under 1/2/4/8/16 concurrency, cold/warm state, shared vs independent prefixes, measured success and foreground interference.
- Adaptive local resource governor, API limits and optional pinned/sandboxed gateway if demonstrated necessary.
- **Promotion:** no improper subscription use, no surprise spend, no unauthorized provider fallback, and a measured gain in quality-adjusted outcomes or cost.

## R5 — Memory, desktop and context (AOS-034–035)
- Cross-harness context compiler with project/source privacy lineage, skills context, precise token budgeting and attention to Claude safe-mode's ignored workspace CLAUDE.md.
- Hybrid RAG + memory lifecycle, project decisions, skills and episodes; retrieval lift evaluated against no-memory baseline before adopting complex engines.
- Push-to-talk/local STT, hotkey/tray, phone status and developer-tool integrations as consented surfaces; ambient recording off by default.
- Secure observation/action split for computer use and browser navigation; no automatically granted credentials.
- **Promotion:** useful repeated personal tasks, measured time saved, memory privacy/relevance tests and app-isolation security pass.

## R6 — Capability discovery and supervised learning (AOS-036)
- Candidate skill/tool/model registry with security manifest, hashes, permissions and user approval.
- Frozen replay evaluation, task/outcome corrections, held-out comparison and guarded promotion/rollback; no uncontrolled policy self-editing.
- Memory compaction with dry runs, pinned source retention, provenance-aware changes and honest forget/backup limits.
- Optional personalized local steward fine-tune **only** after sufficient consented decision samples and evaluation proof.
- **Promotion:** measurable held-out improvement, no gate-metric regression, reproducible revert.

## R7 — Open source, cross-platform and multi-machine (AOS-037)
- Ubuntu/NVIDIA, CPU-only, Apple Silicon compatibility; native inference on Apple host; platform-specific sandbox conformance.
- Signed releases, SBOM, pinned dependencies, license policy, threat model, migrations, offline package mode and no mandatory hosted account/telemetry.
- Potential distributed DBOS recovery/conductor or Temporal *only if architecture decision supported by operational evidence.*
- Public CLI/package/GitHub/domain naming and trademark screening; user-named personal steward.
- **Promotion:** independent fresh installs, restore/rollback, cross-OS sandbox tests, 14-day recovery soak and security review.

## SOTA research capabilities retained beyond initial backlog granularity
- Durable long-running supervisors, fresh-session milestone handoffs, verifier ensembles, independent tool/capability acquisition and agent-agent protocols.
- Multiple model runtimes including local dense/MoE/vision/embedding/ASR/TTS/specialist packs, proactive trigger integrations and desktop companion.
- Memory episode/fact/skill compaction, integrity and forgetting, RAG rerank/graph supplements only when benchmark-justified.
- Reproducible model/agent evals, versioned offline RL/adaptation candidates and software supply-chain defenses.
- Transparent cumulative cloud exposure and actual cost/plan savings, without claiming unknowable encrypted payloads.

For exhaustive target coverage, the **unchanged master architecture** is included in `../references/AgentOS_v0.6.1_Architecture_Baseline.md`, and the module-specific specs are [AOS-031](../specs/AOS-031.md) through [AOS-037](../specs/AOS-037.md).
