# AgentOS Implementation Architecture — Decisions, Invariants and Provenance

**Version:** 0.6.1 implementation-spec pack, 2026-10-11. **Status:** implementation design, review required.  
**Normative baseline:** `../references/AgentOS_v0.6.1_Architecture_Baseline.md` (copied without modification).  
**Change control:** Freeze architectural principles; revise task specs and ADRs based on measured implementation results. Do not silently change the source baseline.

## Source-of-truth hierarchy
1. Explicit user/project safety requirements and approved architecture decisions.
2. The v0.6.1 master architecture (target capabilities and invariant constraints).
3. This package's versioned cross-component contracts; update through ADRs.
4. 38 active implementation specifications (AOS-001–037 with AOS-027 split into 027a and 027b); each defines scope, acceptance and dependencies.
5. Actual implementation code/tests and observed hardware/provider behavior. When code diverges from a spec, file an ADR or defect; never quietly rewrite the spec to rationalize the code.

## Existing implementation assets
The original [agentos-skills-v0.1.0.zip](../attachments/agentos-skills-v0.1.0.zip) is attached with its hash, supplied checksums and an independent file inventory. All seven skill directories and hwprobe.py are physically present and inspected as source data. The [inspection report](../attachments/SKILLS-INVENTORY.md) distinguishes observed checksum/smoke results, skipped format validation and pending integration. The first planning step inventories/tests these actual assets instead of carrying a missing-source caveat forward. The frozen architecture reference retains its original historical text; this addendum supplies current facts.

## Locked architecture invariants
- Kernel owns authoritative task, attempt, approval, policy, budget, side-effect and audit records. An LLM cannot authorize work.
- Goal-contract versions are immutable and acceptance checks must be one of the seven canonical typed checks with executable or authenticated human-reviewed evidence; prose alone is not a passed check.
- **Trust** (project runtime certification), **privacy** (data sensitivity and allowed destinations), **autonomy** (action approval) are independently persisted and enforced; effective permission is their intersection with sandbox and provider scopes.
- Off-device work is opt-in and never a fallback for `RESTRICTED` content. Local model non-residency cannot stop deterministic kernel operations.
- Workers/harnesses and inference runtimes are replaceable; all status and artifacts remain platform-owned.
- Crash recovery does not imply exactly-once external effects. Unknown effects must enter `RECONCILING`, without automatic duplication.
- Repo files, skills, search results, MCP outputs and web text are untrusted. The isolation layer, not the prompt, enforces boundaries.
- Logs and accounting distinguish `known`, `estimated`, `unknown`; missing billing data is not zero.
- Every cloud report distinguishes `authorized`, `accessible`, and `observed` disclosures.
- Every implementation must have deterministic acceptance tests, failure tests, an owner-visible audit trail, and a rollback strategy.

## Platform stack policy
- Python 3.12+ managed by `uv`, FastAPI, SQLAlchemy 2 and Alembic, PostgreSQL; DBOS durable workflows. Versions pinned by lockfile after compatibility tests.
- `pytest`, Ruff, Mypy, Pydantic v2, testcontainers or ephemeral Postgres for integration. Tool suggestions are **proposed**, not claimed installed.
- Start with CLI + minimal loopback HTTP API, then introduce React/Vite and SSE. Observability uses OpenTelemetry and optionally local Phoenix. No mandatory SaaS.
- Ollama first, vLLM/SGLang benchmarked on actual hardware; AWS/cloud APIs and vendor CLI agents only through explicitly approved paths.
- No generic tool-installation or personal-data ingestion during the R0 synthetic proof.

