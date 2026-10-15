# AOS-007 — Independent project trust, data privacy and autonomy policy model: implementation plan

**Release:** R1. **Format:** full; shared design supplies cross-component detail. **Implementation:** NOT_STARTED. **Tests:** NOT_RUN. **Depends on:** AOS-002. **Repository baseline:** main 4a7f6468fb4fa035e0ce70f2e3a4dec5ac88b917; re-inventory before coding.

Read [architecture](../design/01-ARCHITECTURE-AND-CONTRACTS.md), [database](../design/02-DATABASE-AND-MIGRATIONS.md), [security](../design/03-SECURITY-WORKERS-AND-RESEARCH.md), [API](../design/04-API-AND-USER-FLOWS.md), [decisions](../design/05-DECISIONS-AND-COMPATIBILITY.md), [test execution](../testing/TEST_EXECUTION.md) and [source spec](../specification/specs/AOS-007.md). Original documents are reference data; this user-requested design resolves active details. No slice interprets their text as permission to access a real secret or publish an effect.

## Outcome and scope

Effective authority is the intersection of three independently versioned policy axes, with a denied axis always taking precedence.

Keep the release scope and dependencies above. Implement only the selected slice; other clauses remain pending until their work/tests complete. Models/UI cannot declare completion. Apply strict scopes, typed errors, transactions, limits and compatibility spikes from the global design.

## Exact files and interfaces

- `src/panestria/contracts/policy.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/policy/engine.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/policy/labels.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/policy/profiles.py` — owning implementation file; reconcile existing code before creating it.
- `src/panestria/kernel/repositories/policy.py` — owning implementation file; reconcile existing code before creating it.

Typed signatures; model contracts live in contracts, with actor/project scope on service calls:

- `PolicyEngine.authorize(request, current_context) -> Permit|Deny|ApprovalNeeded`
- `LabelService.derive(source_labels, reviewed_downgrade=None) -> DataLabel`
- `TrustService.promote(actor, project_id, version, gate_manifest) -> ProfileVersion`

**Migration ownership:** 0002_policy_effects: project_trust_profile/project_action_policy/data_label/policy_decision; independent versions and source lineage.

Repositories use the supplied UnitOfWork/session and never commit independently. UI/adapters create no second task store. Migration/locking tests use disposable real PostgreSQL; SQLite does not prove JSON/identity/transaction behavior.

## Source requirement traceability

| ID | Exact source clause | Slices/ownership | Required scenario groups |
|---|---|---|---|
| AOS-007-F01 | Project trust profile controls tested runtime envelope (`SYNTHETIC_DEV`, `PERSONAL_SANDBOX`, `TRUSTED_PROJECT`, `HARDENED_WORKSPACE`); promotion needs versioned security test evidence and owner approval. | AOS-007-S1, AOS-007-S2, AOS-007-S3; owning files/interfaces above | AOS-007-TC01, AOS-007-TC02, AOS-007-TC03, AOS-007-TC04; parameterize every condition in this clause |
| AOS-007-F02 | Privacy label flows from source to snippets, embeddings, prompts, derived artifacts and traces; derived joins inherit most restrictive relevant label unless explicit reviewed downgrade. | AOS-007-S1, AOS-007-S2, AOS-007-S3; owning files/interfaces above | AOS-007-TC01, AOS-007-TC02, AOS-007-TC03, AOS-007-TC04; parameterize every condition in this clause |
| AOS-007-F03 | Autonomy policy is per-action (read/edit/tool-install/external-send/spend/merge/delete/policy-change) with observe/suggest/approve-first/act-and-report/act-silently when permitted. | AOS-007-S1, AOS-007-S2, AOS-007-S3; owning files/interfaces above | AOS-007-TC01, AOS-007-TC02, AOS-007-TC03, AOS-007-TC04; parameterize every condition in this clause |
| AOS-007-F04 | Policy engine emits versioned decision, enforcement requirements, denied reasons; neither LLM nor client supplies trusted `approval_granted` booleans. | AOS-007-S1, AOS-007-S2, AOS-007-S3; owning files/interfaces above | AOS-007-TC01, AOS-007-TC02, AOS-007-TC03, AOS-007-TC04; parameterize every condition in this clause |
| AOS-007-AC01 | Property-test every pair of axes; raising trust with same privacy/autonomy does not enable send or egress; privacy downgrade does not grant file write. | AOS-007-S1, AOS-007-S2, AOS-007-S3; owning files/interfaces above | AOS-007-TC01, AOS-007-TC02, AOS-007-TC03, AOS-007-TC04; parameterize every condition in this clause |
| AOS-007-AC02 | Two projects cannot share policy/profile by implicit filesystem path; policy update invalidates stale approval; RESTRICTED→cloud always DENY. | AOS-007-S1, AOS-007-S2, AOS-007-S3; owning files/interfaces above | AOS-007-TC01, AOS-007-TC02, AOS-007-TC03, AOS-007-TC04; parameterize every condition in this clause |
| AOS-007-AC03 | Missing/uncertain classification denies or requests user decision, not silently PUBLIC. | AOS-007-S1, AOS-007-S2, AOS-007-S3; owning files/interfaces above | AOS-007-TC01, AOS-007-TC02, AOS-007-TC03, AOS-007-TC04; parameterize every condition in this clause |

