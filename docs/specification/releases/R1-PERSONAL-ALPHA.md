# R1 Build Specification — Useful Offline Ask + One Hardened Build Worker

**Planning status:** DRAFT — release scope requires review before implementation planning; revision planning-fixes-1.

**Goal:** Deliver a daily-use personal AgentOS before web research and parallel coding are necessary. Preserve all R0 gates, and extend from mock-only synthetic execution to controlled personal use **only after** the corresponding security tests pass.

## Critical-path stories
- **Hardening required before real access:** AOS-006 leases/effects; AOS-007 three-axis policy; AOS-008 OS sandbox; AOS-009 API/approval security; AOS-010 hardened Claude Code worker.
- **Evidence from the start:** AOS-011 memory and use stages; AOS-012 routing/feedback/exposure; AOS-014 events, traces, SSE.
- **Ask:** AOS-015 hardware probe (attached hwprobe.py inventory and simulation evidence; real hardware audit pending); AOS-016 offline inference; AOS-017 chat+memory; AOS-018 offline/pressure tests.
- **Build:** [AOS-027a](../specs/AOS-027a.md) single-worker verifier and merge approval (deps AOS-004/009/010). AOS-027b extends it in R3 after AOS-026. AOS-004 mock worker evolves to Claude via AOS-010.
- **Experience:** R0 CLI, optional very thin locally served status/approval page. Full React Mission Control is the R3 story AOS-028; do not let it delay R1.

## Product journeys
### Ask
1. User enters `agentos ask "..."` with project context. 2. Policy determines data label and local-only routing. 3. Hardware manifest selects local model, with load/unload state observed. 4. Owner-scoped memory is searched; source IDs and context-pack hashes recorded. 5. Reply streams with source-linked recall, TTFT and possible degraded mode.

**A-1 R1 gate:** network disabled at OS boundary; ten fixed questions (three recall, one hostile prompt to use unauthorized cloud); correct scope and zero observed outbound traffic. Report warm/cold TTFT and hardware details. The 3-second provisional warm p95 target from the baseline is conditional on actual Omen benchmark; mark **not met**, not falsely passed, when hardware cannot deliver it.

### Build
1. Owner selects `SYNTHETIC_DEV` project and explicit allowed root. 2. Kernel records structured GoalContract; tests defined by trusted command refs and path checks. 3. Claude Code worker launched under tested safe/restricted CLI profile, in an isolated worktree with sanitized repository configuration. 4. Candidate artifacts reviewed against deterministic verifier. 5. Exact commit/tree SHA requires explicit merge approval. 6. Crashes/retries reconcile unknown effects.

**B-single R1 gate:** synthetic repository proves crash recovery, failed-test rejection, unapproved path refusal, stale approval rejection, malicious `.claude/settings.json` and `.mcp.json` hooks never execute, and exact binary/version/auth mode compatibility. Real personal repos permitted only after this suite, OS sandbox and policy tests pass. No second worker required for R1.

## Data gates
- `memory_use_event`: retrieved, included, used_by_worker, judged_unused, candidate_helped (not causal proof).
- `routing_decision/outcome`: backend choices, rejected alternatives, policy reason, cost known/estimated/unknown.
- `cloud_exposure`: authorized, accessible and observed separately.
- `policy`: project-scoped trust version, independent data label and per-action autonomy.
- `approval`: exact effect digest/version, owner/project scope, expiry.

## Security fixtures
1. Malicious repo config creates marker or attempts network exfil during CLI startup → marker never written and denied egress logged.
2. Worker invokes unauthorized shell/network/tool while in restricted profile → OS enforcement denies.
3. Change only trust mode while holding privacy/autonomy fixed → no new remote route or send permission.
4. Private memory in Project A requested from Project B → no retrieval or derived context leakage.
5. Local web page attempts forged POST to loopback API → Host/Origin/CSRF/auth blocks.
6. Bounded effect response lost → enters RECONCILING; no duplicate action.

## Operational readiness
- One-command install/diagnose model/Claude CLI, no automatic driver installation.
- Clear offline/no-model/unknown-plan states.
- Model warm/cold and resource-pressure metrics on actual machine.
- User-visible audit and approval history; no mandatory telemetry export or hosted account.
- Runbook for provider CLI compatibility upgrade, restoring task from crash, rotating local API auth, and re-probing hardware.

## Explicitly later
R2 public-web Delegate; R3 Codex parallelism and full React UI; R4 vLLM/SGLang adaptive selection; R5 rich context/voice/desktop; R6 learning; R7 distributed open-source support.
