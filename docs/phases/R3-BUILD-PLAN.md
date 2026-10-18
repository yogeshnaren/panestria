# R3 detailed sequence and gate

**Status:** DRAFT / NOT_RUN; component implementation IN_PROGRESS. **Planning revision:** 3. **Gate:** G3. Implementation through R3 is owner-authorized; full release evidence, live conformance and owner acceptance remain pending.

| Step | Plan | Slices | Dependencies |
|---|---|---|---|
| 1 | [AOS-024](../plans/AOS-024-implementation-plan.md) | AOS-024-S1 → S2 → S3 | AOS-004, AOS-008, AOS-010 |
| 2 | [AOS-025](../plans/AOS-025-implementation-plan.md) | AOS-025-S1 → S2 → S3 | AOS-003, AOS-016 |
| 3 | [AOS-026](../plans/AOS-026-implementation-plan.md) | AOS-026-S1 → S2 → S3 | AOS-006, AOS-010, AOS-024, AOS-025 |
| 4 | [AOS-027b](../plans/AOS-027b-implementation-plan.md) | AOS-027b-S1 → S2 → S3 | AOS-027a, AOS-026 |
| 5 | [AOS-028](../plans/AOS-028-implementation-plan.md) | AOS-028-S1 → S2 → S3 | AOS-005, AOS-014, AOS-017, AOS-023, AOS-027b |
| 6 | [AOS-029](../plans/AOS-029-implementation-plan.md) | AOS-029-S1 → S2 → S3 | AOS-012, AOS-014, AOS-028 |
| 7 | [AOS-030](../plans/AOS-030-implementation-plan.md) | AOS-030-S1 → S2 → S3 | AOS-017, AOS-018, AOS-019, AOS-020, AOS-021, AOS-022, AOS-023, AOS-024, AOS-025, AOS-026, AOS-027b, AOS-028, AOS-029 |

Cumulative gate requires **157 scenario groups**: 124 baseline across **31 AOS items** plus 33 revision-3 cases covering **8 extensions**. The 38 total AOS IDs and original item phases remain unchanged. See [release gates](../testing/release-gates.json) and [execution](../testing/TEST_EXECUTION.md). Every group must cover all its source acceptance parameters. Missing/skipped/mock-for-live/version-mismatched evidence is INCOMPLETE.

## Demonstration / exit

Two certified workers, bounded DAG/cash/resource admission, integrated required suite and exact final approval. Mission Control reflects canonical task/evidence/usage/exposure with redacted local traces. A-1/D-1/B-1 and six faults pass, followed by 14-day owner trial/acceptance.

Record code, dependency/image/model/CLI/hardware versions, corpus/hash, reports, known issues, runbook and rollback. Do not assume current docs or simulated prototypes are installed-runtime proof.

Freeze the candidate for [MVP review](../MVP_ACCEPTANCE_CHECKLIST.md). Technical build completion precedes observed trial and owner MVP_ACCEPTED. A separate owner record authorizes R4/SOTA; these coding prompts stop at R3.

## Revision 3 implementation sequence

After the relevant baseline interfaces exist, select extensions by their manifest dependencies. Classification/vault comes before sensitive style/context; grants precede phone ingress; quota observations precede scheduling/capture; resource tests and complete release evaluation follow their dependencies. Fixture implementation may continue while independent live certification is pending. Do not enable uncertified capabilities.

| Extension | Owning plan | Added slices | Required outcome |
| --- | --- | --- | --- |
| MVP-X07 | AOS-011 | AOS-011-S4, AOS-011-S5, AOS-011-S6 | Encrypted owner profile and canonical classification |
| MVP-X08 | AOS-017 | AOS-017-S4, AOS-017-S5, AOS-017-S6 | Portable assistant charter, communication style and model context |
| MVP-X09 | AOS-008 | AOS-008-S4, AOS-008-S5 | Explicit connection grants and secret boundary |
| MVP-X10 | AOS-025 | AOS-025-S4, AOS-025-S5 | Verified milestones, stall detection and bounded repair |
| MVP-X11 | AOS-012 | AOS-012-S4, AOS-012-S5, AOS-012-S6, AOS-012-S7 | Quota-aware useful work and automatic offline capture |
| MVP-X12 | AOS-028 | AOS-028-S4, AOS-028-S5, AOS-028-S6 | Private read-only phone companion |
| MVP-X13 | AOS-018 | AOS-018-S4, AOS-018-S5 | Measured lightweight resource and foreground contract |
| MVP-X14 | AOS-030 | AOS-030-S4, AOS-030-S5 | Reuse, REA evidence and comparative engineering |

Read [the active extension specification](../specification/architecture/05-PERSONAL-PLATFORM-REVISION-3.md) and [shared slice handoff](../cursor/prompts/MVP-REV3-SLICE.md). Each envelope targets about one developer-day; split it after repository inspection if needed. The 21 extension slices have individual NOT_STARTED/IN_PROGRESS status in the manifest; all 33 added acceptance cases remain NOT_RUN. MVP-X09 has owner-reviewed declaration and process-local root components with linked evidence, while the actual broker/current-authority/account/purpose/budget/secret/onboarding integration remains unfinished. Component checks do not complete a case or release gate. Baseline AOS-030-S3 owner trial must occur after extension completion and all 156 pretrial cases; AOS-030-TC04 then records the trial/owner decision and final G3 requires all 157 cases; numeric slice order does not permit an early trial. No skipped/unimplemented case can complete G3.

Phone status/inbox is read-only over separately enabled private authenticated TLS ingress. Background push, voice, remote approvals, graph/fine-tuning and autonomous promotion remain later. Quota scheduling and verified offline retention are MVP capabilities; sophisticated forecasting and weight training are not prerequisites for using them.