## Release gates (change relative to frozen master)
- **R0 / Kernel Proof:** AOS-001–005, synthetic goal → durable mock worktree → verifier → approval, crash-tested, no real accounts or sensitive repo.
- **R1 / Personal Alpha:** Offline Ask + bounded Build using **one** hardened Claude Code worker; policy/sandbox gates AOS-006–012,014–018; minimal CLI/status UI. AOS-027a provides single-worker verification and merge approval, depending only on AOS-004,009,010.
- **R2 / Research Alpha:** Read-only Delegate; AOS-013 and AOS-019–023; configurable search backend, network isolation, fetched-source provenance and support verification.
- **R3 / Multi-Agent Alpha:** AOS-024–026,027b,028–030; Codex, two-worker scheduling, complete React Mission Control, Phoenix, full journey and chaos suite. AOS-027b extends AOS-027a after AOS-026; R1 has no R3 dependency.
- **R4 / Intelligent Resources:** AOS-031–033 (Phase 2 capabilities).
- **R5 / Context & Desktop:** AOS-034–035 (Phase 3).
- **R6 / Evaluated Adaptation:** AOS-036 (Phase 4).
- **R7 / Open-Source Portability:** AOS-037 (Phase 5).

**R1 is not allowed to operate on real repositories/accounts until corresponding security gates pass**; R0 uses synthetic and mock resources. This release split is an implementation sequencing addendum, not a reduction of full SOTA requirements.

## Architecture decisions and implementation verification
- ADR-001: Adopt portable Agent Skills (`SKILL.md`) for procedural capabilities, plus separate AgentOS permission/IO manifest; skill validator and provenance gate.
- ADR-002: Approved search-provider interface: SearXNG and configurable commercial provider; each search is a network disclosure with stored telemetry; SearXNG itself may contact upstream engines.
- ADR-003: Public kernel API remains transport-agnostic so an opt-in MCP server can expose `submit_goal`, `get_status`, `get_artifacts`, `list_tasks` after R1. No MCP caller bypasses kernel policy; Hermes is one potential MCP client, not an OS-internal authority.
- ADR-004: Use DBOS initially with PostgreSQL, no promise of trivial Temporal substitution. Re-evaluate distributed executor only against actual multi-node needs.
- ADR-005: No brand selection on critical path; `agentos` is a **private codename**. Public name/CLI/PyPI/npm/GitHub/domain clearance before public beta.
- ADR-006: Explicit release ladder R0–R7. Every promotion is conditional on specified tests; no cross-project widening by trust-mode promotion.

## Build/plan-generation discipline
Use the risk-scaled formats in [common requirements](../COMMON-REQUIREMENTS.md): checklist for AOS-001/004; full for AOS-002/003/005; each slice targets about one developer-day. R1–R7 release scopes are drafts before detailed planning. Plans name applicable source files, migrations, interfaces, tests, evidence and rollback. Distinguish existing code, source-backed fact, design proposal, and unresolved issue. No plan may infer that a skill or CLI flag works solely from this spec. Record the exact commit/SHA, runtime and vendor version that passed its acceptance suite.

## User-authorized planning fixes (2026-10-11)
- ADR-007: One canonical acceptance discriminator registry and schema; reject aliases and arbitrary command strings. Existing goal-contract migration is documented, not silently applied to the original archive.
- ADR-008: Split AOS-027a (R1, deps 004/009/010) and AOS-027b (R3, deps 027a/026); revise downstream references and backlog counts.
- ADR-009: One Python distribution with sub-packages and Import Linter boundaries; one global commit-ordered event cursor; task_event, effect_digest and explicit approval project scope.
- ADR-010: DBOS datasource transactions atomically commit task state, event and durable result in one PostgreSQL database. Schema separation is ownership, not separate task stores. Keep external-effect reconciliation.

These choices are settled for this planning revision by the current user request and override conflicting historical implementation details in the frozen baseline. Exact dependency versions and production behavior still require the named implementation tests. Architectural target capabilities are preserved. Common requirements are normative with each individual spec.

## References
- Official DBOS durability and idempotency: https://docs.dbos.dev/python/tutorials/workflow-tutorial
- DBOS determinism, retries and recovery: https://docs.dbos.dev/architecture
- MCP tool specification (2026-07-28): https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/server/tools.mdx
- Search API: https://docs.searxng.org/dev/search_api.html
- Agent Skills specification: https://agentskills.io/specification
- Claude CLI docs: https://code.claude.com/docs/en/cli-reference
- Anthropic security and compliance: https://code.claude.com/docs/en/legal-and-compliance
- OpenAI plan-use terms: https://openai.com/policies/sign-in-with-chatgpt-terms/
