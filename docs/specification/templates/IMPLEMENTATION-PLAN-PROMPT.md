# Implementation Plan Prompt — Use With Any AOS-NNN Specification

Use this full template for AOS-002, AOS-003 and AOS-005. Use [the checklist](IMPLEMENTATION-CHECKLIST.md) for AOS-001 and AOS-004, beginning with AOS-001. R1–R7 are drafts; confirm their release scope before detailed planning. Attach/read the matching `specs/AOS-NNN.md`, `architecture/00-DECISIONS-AND-INVARIANTS.md`, `architecture/01-CANONICAL-DATA-AND-API-CONTRACTS.md`, the normative COMMON-REQUIREMENTS.md, acceptance schemas/type registry, attached skill ZIP/inventory, and current repository state. Read only other AOS docs named as dependencies.

---

You are a principal software engineer implementing a privacy-first, local-first Agent Operating System. Your task is **planning only**, not editing code, for **AOS-NNN**.

**Source priority:** actual repository/skills source and executed tests for implemented facts; frozen `AgentOS_v0.6.1_Architecture_Baseline.md` for architectural invariants; architecture contracts for system interfaces; `specs/AOS-NNN.md` for task requirements. Do not silently replace contradictions. Surface them as ADR/clarifications with precise affected files/requirements.

## Workflow
1. **Inventory:** Read repo tree, current architecture/contracts, lockfile, migrations, test suites, and any existing relevant Agent Skills. For each relevant existing asset report path, commit/hash, test status and reusability; verify the attached original ZIP/checksums and inspection report; inventory actual source, format, license, dependency and permission gaps. Re-run relevant synthetic tests; preserve original hashes and do not execute install/live-worker paths during inventory.
2. **Requirements extraction:** Produce a numbered requirement/acceptance matrix mapping every spec clause to an intended code change and one test. Identify test-unverifiable claims and propose a measurable substitute.
3. **Threat/failure analysis:** Write trust boundaries, data sensitivity, action autonomy, OS execution permissions, credential handling, exact external-effect retry/reconciliation semantics. Show negative tests before suggesting real data/provider use.
4. **API and database:** Specify exact Pydantic schemas, module/function signatures, SQL/Alembic migrations, constraints/indexes, errors, event shapes and owner/tenant scopes. Identify compatibility and upgrade/restore plan. Reuse canonical task_event, effect_digest/project scope, constrained task states and global ordered seq; do not reopen those settled choices. For AOS-003, check current official DBOS transaction/datasource docs, pin the exact supported release and prove state/event/durable result commit in one transaction/session/database with crash fixtures.
5. **Detailed build sequence:** Break into independently testable commits/slices targeting about one developer-day each; split larger estimates further. For each slice list exact files, changes, prerequisites, commands, unit+contract+integration tests, CI checks, expected outputs and rollback. Keep a working vertical path; avoid broad scaffolding.
6. **Operations:** Plan logging/tracing/cost/pressure capture, diagnostic commands, timeouts, retries, kill/restart behavior, on-disk retention and release toggle.
7. **Production readiness:** Security fixture suite, fault-injection matrix, load/latency bounds, version pins, licensing/terms, reproducible deploy, rollback and release gate.
8. **Open decisions:** Ask only questions that block safe implementation; otherwise state an explicit conservative assumption and ADR candidate with reversibility.

## Output format
Create `plans/AOS-NNN-implementation-plan.md` with:
- Executive outcome and explicit non-goals.
- Evidence-based baseline inventory (implemented vs proposed vs unverified).
- Requirement-to-code-to-test traceability table.
- Proposed exact file changes and domain/API/schema contracts.
- Text/mermaid sequence and state diagrams where complexity merits it.
- Security/data-flow and failure-mode table.
- Sequenced atomic tasks with acceptance per commit.
- Data migrations, backup, deployment and rollback instructions.
- Test commands, fixtures, mocks and expected success/failure outcomes.
- Metrics, logs/traces, resource budgets and release signals.
- Dependencies, compatibility versions and open ADRs.
- A final **Ready to Implement** checklist. If any critical security or design unknown remains, mark `BLOCKED` and state precisely why.

Do not claim success, run status, provider compliance or performance unless observed. No real credentials, real repositories or network egress before their relevant security gates. Do not expand into unrelated AOS backlog items without necessity and approved scope.

---

## Implementation coding handoff prompt

Once the plan has been reviewed and approved:

"Implement only the first unchecked vertical slice of `plans/AOS-NNN-implementation-plan.md`. Before changes, confirm relevant repo state and applicable tests. Make the smallest safe change, add tests first or alongside, run the specified checks, and report exactly what changed, commands run, pass/fail evidence, known limitations, and the next slice. Do not mark AOS-NNN complete until every acceptance criterion and security test passes. Do not cross the current release trust boundary."
