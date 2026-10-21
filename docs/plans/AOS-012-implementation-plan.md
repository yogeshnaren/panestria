# AOS-012 — Routing outcomes, corrections and cloud-exposure event contracts: implementation plan

**Release:** R1. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-002, AOS-007. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](../design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](../design/02-DATABASE-AND-MIGRATIONS.md), [security](../design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](../design/04-API-AND-USER-FLOWS.md), [decisions](../design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](../testing/TEST_EXECUTION.md) and [source spec](../specification/specs/AOS-012.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

Every future routing/personalization decision has minimally sufficient evidence from the earliest real tasks, without claiming unavailable cost/quota data.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/telemetry/usage.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/telemetry/exposure.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/kernel/repositories/routing.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/memory/use_events.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `RoutingRecorder.decision(actor, candidates, selected, policy_ref) -> RouteRef`
- `OutcomeRecorder.record(task_ref, verifier_refs, correction_ref) -> OutcomeRef`
- `ExposureLedger.record_authorized/accessible/observed(scope, record) -> ExposureRef`

**Migration ownership:** 0004_telemetry: routing_decision/outcome/user_correction/exposure_observation/usage_observation with nullable unknown measurements.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-012-F01 | Persist eligible/denied backend candidates, reason, capability class, policy IDs, selected route, expected cost/risk and uncertainty; post-execution task outcome references deterministic verifier/user acceptance. | AOS-012-S1, AOS-012-S2, AOS-012-S3; owning files/interfaces above | AOS-012-TC01, AOS-012-TC02, AOS-012-TC03, AOS-012-TC04; parameterize every condition in this clause |
| AOS-012-F02 | Record `user_correction` as diff/rejection/explicit text with output version, owner consent and sensitivity. Do not train or infer preferences merely from passive prompt data. | AOS-012-S1, AOS-012-S2, AOS-012-S3; owning files/interfaces above | AOS-012-TC01, AOS-012-TC02, AOS-012-TC03, AOS-012-TC04; parameterize every condition in this clause |
| AOS-012-F03 | Store three separate outbound-data dimensions: `authorized` (policy), `accessible` (files/prompt scope), `observed` (OS/process network metadata); encrypted CLI contents may be unknowable. | AOS-012-S1, AOS-012-S2, AOS-012-S3; owning files/interfaces above | AOS-012-TC01, AOS-012-TC02, AOS-012-TC03, AOS-012-TC04; parameterize every condition in this clause |
| AOS-012-F04 | Cost and quota observations use `known/estimated/unknown` with null amount for unknown; event schemas are versioned for eventual subscriptions optimizer. | AOS-012-S1, AOS-012-S2, AOS-012-S3; owning files/interfaces above | AOS-012-TC01, AOS-012-TC02, AOS-012-TC03, AOS-012-TC04; parameterize every condition in this clause |
| AOS-012-AC01 | After process restart reconstruct route selection and rejection reasons from DB alone. | AOS-012-S1, AOS-012-S2, AOS-012-S3; owning files/interfaces above | AOS-012-TC01, AOS-012-TC02, AOS-012-TC03, AOS-012-TC04; parameterize every condition in this clause |
| AOS-012-AC02 | Unknown quota yields null, not 0 or unlimited; possible egress reported accessible but not observed with correct distinction. | AOS-012-S1, AOS-012-S2, AOS-012-S3; owning files/interfaces above | AOS-012-TC01, AOS-012-TC02, AOS-012-TC03, AOS-012-TC04; parameterize every condition in this clause |
| AOS-012-AC03 | User correction cannot overwrite immutable original answer artifact; denied route remains denied after another agent suggests it. | AOS-012-S1, AOS-012-S2, AOS-012-S3; owning files/interfaces above | AOS-012-TC01, AOS-012-TC02, AOS-012-TC03, AOS-012-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-012-S1](../cursor/prompts/AOS-012-S1.md) | AOS-002, AOS-007 | Versioned eligible/denied route and normalized usage/outcome schemas linked to task/policy/correlation. | AOS-012-TC01; command/report/exit, immutable evidence and diff |
| [AOS-012-S2](../cursor/prompts/AOS-012-S2.md) | AOS-012-S1 | Separate authorized/accessible/observed disclosure records, corrected output versions and consent/retention boundaries. | AOS-012-TC02; command/report/exit, immutable evidence and diff |
| [AOS-012-S3](../cursor/prompts/AOS-012-S3.md) | AOS-012-S2 | Restart reconstruction, unknown-value and poisoned-correction fixtures; secret-safe API/report views. | AOS-012-TC01, AOS-012-TC02, AOS-012-TC03, AOS-012-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-012-TC01 | contract | `tests/integration/test_aos_012.py::test_usage_unknown_not_zero` | Unknown amount/quota remains null with confidence status; native plan allowance and API cash distinct. |
| AOS-012-TC02 | integration | `tests/integration/test_aos_012.py::test_routing_replay_restart` | DB alone reconstructs selected route and every rejection reason after process restart. |
| AOS-012-TC03 | security | `tests/integration/test_aos_012.py::test_correction_is_not_authority` | Correction cannot overwrite original evidence or permit denied route; model suggestion cannot manufacture consent. |
| AOS-012-TC04 | contract | `tests/integration/test_aos_012.py::test_exposure_three_dimensions` | Accessible encrypted CLI workspace is not claimed actually transmitted; observed network metadata and authorized policy are separately recorded. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_012.py --junitxml=evidence/AOS-012.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

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

