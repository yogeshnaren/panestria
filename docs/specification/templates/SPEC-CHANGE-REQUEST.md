# AgentOS Specification Change Request (CR-XXX)

- **Title / proposer / date:**
- **Reason:** Observed defect, measured performance, upstream vendor change, actual skill implementation or explicit new requirement.
- **Affected AOS spec IDs:**
- **Affected architecture invariants / ADRs:**
- **Current behavior / observed evidence:** Include code SHA, fixture, hardware/provider runtime version and log references.
- **Proposed contract change:** Before/after interface or schema, exact wording, semantics and versioning.
- **Security/privacy/autonomy effect:** Independent analysis for all three axes; egress and approvals.
- **Migration/backward compatibility:** DB changes, API/events, Agent Skills, existing task resume behavior, data retention.
- **Acceptance criteria:** Positive, negative and chaos tests; workload performance change if relevant.
- **Rollback plan:** What can be reverted; what persisted changes require migration.
- **Release impact:** R0/R1/R2/R3/R4–R7; blockers/new gate.
- **Decision:** APPROVED / REJECTED / DEFERRED, named approver and date.

**Rule:** The master architecture is frozen. Record approved meaningful changes as ADR/addenda; do not silently edit historical baseline or repurpose backlog IDs.
