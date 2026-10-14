# AOS-015 — Hardware probe integration and versioned capability manifest: implementation plan

**Release:** R1. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-001. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](../design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](../design/02-DATABASE-AND-MIGRATIONS.md), [security](../design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](../design/04-API-AND-USER-FLOWS.md), [decisions](../design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](../testing/TEST_EXECUTION.md) and [source spec](../specification/specs/AOS-015.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

AgentOS accurately measures installed CPU/GPU/RAM/disk/power and chooses feasible local model candidates without treating simulated specs as real.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/resources/probe.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/resources/catalog.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/resources/benchmark.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/cli/hardware.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `HardwareProbe.collect(read_only=True) -> HardwareManifest`
- `ModelCatalog.candidates(profile, required_capability) -> CandidateModels`
- `PlacementPlanner.propose(manifest, limits) -> PlacementProposal`

**Migration ownership:** Versioned hardware/model manifests and protected hashes; no upload of device identifiers by default.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-015-F01 | Inventory existing `hardware-probe` skill and `hwprobe.py` source/tests; verify claimed five simulated profiles, provenance and license. Run read-only OS probes (`nvidia-smi`, CPU info, RAM, upower, ROCm/macOS when available); missing tool reported unsupported, not 0 resources. | AOS-015-S1, AOS-015-S2, AOS-015-S3; owning files/interfaces above | AOS-015-TC01, AOS-015-TC02, AOS-015-TC03, AOS-015-TC04; parameterize every condition in this clause |
| AOS-015-F02 | Define signed/versioned `HardwareManifest` with OS/kernel, accelerator type, total/free VRAM, RAM, driver/runtime, measured/estimated bandwidth, thermal/battery/AC status, time and permissions; avoid privileged probing. | AOS-015-S1, AOS-015-S2, AOS-015-S3; owning files/interfaces above | AOS-015-TC01, AOS-015-TC02, AOS-015-TC03, AOS-015-TC04; parameterize every condition in this clause |
| AOS-015-F03 | A model-role catalog estimates resident memory as weights + KV + overhead, capability and license; no guaranteed tok/s from bandwidth estimate. Select steward by safe fit then benchmark actual TTFT/throughput. | AOS-015-S1, AOS-015-S2, AOS-015-S3; owning files/interfaces above | AOS-015-TC01, AOS-015-TC02, AOS-015-TC03, AOS-015-TC04; parameterize every condition in this clause |
| AOS-015-F04 | Re-probe on install/boot/drivers/catalog changes and preserve previous manifest for before/after comparison; allow user pin with an explicit degraded warning. | AOS-015-S1, AOS-015-S2, AOS-015-S3; owning files/interfaces above | AOS-015-TC01, AOS-015-TC02, AOS-015-TC03, AOS-015-TC04; parameterize every condition in this clause |
| AOS-015-AC01 | Run probe on actual Omen: record GPU name and real VRAM, RAM, driver and power; missing nvidia-smi gives explicit fallback. | AOS-015-S1, AOS-015-S2, AOS-015-S3; owning files/interfaces above | AOS-015-TC01, AOS-015-TC02, AOS-015-TC03, AOS-015-TC04; parameterize every condition in this clause |
| AOS-015-AC02 | Five attached simulated profile fixtures (smoke-checked in this revision) pass expected placement/low-memory degradation; no silent cloud selection for Restricted work. | AOS-015-S1, AOS-015-S2, AOS-015-S3; owning files/interfaces above | AOS-015-TC01, AOS-015-TC02, AOS-015-TC03, AOS-015-TC04; parameterize every condition in this clause |
| AOS-015-AC03 | Non-privileged probe doesn't change NVIDIA driver/prime config; manifests parse from fresh JSON Schema. | AOS-015-S1, AOS-015-S2, AOS-015-S3; owning files/interfaces above | AOS-015-TC01, AOS-015-TC02, AOS-015-TC03, AOS-015-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-015-S1](../cursor/prompts/AOS-015-S1.md) | AOS-001 | Inventory original hwprobe source/license/presets and adapt typed uncertainty/probe-method manifest without installing drivers. | AOS-015-TC01; command/report/exit, immutable evidence and diff |
| [AOS-015-S2](../cursor/prompts/AOS-015-S2.md) | AOS-015-S1 | Read-only physical probes and candidate memory estimates distinguish unsupported/missing from zero capacity. | AOS-015-TC02; command/report/exit, immutable evidence and diff |
| [AOS-015-S3](../cursor/prompts/AOS-015-S3.md) | AOS-015-S2 | Preset/low-memory fixtures plus explicit real-machine manifest and measured placement proposal. | AOS-015-TC01, AOS-015-TC02, AOS-015-TC03, AOS-015-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-015-TC01 | unit | `tests/integration/test_aos_015.py::test_five_presets_and_missing_tools` | All five attached preset fixtures parse as simulated; missing nvidia-smi unsupported, not zero VRAM or made-up GPU. |
| AOS-015-TC02 | contract | `tests/integration/test_aos_015.py::test_model_fit_uncertainty` | Weight/KV/overhead budget enforced, bandwidth estimate not labelled measured throughput; license/capability refs required. |
| AOS-015-TC03 | live | `tests/integration/test_aos_015.py::test_real_hardware_read_only` | Actual GPU/VRAM/RAM/driver/power observed without driver/prime mutation; no network upload or privileged probing. |
| AOS-015-TC04 | integration | `tests/integration/test_aos_015.py::test_manifest_version_change` | Probe/catalog/version change creates new hashed manifest with old evidence retained and explicit user pin/degraded result. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_015.py --junitxml=evidence/AOS-015.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

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