## Revision 3 extension — MVP-X11, delivered in R3

The [active personal-platform contract](../specification/architecture/05-PERSONAL-PLATFORM-REVISION-3.md#mvp-x11) adds **Quota-aware useful work and automatic offline capture**. Original parent scope and historical results remain intact. These new slices deliver in **R3**, even when the parent AOS item originally ships in R1; they do not reopen historical G0 acceptance or fabricate G1 evidence. Inspect the current repository before choosing exact new files/migration revisions.

| Slice | Concrete outcome, narrowed to about one developer-day | Prerequisites |
| --- | --- | --- |
| AOS-012-S4 | Implement scoped quota observations, owner input, freshness and truthful confidence/UI data. | AOS-012-S3, AOS-010-S3 |
| AOS-012-S5 | Implement the bounded preferred-provider queue, reserves and foreground admission. | AOS-012-S4, AOS-026-S3 |
| AOS-012-S6 | Implement offline validated-result/eligible-example capture with separate purpose/rights checks. | AOS-012-S5, AOS-011-S6 |
| AOS-012-S7 | Prove restart/cancel/limit/no-paid-spillover behavior and expose operator controls. | AOS-012-S6, AOS-029-S3 |

Use the [revision-3 slice handoff](../cursor/prompts/MVP-REV3-SLICE.md) with the selected manifest entry. File ownership candidates are in implementation-slices.json; record an ADR for a material change. Existing shared transaction/security/API requirements still apply.

| Added case | Lane | Required passing behavior |
| --- | --- | --- |
| AOS-012-TC05 | contract | Fresh provider-reported, owner-reported, estimated and unknown quota observations retain source/time/window/model/reset metadata; unknown is not zero or unlimited and may permit authorized bounded best-effort work. |
| AOS-012-TC06 | integration | Reported 40%-before-reset evidence schedules valuable preferred-provider tasks; overlapping windows, regular-use reserves, observation freshness and foreground priority govern bounded admission. |
| AOS-012-TC07 | security | Background policy permits only the approved billing/entitlement route and per-job budgets; missing no-extra-spend proof denies that mode and quota exhaustion never silently enables paid API/extra usage or another provider. |
| AOS-012-TC08 | integration | Results are retained offline with protected inputs/outputs, model/version, provenance, privacy, validation and retention lineage; unverified architecture advice remains a proposal. |
| AOS-012-TC09 | security | Knowledge/reference permission and training eligibility are independent; unknown/restricted rights and contaminated/unverified examples cannot enter training exports; permitted curated examples survive offline export/restore. |
| AOS-012-TC10 | chaos | Restart, cancellation, foreground preemption and provider limit/reset observations preserve queue/outcome state; ambiguous inference is reconciled without blind duplicate paid work or retry storms. |

These nodes and scenarios are planned, not observed tests. Register real assertion/node/lane/evidence mappings while implementing; missing required evidence blocks G3. Rollout begins disabled, uses synthetic content until its boundary is certified, stops admissions on failure and preserves audit/receipts. R4-R7 work is not authorized by completing this extension.

## Observed quota component (2026-10-16)

The active implementation now includes `contracts/quota.py`, `kernel/quota.py`
and owner-scoped `/v2/quota` input/read/current routes, additive migration0029 and
an actual schema snapshot. See [design43](../design/43-QUOTA-OBSERVATIONS.md),
[operator review](../testing/QUOTA_OBSERVATIONS.md) and
[evidence](../../evidence/quota-observations-2026-10-16/REPORT.md). Clean cdf3e35
passes172 focused checks (67 new), including real PostgreSQL transactions/races,
HTTP revocation, actual expiry and dump/restore. The preserved earlier status
headers are not proof of current implementation or release acceptance.

S4/TC05 remains partial: source lanes retain truthful metadata and owner input is
implemented, but provider/estimate ingestion fixtures do not qualify a supported
live telemetry source or a Mission Control display. The bounded queue, foreground
reserve, exhaustion/no-paid-spillover policy, actual offline capture and remaining
S5–S7/TC06–TC10 remain required. No gate status is promoted by this report.

## Confirmed Build offline-reference component

[Design68](../design/68-OFFLINE-BUILD-REFERENCES.md) and the
[operator guide](../testing/OFFLINE_BUILD_REFERENCES.md) implement one S6 outcome:
manual or explicitly opt-in capture after canonical PUBLIC Build final verification
and an exact confirmed owner merge. A bounded private archive carries exact
contract/diff/check evidence and historical provenance, with standalone integrity-
checked restore/viewing. It grants only local-reference retention, never training
consent; eligibility remains UNKNOWN/export DENIED. No queue, raw-model truth,
knowledge promotion or weight update is implied. Source-bound component checks
are linked from the guide. Other modes, S5 queue/reserves, separate purpose/rights
flows, known model identity, suppression/retention and full TC08/09 remain pending.
