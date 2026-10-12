# AOS-027a — Single-worker verification and protected merge approval

**Implementation specification:** AgentOS v0.6.1 | **Release:** R1 | **Status:** DRAFT; release scope requires review before implementation planning  
**Dependencies:** [AOS-004](AOS-004.md), [AOS-009](AOS-009.md), [AOS-010](AOS-010.md)  
**Architecture:** [Decisions](../architecture/00-DECISIONS-AND-INVARIANTS.md) · [Canonical contracts](../architecture/01-CANONICAL-DATA-AND-API-CONTRACTS.md) · [Frozen v0.6.1 master](../references/AgentOS_v0.6.1_Architecture_Baseline.md)
**Shared requirements:** [Common requirements](../COMMON-REQUIREMENTS.md) apply; **planning format:** full; slices target one developer-day.

## 1. Goal / business outcome
A worker cannot claim a software task done based on its own narrative; checked evidence and exact approval govern acceptance and any protected merge.

## 2. In-scope functional requirements
- Implement the R1 single-worker verifier and merge-approval service after AOS-004, AOS-009 and AOS-010. Use canonical trusted-command-ref, git-diff-path-check and policy-decision checks; human-review evidence cannot substitute for explicit action authorization.
- Verifier must run against the **candidate final tree** for the single worker and exact intended destination base; a stale worktree test report cannot authorize a changed candidate. Use pinned known test commands with timeout and output limit; file diff signed with commit/tree SHA.
- Protected merge requires approval digest binding exact candidate commit, destination branch, check set, project/action policy version and expiry. Revalidate immediately before side effect; unexpected external effect goes RECONCILING.
- Missing evidence, failed/UNKNOWN checks, modified diff after approval or policy mismatch means no merge.

## 3. Required interfaces, contracts and ownership
- `VerificationService.verify_candidate(commit_sha,contract_id)`, `MergeApprovalService.request/commit`, `BuildEvidenceBundle` with test, diff, path, static scan, artifact hashes.

## 4. Data model, migrations and evidence
- Check runs store tree SHA, verifier type/version, result/evidence hash; approval binds candidate digest. Link side-effect record to actual protected merge receipt or uncertain reconciliation.

## 5. Acceptance criteria and automated test matrix
- Deliberately failing tests reject worker 'done'; unauthorized path diff rejects before completion.
- Rebase changes candidate hash: old approval invalid. Inject lost response after mock merge: no duplicate merge; unresolved state requires reconciliation.
- One hardened Claude Code worker produces a candidate, verifier independently checks it, and a single-use effect_digest-bound approval permits only that exact scoped merge. Wrong owner/project, changed destination/base/candidate/check set or expired approval denies execution.

## 6. Threat model and mandatory safeguards
- False completion, test-runner tampering, time-of-check/time-of-use race, merge token misuse, encoded path bypass, supply-chain test script attack.

## 7. Operations, observability and rollout
- Approval inbox evidence preview, audit trail, retained test stdout summaries, gated branch history; recovery runbook for uncertain merge.

## 8. Explicit non-goals
- No concurrent-worker scheduler or integrated multi-worker verifier; these are AOS-027b in R3. No automatic deployment or external publishing without action authorization.

## 9. Decisions to confirm in implementation planning
- Agree trusted test-runner isolation and test coverage policy per repository; test R1 single-worker verification without depending on AOS-026. Completion of AOS-027a does not mark AOS-027b done.

**Existing skill/artifact reconciliation:** `goal-contract` structured verifiers and `milestone-handoff` final tree hashes feed Build evidence.

## 10. Supporting references
- See master architecture references and verify exact upstream versions at build time.
- Frozen master: `../references/AgentOS_v0.6.1_Architecture_Baseline.md` (backlog §16; applicable design sections).
- Shared contracts: `../architecture/01-CANONICAL-DATA-AND-API-CONTRACTS.md`.
