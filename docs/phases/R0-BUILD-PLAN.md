# R0 detailed sequence and gate

**Status:** NOT_STARTED / NOT_RUN. **Gate:** G0. Detailed planning through R3 is authorized; code/live conformance remain pending.

| Step | Plan | Slices | Dependencies |
|---|---|---|---|
| 1 | [AOS-001](../plans/AOS-001-implementation-plan.md) | AOS-001-S1 → S2 → S3 | repo inventory |
| 2 | [AOS-002](../plans/AOS-002-implementation-plan.md) | AOS-002-S1 → S2 → S3 | AOS-001 |
| 3 | [AOS-003](../plans/AOS-003-implementation-plan.md) | AOS-003-S1 → S2 → S3 | AOS-002 |
| 4 | [AOS-004](../plans/AOS-004-implementation-plan.md) | AOS-004-S1 → S2 → S3 | AOS-003 |
| 5 | [AOS-005](../plans/AOS-005-implementation-plan.md) | AOS-005-S1 → S2 → S3 | AOS-003, AOS-004 |

Cumulative gate requires **20 scenario groups** across **5 items**. See [release gates](../testing/release-gates.json) and [execution](../testing/TEST_EXECUTION.md). Every group must cover all its source acceptance parameters. Missing/skipped/mock-for-live/version-mismatched evidence is INCOMPLETE.

## Demonstration / exit

Synthetic goal/contract consent, mock worktree, independent checks, exact synthetic merge approval and durable recovery. Real PostgreSQL migration/concurrency/atomic enqueue/replay and safe cleanup proven; no live accounts.

Record code, dependency/image/model/CLI/hardware versions, corpus/hash, reports, known issues, runbook and rollback. Do not assume current docs or simulated prototypes are installed-runtime proof.
