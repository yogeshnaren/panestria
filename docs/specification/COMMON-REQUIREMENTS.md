# Common requirements for every active build specification

**Revision:** planning-fixes-1. This file is normative with each linked specification; it replaces the repeated shared boilerplate. Each spec contains its own scope, interfaces, evidence and acceptance tests. Apply a requirement only where relevant and record a short reason for any N/A.

**Definition of success:** completion is decided by the acceptance and negative tests below, not by an LLM report or a merged code patch alone.

- **Owner boundary:** kernel persists authoritative state/decisions; relevant adapter/service is replaceable; frontend, if any, reads the same typed API.
- **Versioning:** persisted payloads carry `schema_version`; external CLI/SDK version is captured in compatibility evidence. Scope-sensitive API calls enforce project and user ownership.

Use additive migrations with constraints and indexes tested on real PostgreSQL. Backups/restore and forward-compatibility behavior must be documented for any destructive migration. Data sensitivity and source provenance survive derivation and logging.

## 5. Execution behavior and error handling
- Reject an invalid authorization/scope/contract before dispatch. Preserve a structured denial event with a safe diagnostic code.
- Bounded timeouts, resource caps, retries and cancellation must be defined for every external call; errors distinguish safe-to-retry from ambiguous side effects.
- On interruption, replay authoritative DB state and revalidate policy; no worker can commit after an invalidated lease or mutate an approved contract.
- Unknown data, usage, provider availability or verifier outcome are represented explicitly; they are not silently converted into successful states.
- Each critical action includes owner, project, task, attempt, policy version and trace IDs where applicable.

**Test classes required:** unit; database migration/contract; integration fixture; at least one negative security or failure-injection test; reproducibility on supported R-stage deployment. Record fixture inputs, expected outputs, CLI/SDK versions and observed results. Where physical GPU/provider credentials are needed, isolate optional live tests from offline CI.

Use actual OS/database/API guards, not only model prompts. No test may access an unrelated real workspace, local tokens or external endpoints without explicitly granted user test authorization.

- Capture `task_id`, `attempt_id`, `worker/runtime_version`, `trace_id` and appropriate evidence IDs; redact secrets and respect privacy labels.
- Roll out behind a release-stage feature gate; on failure, disable new admissions, retain durable history and restore prior version. Do not erase the audit record during rollback.
- Link a runbook: setup, troubleshooting, cancellation, stuck-state recovery, test fixtures and resource effects.

## Planning depth and slice size

- AOS-001 and AOS-004 use the [checklist template](templates/IMPLEMENTATION-CHECKLIST.md). Preserve their acceptance and failure tests; a checklist is sufficient to map exact files, commands, expected results and rollback.
- AOS-002, AOS-003 and AOS-005 use the [full planning template](templates/IMPLEMENTATION-PLAN-PROMPT.md): schema, durability and approvals need explicit contracts and failure analysis.
- R1–R7 are DRAFT in backlog metadata and release/spec documents. Resolve their release scope before detailed implementation planning. Draft does not mean implemented or removed from the target architecture.
- Each implementation slice should fit about one developer-day and end in an executable check. Split larger estimates further; list the next slice without implementing it prematurely. No large all-backlog planning pass.
- Full plans provide exact files/interfaces, migrations or N/A, requirement-to-test mapping, bounded failure/retry behavior, version pins, evidence, observability and rollback. The checklist covers the same applicable outcomes in a shorter format.
- Read the attached original skills archive and [inspection report](attachments/SKILLS-INVENTORY.md) first. Skills are candidate implementations; inclusion, checksum validation and smoke tests do not grant permissions or establish production integration.
- Canonical acceptance discriminators come exclusively from [the type registry](contracts/acceptance-check-types.json) and [acceptance node schema](contracts/acceptance-check.schema.json). Unimplemented types fail admission. An unknown verdict never satisfies a required check.
- Use the same PostgreSQL database for AgentOS domain tables and DBOS-managed tracking, with separate schemas and one DBOS datasource transaction/session for each task-state/event update. External effects retain intent, idempotency and reconciliation requirements.
