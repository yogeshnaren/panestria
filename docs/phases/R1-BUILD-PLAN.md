# R1 detailed sequence and gate

**Status:** IN_PROGRESS / NOT_RUN. **Gate:** G1. R0 is accepted and R1 implementation is authorized. See [execution control](R1-EXECUTION-CONTROL.md); live conformance remains pending.

| Step | Plan | Slices | Dependencies |
|---|---|---|---|
| 1 | [AOS-006](../plans/AOS-006-implementation-plan.md) | AOS-006-S1 → S2 → S3 | AOS-003 |
| 2 | [AOS-007](../plans/AOS-007-implementation-plan.md) | AOS-007-S1 → S2 → S3 | AOS-002 |
| 3 | [AOS-008](../plans/AOS-008-implementation-plan.md) | AOS-008-S1 → S2 → S3 | AOS-004, AOS-007 |
| 4 | [AOS-009](../plans/AOS-009-implementation-plan.md) | AOS-009-S1 → S2 → S3 | AOS-005, AOS-007 |
| 5 | [AOS-010](../plans/AOS-010-implementation-plan.md) | AOS-010-S1 → S2 → S3 | AOS-004, AOS-008, AOS-009 |
| 6 | [AOS-027a](../plans/AOS-027a-implementation-plan.md) | AOS-027a-S1 → S2 → S3 | AOS-004, AOS-009, AOS-010 |
| 7 | [AOS-011](../plans/AOS-011-implementation-plan.md) | AOS-011-S1 → S2 → S3 | AOS-002 |
| 8 | [AOS-012](../plans/AOS-012-implementation-plan.md) | AOS-012-S1 → S2 → S3 | AOS-002, AOS-007 |
| 9 | [AOS-014](../plans/AOS-014-implementation-plan.md) | AOS-014-S1 → S2 → S3 | AOS-003, AOS-012 |
| 10 | [AOS-015](../plans/AOS-015-implementation-plan.md) | AOS-015-S1 → S2 → S3 | AOS-001 |
| 11 | [AOS-016](../plans/AOS-016-implementation-plan.md) | AOS-016-S1 → S2 → S3 | AOS-011, AOS-015 |
| 12 | [AOS-017](../plans/AOS-017-implementation-plan.md) | AOS-017-S1 → S2 → S3 | AOS-011, AOS-016 |
| 13 | [AOS-018](../plans/AOS-018-implementation-plan.md) | AOS-018-S1 → S2 → S3 | AOS-015, AOS-016, AOS-017 |

Cumulative gate requires **72 scenario groups** across **18 items**. See [release gates](../testing/release-gates.json) and [execution](../testing/TEST_EXECUTION.md). Every group must cover all its source acceptance parameters. Missing/skipped/mock-for-live/version-mismatched evidence is INCOMPLETE.

## Demonstration / exit

Offline Ask/source-linked memory and one independently verified live worker. Three-axis policy, OS/credential/tool isolation, API security, resource caps, baseline opt-in SDK and telemetry proved. Uncertified native shell tier cannot be declared certified by an edit-only pilot.

Record code, dependency/image/model/CLI/hardware versions, corpus/hash, reports, known issues, runbook and rollback. Do not assume current docs or simulated prototypes are installed-runtime proof.

## Revision 3 boundaries

R0 is accepted and R1/G1 remains in progress, not completed by merged code. [Revision 3](../specification/architecture/05-PERSONAL-PLATFORM-REVISION-3.md) assigns added work to R3 under existing owners; it does not silently expand historical G0/G1 manifests. Resolve classification and certify the vault before sensitive profiles are enabled. Independent fixture work can continue during a pending quota/live lane. Use current main/task branches and [the phase tracker](../phase-tracker.json), rather than the old aggregate r1-alpha branch, for new work.
