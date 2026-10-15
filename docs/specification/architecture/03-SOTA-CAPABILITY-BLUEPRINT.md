# Full SOTA AgentOS Target — Capability Preservation and Implementation Boundaries

**Meaning of SOTA:** research-informed design ambition, not a measured industry leaderboard claim. No part of this target is deleted by R0–R3 reduction. The [full v0.6.1 architecture](../references/AgentOS_v0.6.1_Architecture_Baseline.md) is frozen; this file maps advanced capabilities into implementable interfaces and evidence gates.

| Full target capability | Required system behavior | Architectural owner | Initial slice | Full target story |
|---|---|---|---|---|
| Always-available steward | Local/private endpoint, hardware-aware model residency and safe fallback | intelligence/resources | AOS-015–018 | AOS-034 |
| Durable multi-agent work | DAG scheduling, checkpoint/recovery, external-effect reconciliation | kernel/execution | AOS-001–006 | AOS-025–026,037 |
| Multi-provider inference | Stable model capabilities, local/cloud entitlements and measured routing | token broker | AOS-016 | AOS-031–033 |
| Vendor harness ecosystem | Official CLI/SDK jobs via stable worker protocol | harness broker | AOS-010 | AOS-024,037 |
| Quota/cost optimizer | Explicit cost vs subscription allowance, confidence, reserve and limits | entitlements | AOS-012 | AOS-031–033 |
| Safe tool/MCP ecosystem | Discover, approve, pin and sandbox capabilities; no self-granted permissions | registry/policy | AOS-008/010 | AOS-036–037 |
| Long-running supervisor | Structured milestone contracts, reset context per milestone, bounded replan | intelligence | AOS-002/003 | AOS-025/036 |
| Verifier/evidence | Deterministic tests, source proof, judge with abstention, release gates | verification | AOS-004 | AOS-021–022/027a/027b/030 |
| Personal memory/RAG | Owner/project fact/event/skill stores, provenance, usage stages and controlled forgetting | memory | AOS-011/017 | AOS-034/036 |
| Context compiler | Harness-native context packs filtered by trust/privacy and skill versions | intelligence/memory | R1 minimal | AOS-034 |
| Hardware governor | Measured placement, CPU/GPU/thermal/resource priority, specialist scheduling | resources | AOS-015/018 | AOS-032–033 |
| Specialist model packs | Text/vision/ASR/TTS/image/coding capability-based optional install | inference+registry | Ollama text | AOS-034/036–037 |
| Research agent | Query approval, isolated search/fetch, evidence-backed claims | tools/verification | none until R2 | AOS-013,019–023 |
| Computer use and ambient integration | Explicit opt-in, observation/action split, per-app permissions, local-first | experience/tools | no | AOS-035 |
| Mission Control/voice | Fast Ask/Delegate/Build, live fleet/cost/security/quality views, voice/hotkey | experience | CLI R0/R1 | AOS-028–029/034 |
| Security/privacy/audit | Three policy axes, sandbox egress, cloud exposure, immutable audit, user approvals | kernel/policy | AOS-002/005 | AOS-006–014/037 |
| Learning and evaluation | Trusted corrections, replay, shadow candidates, approved promotion, rollback | evaluation | capture R1 | AOS-036 |
| Portable open-source distribution | No required account, Linux/macOS/CPU/GPU compatibility, signed builds, upgrades | deployment | Ubuntu dev | AOS-037 |

## Mandatory cross-cutting properties

1. **Portability:** No platform-specific CLI or GPU detail leaks into kernel task models; worker capability manifest mediates differences.
2. **Security before authority:** Each new tool/worker/model/API requires compatibility + policy conformance tests, not only a wrapper.
3. **Human control:** Project trust, data privacy and action autonomy are separate, and user-requested stop always stops new admissions immediately.
4. **Grounded outcomes:** An agent output is a *candidate* until executed acceptance and evidence checks pass; unsupported claims are flagged.
5. **Reproducibility:** Tasks, context packs, evidence and metrics include versions, hashes, source labels and actor/attempt IDs.
6. **Hardware courtesy:** AgentOS yields to foreground applications and survives resource pressure without losing task status.
7. **Economic reality:** API cash cost, subscription allowance, shadow/avoided cost, and unknown quota are different measures.
8. **No silent self-modification:** System permissions, tools, standing instructions and model changes are evaluated and approved before production promotion.

## Future epic expansion requirements
AOS-034,035,036,037 are intentionally high-level platform epics because actual hardware performance, user tasks, review/telemetry and upstream project health are not yet measured. Before implementing these stories, split them into child build specs with: concrete supported OS/hardware variants, API schema, negative security tests, benchmark dataset, operator/upgrade docs and rollback. This split **cannot remove** target requirements without explicit ADR.

## Evidence for deciding what to build next
- Need for SGLang/vLLM requires same-model throughput/quality study rather than the number of abstract agents.
- Need for Temporal requires observed distributed recovery/coordination requirements; DBOS remains initial approved executor.
- Need for Graphiti/Letta/Mem0 requires retrieval failure or memory lift evidence; PostgreSQL and documented memory facts remain authoritative.
- Need for LangGraph expansion requires reasoning control-flow complexity that structured planner cannot express cleanly.
- Need for LangSmith/Langfuse requires observability/observed eval limitations; OTel remains the stable telemetry contract.
- Need for specialist agent fleets or advanced MCP servers requires repeatable user tasks, approval capacity and security gates.

## Primary source starting points
- DBOS: https://docs.dbos.dev/python/tutorials/workflow-tutorial
- LangGraph persistence: https://docs.langchain.com/oss/python/langgraph/persistence
- vLLM: https://github.com/vllm-project/vllm
- SGLang: https://github.com/sgl-project/sglang
- Ollama: https://github.com/ollama/ollama
- Agent Skills: https://agentskills.io/specification
- MCP: https://github.com/modelcontextprotocol/modelcontextprotocol
- OpenTelemetry: https://opentelemetry.io/docs/
- Phoenix: https://github.com/Arize-ai/phoenix
- Temporal: https://github.com/temporalio/temporal
- Claude Code: https://code.claude.com/docs/en/cli-reference
- Codex CLI: https://github.com/openai/codex

## Active personal-platform revision 3

The [revision-3 contract](05-PERSONAL-PLATFORM-REVISION-3.md) adds eight bounded R3 obligations and explicitly preserves the R4–R7 target above. Basic quota-aware useful work/offline capture, encrypted profile/style/model context, connection grants, read-only private phone views and verified/resource evidence are MVP foundations. R4 improves telemetry/governor/model selection; R5 adds qualified Byzantium voice/TTS and fuller surfaces; R6 adds permitted weight learning, coaching/graph candidates and gated adaptation; R7 expands user/host/platform trust. Reuse uses REA's source/artifact/runtime evidence workflow, never a claim that inspected proprietary code is automatically reusable.
