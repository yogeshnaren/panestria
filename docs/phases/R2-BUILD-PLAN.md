# R2 detailed sequence and gate

**Status:** NOT_STARTED / NOT_RUN. **Gate:** G2. Detailed planning through R3 is authorized; code/live conformance remain pending.

| Step | Plan | Slices | Dependencies |
|---|---|---|---|
| 1 | [AOS-013](../plans/AOS-013-implementation-plan.md) | AOS-013-S1 → S2 → S3 | AOS-002, AOS-008 |
| 2 | [AOS-019](../plans/AOS-019-implementation-plan.md) | AOS-019-S1 → S2 → S3 | AOS-008, AOS-009, AOS-013 |
| 3 | [AOS-020](../plans/AOS-020-implementation-plan.md) | AOS-020-S1 → S2 → S3 | AOS-013, AOS-019 |
| 4 | [AOS-021](../plans/AOS-021-implementation-plan.md) | AOS-021-S1 → S2 → S3 | AOS-020 |
| 5 | [AOS-022](../plans/AOS-022-implementation-plan.md) | AOS-022-S1 → S2 → S3 | AOS-021, AOS-016 |
| 6 | [AOS-023](../plans/AOS-023-implementation-plan.md) | AOS-023-S1 → S2 → S3 | AOS-019, AOS-020, AOS-021, AOS-022 |

Cumulative gate requires **96 scenario groups** across **24 items**. See [release gates](../testing/release-gates.json) and [execution](../testing/TEST_EXECUTION.md). Every group must cover all its source acceptance parameters. Missing/skipped/mock-for-live/version-mismatched evidence is INCOMPLETE.

## Demonstration / exit

Configured public-web search, pinned safe fetch, isolated reader, exact retained hashes/byte passages/quotes and separate support/uncertainty. Five adversarial briefs and scoped live brief; disabling research leaves Ask/Build working.

Record code, dependency/image/model/CLI/hardware versions, corpus/hash, reports, known issues, runbook and rollback. Do not assume current docs or simulated prototypes are installed-runtime proof.
