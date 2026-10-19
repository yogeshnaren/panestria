# AOS-018 — Offline, degraded-mode and foreground-resource safety tests: implementation plan

**Release:** R1. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-015, AOS-016, AOS-017. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](../design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](../design/02-DATABASE-AND-MIGRATIONS.md), [security](../design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](../design/04-API-AND-USER-FLOWS.md), [decisions](../design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](../testing/TEST_EXECUTION.md) and [source spec](../specification/specs/AOS-018.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

Offline Ask remains useful without cloud/network, while CPU/GPU pressure does not cause resource starvation or corrupt task state.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/resources/admission.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/resources/probe.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/execution/task_workflow.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/cli/doctor.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `RuntimeGovernor.observe/admit/degrade(snapshot, job) -> Admission`
- `DegradedStatus.reason -> TypedReason`
- `OfflineGateRunner.run(profile, corpus) -> GateEvidence`

**Migration ownership:** Resource observation/admission/degraded reason events; only coarse MVP limits, no R4 optimizer.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-018-F01 | Build OS-level no-network test harness and optional network namespace; assert no DNS, HTTP or provider CLI fallback for local-only work. Test model cold load, unload and abort during response. | AOS-018-S1, AOS-018-S2, AOS-018-S3; owning files/interfaces above | AOS-018-TC01, AOS-018-TC02, AOS-018-TC03, AOS-018-TC04; parameterize every condition in this clause |
| AOS-018-F02 | Sample GPU VRAM/compute, CPU, RAM, battery/AC, thermal flags and active-foreground policy; implement conservative admission ceiling and a deterministic steward control fallback if GPU unavailable. | AOS-018-S1, AOS-018-S2, AOS-018-S3; owning files/interfaces above | AOS-018-TC01, AOS-018-TC02, AOS-018-TC03, AOS-018-TC04; parameterize every condition in this clause |
| AOS-018-F03 | Test prompt/time budget, OOM recovery, model process restart, disk pressure and cloud account absence. Distinguish intentional queue from hung service. | AOS-018-S1, AOS-018-S2, AOS-018-S3; owning files/interfaces above | AOS-018-TC01, AOS-018-TC02, AOS-018-TC03, AOS-018-TC04; parameterize every condition in this clause |
| AOS-018-AC01 | No egress in network-disabled A-1, including DNS and model auto-download. | AOS-018-S1, AOS-018-S2, AOS-018-S3; owning files/interfaces above | AOS-018-TC01, AOS-018-TC02, AOS-018-TC03, AOS-018-TC04; parameterize every condition in this clause |
| AOS-018-AC02 | Under synthetic GPU allocation pressure, heavy inference waits/steps down and existing durable tasks remain recoverable. | AOS-018-S1, AOS-018-S2, AOS-018-S3; owning files/interfaces above | AOS-018-TC01, AOS-018-TC02, AOS-018-TC03, AOS-018-TC04; parameterize every condition in this clause |
| AOS-018-AC03 | Battery mode and disabled GPU produce explicit CPU or unavailable states without silent cloud fallbacks. | AOS-018-S1, AOS-018-S2, AOS-018-S3; owning files/interfaces above | AOS-018-TC01, AOS-018-TC02, AOS-018-TC03, AOS-018-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-018-S1](../cursor/prompts/AOS-018-S1.md) | AOS-015, AOS-016, AOS-017 | Explicit conservative process/CPU/RAM/VRAM/disk caps and observed/battery/degraded states. | AOS-018-TC01; command/report/exit, immutable evidence and diff |
| [AOS-018-S2](../cursor/prompts/AOS-018-S2.md) | AOS-018-S1 | No-network harness, model restart/OOM/unload and foreground-priority fixtures with clear queue-vs-hang diagnostics. | AOS-018-TC02; command/report/exit, immutable evidence and diff |
| [AOS-018-S3](../cursor/prompts/AOS-018-S3.md) | AOS-018-S2 | Actual physical resource/offline/cancellation recovery run and observed incident/latency evidence. | AOS-018-TC01, AOS-018-TC02, AOS-018-TC03, AOS-018-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-018-TC01 | security | `tests/integration/test_aos_018.py::test_offline_dns_no_provider` | OS-network-disabled Ask performs no DNS/provider fallback; absent account has no effect on local path. |
| AOS-018-TC02 | chaos | `tests/integration/test_aos_018.py::test_oom_disk_model_restart` | Inject pressure/disk full/model kill; stop admissions, preserve events/evidence, bounded recover/degrade. |
| AOS-018-TC03 | integration | `tests/integration/test_aos_018.py::test_capacity_queue_and_cancel` | Known ceiling queues excess work; cancellation ends no-new-admissions immediately and reports in-flight effects honestly. |
| AOS-018-TC04 | live | `tests/integration/test_aos_018.py::test_foreground_pressure_profile` | Actual hardware under approved pressure stays within recorded profile limits; no false guarantee of fine-grained consumer GPU partitioning. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_018.py --junitxml=evidence/AOS-018.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

