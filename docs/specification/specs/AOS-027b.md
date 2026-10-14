# AOS-027b — Integrated multi-worker verification and protected merge

**Implementation specification:** AgentOS v0.6.1 | **Release:** R3 | **Status:** DRAFT; release scope requires review before implementation planning  
**Dependencies:** [AOS-027a](AOS-027a.md), [AOS-026](AOS-026.md)  
**Architecture:** [Decisions](../architecture/00-DECISIONS-AND-INVARIANTS.md) · [Canonical contracts](../architecture/01-CANONICAL-DATA-AND-API-CONTRACTS.md) · [Frozen v0.6.1 master](../references/AgentOS_v0.6.1_Architecture_Baseline.md)
**Shared requirements:** [Common requirements](../COMMON-REQUIREMENTS.md) apply; **planning format:** full; slices target one developer-day.

## 1. Goal / business outcome
A worker cannot claim a software task done based on its own narrative; checked evidence and exact approval govern acceptance and any protected merge.

## 2. In-scope functional requirements
- Extend the AOS-027a service after AOS-026. Collect fenced worker results, detect conflicts, construct the integrated candidate tree and run the complete required check set on that tree; reuse the R1 approval and evidence contracts.
- Verifier must run against the **candidate final tree** (post-integration for multiworker), not only each worktree's isolated passing tests. Use pinned known test commands with timeout and output limit; file diff signed with commit/tree SHA.
- Protected merge requires approval digest binding exact candidate commit, destination branch, check set, project/action policy version and expiry. Revalidate immediately before side effect; unexpected external effect goes RECONCILING.
- Missing evidence, failed/UNKNOWN checks, modified diff after approval or policy mismatch means no merge.

## 3. Required interfaces, contracts and ownership
- `VerificationService.verify_candidate(commit_sha,contract_id)`, `MergeApprovalService.request/commit`, `BuildEvidenceBundle` with test, diff, path, static scan, artifact hashes.

## 4. Data model, migrations and evidence
- Check runs store tree SHA, verifier type/version, result/evidence hash; approval binds candidate digest. Link side-effect record to actual protected merge receipt or uncertain reconciliation.

## 5. Acceptance criteria and automated test matrix
- Two independently passing worker trees whose integrated result fails tests must be rejected. A stale/fenced result cannot enter the integrated candidate; overlapping changes require an explicit reviewed resolution and fresh check run.
- Rebase changes candidate hash: old approval invalid. Inject lost response after mock merge: no duplicate merge; unresolved state requires reconciliation.
- Two-worker tree tests re-run after integration; passing isolated suites insufficient when combined result fails.

## 6. Threat model and mandatory safeguards
- False completion, test-runner tampering, time-of-check/time-of-use race, merge token misuse, encoded path bypass, supply-chain test script attack.

## 7. Operations, observability and rollout
- Approval inbox evidence preview, audit trail, retained test stdout summaries, gated branch history; recovery runbook for uncertain merge.

## 8. Explicit non-goals
- No replacement single-worker approval implementation; reuse AOS-027a. No automatic production deployment or external PR publishing without action authorization.

## 9. Decisions to confirm in implementation planning
- Agree trusted test-runner isolation and test coverage policy per repository; preserve AOS-027a service semantics while binding approval to the final integrated tree. Resolve conflict policy and test evidence on the exact scheduler release.

**Existing skill/artifact reconciliation:** `goal-contract` structured verifiers and `milestone-handoff` final tree hashes feed Build evidence.

## 10. Supporting references
- See master architecture references and verify exact upstream versions at build time.
- Frozen master: `../references/AgentOS_v0.6.1_Architecture_Baseline.md` (backlog §16; applicable design sections).
- Shared contracts: `../architecture/01-CANONICAL-DATA-AND-API-CONTRACTS.md`.
