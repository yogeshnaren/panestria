# Panestria — extensive R0–R3 implementation design and Cursor plan

**Revision:** 1, 2026-10-11. **Repo:** [yogeshnaren/panestria](https://github.com/yogeshnaren/panestria). **Historical baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917 contained README and MIT LICENSE only. That sentence is the initial inventory, not the current tree. **MVP boundary:** R3.

**Live status:** AOS-001-S1 and S2 hermetic cases passed and are not a release-gate pass. AOS-001-S3 is the active slice on `r0-kernel`. AOS-001-TC04, AOS-001, R0, and the R3 MVP remain incomplete.

This package provides 31 item plans, 93 bounded coding handoffs, 124 scenario groups and source-clause traceability through the complete MVP. Global architecture, API/state/transaction/security/migration designs resolve interfaces that a coding agent otherwise might invent. Original architecture/specs/skills are preserved. R4–R7 remain visible in the wider coverage roadmap; none of the coding handoffs automatically proceeds to SOTA.

## Read first

1. [Cursor setup and first prompt](CURSOR_START_HERE.md).
2. [Architecture and typed contracts](design/01-ARCHITECTURE-AND-CONTRACTS.md), [DB/migrations](design/02-DATABASE-AND-MIGRATIONS.md), [security/worker/research boundaries](design/03-SECURITY-WORKERS-AND-RESEARCH.md).
3. [API/CLI/UI flows](design/04-API-AND-USER-FLOWS.md), [decisions/compatibility spikes](design/05-DECISIONS-AND-COMPATIBILITY.md) and [verified sources](design/06-VERIFIED-SOURCES.md).
4. [AOS-001 implementation plan](plans/AOS-001-implementation-plan.md), then its first [coding handoff](cursor/prompts/AOS-001-S1.md).
5. [Test execution/evidence](testing/TEST_EXECUTION.md) and [operations/release runbook](operations/RUNBOOK-AND-RELEASE.md).

## Phase entry points

| Stage | Outcome | Detailed plans | Stop/exit |
|---|---|---|---|
| [R0](phases/R0-BUILD-PLAN.md) | Synthetic durable kernel | 001–005 | G0 observed schema/workflow/evidence/approval/recovery |
| [R1](phases/R1-BUILD-PLAN.md) | Offline Ask and one-worker Build | 006–012,014–018,027a | G1 actual policy/OS/adapter/hardware proof |
| [R2](phases/R2-BUILD-PLAN.md) | Verified public-web Delegate | 013,019–023 | G2 deterministic evidence plus support/uncertainty/live brief |
| [R3](phases/R3-BUILD-PLAN.md) | Two-worker Build and Mission Control | 024–026,027b,028–030 | G3 cumulative checks/six faults, 14-day trial and owner review |

Build completion, technical gate PASS and owner-accepted MVP are distinct. Use [MVP acceptance](MVP_ACCEPTANCE_CHECKLIST.md). Owner acceptance does not imply SOTA permission.

## Machine-readable planning artifacts

- [Slices and prerequisites](implementation-slices.json).
- [Functional/acceptance traceability](requirement-traceability.json): every source clause retained and assigned to scenario groups; actual assertion mappings remain implementation work.
- [Scenario catalog](testing/test-catalog.json) and [cumulative gates](testing/release-gates.json).
- [Schemas](schemas/goal-contract.schema.json), [event schema](schemas/task-event.schema.json), [case result schema](schemas/case-result.schema.json), [acceptance schema](schemas/acceptance-check.schema.json).
- [Fixture examples](fixtures/README.md).
- [Wider MVP→SOTA roadmap](PANESTRIA_PHASED_IMPLEMENTATION_PLAN.md), [coverage preservation](FULL_TARGET_COVERAGE.md), [original repaired specs](specification/README.md).
- [Package/design validation report](VALIDATION_REPORT.json): artifact checks only, never runtime or SQL execution proof.

Do not feed the entire large consolidated manual into one coding request. Use the global decisions and one exact slice/plan/dependency subset, require observed tests, review and repeat. Native credential/tool isolation, installed DBOS/CLI APIs, OS enforcement, actual model performance and judge calibration are explicit spikes with fail-closed outcomes; a mock does not settle them.
