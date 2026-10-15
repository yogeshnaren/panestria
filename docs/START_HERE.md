# Panestria build entrypoint

**Active planning revision:** 3, 2026-10-15. **Main build document:** [phased implementation plan, MVP through SOTA](PANESTRIA_PHASED_IMPLEMENTATION_PLAN.md).

R0 is COMPLETE/G0 PASS for its recorded accepted candidate. R1 is IN_PROGRESS/G1 NOT_RUN. R2/R3 scope is drafted and code/live acceptance remains pending. MVP ends at R3: 156-case pretrial readiness, the 14-day trial/owner decision in AOS-030-TC04, and all 157 cases for final G3/owner acceptance. R4–R7 implementation requires a separate owner decision.

Read the phased plan and [active personal-platform specification](specification/architecture/05-PERSONAL-PLATFORM-REVISION-3.md), then the relevant design files, item plan and one selected manifest slice. The original 38 AOS specs and 31 MVP items remain; eight additional MVP obligations add 21 slice envelopes and 33 cases. Current planning coverage is **114 slices / 157 G3 scenarios**, not a claim those tests or features exist.

## Build navigation

For the supported offline Ask application, use [owner setup](testing/LOCAL_ASK_SETUP.md),
[server launch](testing/LOCAL_ASK_SERVER.md) and [browser pairing/testing](testing/LOCAL_ASK_BROWSER.md).
These component paths are usable before release acceptance; they do not enable
profiles, remote phone access, or Build tools in the Ask browser.

1. [Cursor instructions and reusable prompt](CURSOR_START_HERE.md).
2. [Architecture](design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](design/02-DATABASE-AND-MIGRATIONS.md), [security](design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API/UI](design/04-API-AND-USER-FLOWS.md), [decisions](design/05-DECISIONS-AND-COMPATIBILITY.md).
3. [Phase tracker](phase-tracker.json), [active backlog](specification/backlog.json), [slice manifest](implementation-slices.json), [requirement traceability](requirement-traceability.json).
4. [R1 plan](phases/R1-BUILD-PLAN.md), [R2 plan](phases/R2-BUILD-PLAN.md), [R3 plan and extensions](phases/R3-BUILD-PLAN.md), [R4–R7 expansion](specification/releases/R4-R7-SOTA-EXPANSION.md).
5. [Case catalog](testing/test-catalog.json), [required gates](testing/release-gates.json), [evidence execution](testing/TEST_EXECUTION.md), [MVP acceptance](MVP_ACCEPTANCE_CHECKLIST.md), [operations](operations/RUNBOOK-AND-RELEASE.md).
6. [Full-target coverage](FULL_TARGET_COVERAGE.md), [preserved source/spec pack](specification/README.md), [classification ADR](../adr/0003-personal-platform-classification.md).

Older prompts/status headers and original download bundles are historical where superseded by revision 3. Preserve their provenance and hashes; do not restart completed R0 work because an old prompt says AOS-001-S1. Reconcile each selected slice against actual current code and evidence. A component suite, a document validator or a merged PR cannot substitute for a release gate or its required live checks.

Use small task branches/PRs and coherent implementation/test commits. A multi-slice goal may continue through authorized ready MVP slices with a reviewable result per slice; a single-slice request stops there. Never cross the R3 owner checkpoint automatically. The [older validation report](VALIDATION_REPORT.json) records its original artifact snapshot; current validation must identify its own source revision.