## Failure, operations and rollback

Unsafe scope/config/version/malformed evidence is non-retryable denial; transient safe I/O uses bounded retry; ambiguous external effects pause in RECONCILING. Mutations check current owner/project/contract/epoch and append events atomically. Timeouts/cancellation preserve durable state; diagnostics redact sensitive content. No generic retry can create exactly-once external effects.

Capture relevant task/attempt/epoch/policy/trace and immutable evidence IDs. Roll out behind this capability gate. On regression stop affected admissions, retain history/receipts/evidence and revert code/config; migrations use tested restore/forward repair. Never blindly delete history or compensate a confirmed effect. Implement setup/diagnosis, stuck-state and scoped cleanup runbook steps with this item.

## Item completion

- [ ] Every source clause maps to actual assertions and observed evidence.
- [ ] Required scenarios PASS for one recorded candidate/environment; missing/skipped/unknown/live gaps remain blockers.
- [ ] Migration/API/adapters match the approved design; material changes have an ADR.
- [ ] Applicable live/compatibility, runbook and rollback/restore evidence complete.
- [ ] User-visible results are verifiable; worker narrative grants no authority.

Only then complete this item. A release cannot promote while its other required items remain unfinished. AOS-030 trial/owner acceptance decides complete MVP; SOTA authorization remains separate.

## Revision 3 extension — MVP-X13, delivered in R3

Owner clarification (2026-10-18): S4 includes an initial
[read-only storage component](../testing/STORAGE_AWARENESS.md): reserves, bounded
opt-in directory/Docker/Timeshift observations and terminal warning/recovery output.
`tests/unit/test_storage_awareness.py` covers thresholds, reserve/growth, hardlinks,
symlinks, denied/timed-out scans, local-only Docker estimates, read-only backup
policy, private settings and disabled/deduplicated/revoked notifications. This is
partial TC05/TC07 behavior, not qualification of those whole cases.

Remaining S4/S5: connect expected writes/headroom to worker/download/artifact
admission, integrate opt-in settings/local inbox with AOS-029, retain bounded
source-bound growth observations across restarts and qualify real host budgets.
Offer keep/defer, inspect, backup-scope/target review, unused-cache review with
rebuild/offline impact, or owner-managed capacity expansion/migration. Never delete
storage, prune caches/volumes or change backup settings. Preserve historical gates.

The [active personal-platform contract](../specification/architecture/05-PERSONAL-PLATFORM-REVISION-3.md#mvp-x13) adds **Measured lightweight resource and foreground contract**. Original parent scope and historical results remain intact. These new slices deliver in **R3**, even when the parent AOS item originally ships in R1; they do not reopen historical G0 acceptance or fabricate G1 evidence. Inspect the current repository before choosing exact new files/migration revisions.

| Slice | Concrete outcome, narrowed to about one developer-day | Prerequisites |
| --- | --- | --- |
| AOS-018-S4 | Add reproducible component resource/latency baseline and approved target-host budgets. | AOS-015-S3, AOS-016-S3, AOS-018-S3 |
| AOS-018-S5 | Verify foreground/pressure/recovery limits and expose honest measured capacity. | AOS-018-S4, AOS-026-S3, AOS-029-S3 |

Use the [revision-3 slice handoff](../cursor/prompts/MVP-REV3-SLICE.md) with the selected manifest entry. File ownership candidates are in implementation-slices.json; record an ADR for a material change. Existing shared transaction/security/API requirements still apply.

| Added case | Lane | Required passing behavior |
| --- | --- | --- |
| AOS-018-TC05 | integration | Versioned measurements separate controller/database/model idle/active/peak memory, CPU, disk, VRAM, queue latency and cold/warm output; host-specific budgets are fixed before qualification. |
| AOS-018-TC06 | security | Effective CPU/RAM/process/I/O limits and pressure-aware admission protect controller recovery and foreground work; unavailable cgroup/PSI capabilities are explicit. |
| AOS-018-TC07 | chaos | Resource pressure bounds queues and unloads safe idle resources while retaining task state; no unauthorized cloud fallback; GPU estimates are not reported as guaranteed VRAM partitions. |
| AOS-018-TC08 | live | Actual target-host workload and foreground contention meet recorded memory/responsiveness budgets; synthetic presets or unmeasured resource claims cannot qualify. |

These nodes and scenarios are planned, not observed tests. Register real assertion/node/lane/evidence mappings while implementing; missing required evidence blocks G3. Rollout begins disabled, uses synthetic content until its boundary is certified, stops admissions on failure and preserves audit/receipts. R4-R7 work is not authorized by completing this extension.