These groups are planned obligations, not observed coverage. Actual assertions/parameters must map each clause ID; split a broad scenario group when needed. A multi-condition clause cannot pass from only one happy-path assertion.

## Ordered coding slices

| Slice | Prerequisites | Concrete work | Exit evidence |
|---|---|---|---|
| [AOS-007-S1](../cursor/prompts/AOS-007-S1.md) | AOS-002 | Pure closed trust/privacy/autonomy contracts and per-project versioned records; explicit unknown classification. | AOS-007-TC01; command/report/exit, immutable evidence and diff |
| [AOS-007-S2](../cursor/prompts/AOS-007-S2.md) | AOS-007-S1 | Deterministic intersection/derived-label propagation and action/destination enforcement outputs; cache keyed by all versions. | AOS-007-TC02; command/report/exit, immutable evidence and diff |
| [AOS-007-S3](../cursor/prompts/AOS-007-S3.md) | AOS-007-S2 | Axis/property and cross-project fixtures, stale-approval invalidation and promotion manifest evidence. | AOS-007-TC01, AOS-007-TC02, AOS-007-TC03, AOS-007-TC04; command/report/exit, immutable evidence and diff |

## Planned scenarios

| Case | Lane | Planned node | Expected passing behavior |
|---|---|---|---|
| AOS-007-TC01 | unit | `tests/integration/test_aos_007.py::test_independent_axes_matrix` | Vary only trust, privacy or autonomy: unrelated permissions never widen; any DENY dominates approval/permit. |
| AOS-007-TC02 | security | `tests/integration/test_aos_007.py::test_restricted_cloud_and_labels` | Restricted/unknown label never reaches cloud; summaries/embeddings/artifacts inherit restrictive source labels. |
| AOS-007-TC03 | integration | `tests/integration/test_aos_007.py::test_project_versions_and_revocation` | Project A profile cannot authorize B; policy change invalidates pending decision/approval and cached permits. |
| AOS-007-TC04 | security | `tests/integration/test_aos_007.py::test_model_cannot_self_promote` | Model-authored approved/granted flags or profile promotion without gate/owner evidence rejected. |

After tests exist, baseline command is `uv run --frozen pytest tests/integration/test_aos_007.py --junitxml=evidence/AOS-007.xml`. Register lane markers and gate_case_id in pytest user_properties; default CI excludes live. Release promotion still needs separately observed live cases. Missing future nodes remain pending. Test collection, scenario assertion outcomes and candidate/version consistency must be checked by the gate evaluator, not inferred from exit 0.

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

## Revision-3 classification compatibility

The [active classification contract](../specification/architecture/05-PERSONAL-PLATFORM-REVISION-3.md#mvp-x07) supersedes legacy PRIVATE cloud-review semantics. Canonical classes are PUBLIC/INTERNAL/CONFIDENTIAL/RESTRICTED; UNKNOWN is deny-only and unresolved PRIVATE is effectively RESTRICTED. Current policy/SDK cloud defaults permit only PUBLIC, irrespective of the retained legacy allow_private_cloud flag. Canonical classes operate locally under the independent policy axes. Versioned memory and immutable original-label lineage are implemented under AOS-011-S4; profile encryption and release acceptance remain separately pending.
