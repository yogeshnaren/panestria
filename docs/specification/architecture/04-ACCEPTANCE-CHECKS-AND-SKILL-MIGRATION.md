# Canonical acceptance checks and goal-contract skill migration

**Authoritative v1 discriminators:** `trusted-command-ref`, `git-diff-path-check`, `policy-decision`, `artifact-exists`, `human-review`, `citation-check`, `rubric-review`. All active specs, schemas and examples use `acceptance[].verifier.type`; `required` is explicit. The registry and JSON Schema in `contracts/` are the machine-readable source of truth. SQL and generated Pydantic types must match them exactly.

| Type | Meaning and required evidence | First implementation |
|---|---|---|
| `trusted-command-ref` | Reviewed immutable command registry reference; fixed argv, expected exit code, bounded timeout/output and sandboxed runner; retain report, command registry version and candidate tree hash | R0 synthetic only |
| `git-diff-path-check` | Allowed and forbidden paths against exact base/candidate tree; canonical path and symlink checks; retain diff/path report | R0 |
| `policy-decision` | Kernel policy evaluation of an action equals allow, deny or approval-required; retain policy version, actor and scope. A result of approval-required is evidence of a guard, not authorization to execute | R0 |
| `artifact-exists` | Protected artifact reference exists and content SHA256 matches; existence of an arbitrary file alone cannot establish success | R0 |
| `human-review` | Authenticated named reviewer examines immutable evidence tied to contract/candidate hash, records verdict and rationale | R0 |
| `citation-check` | Retained source manifest, hashes, passages and claim references; deterministic provenance/quotation report; source support assessed separately | R2 draft |
| `rubric-review` | Versioned rubric and calibration fixtures plus named human sign-off; model scoring is advisory and cannot alone pass a required check | R2 draft |

Verdicts are `PASS`, `FAIL`, `UNKNOWN`, `ERROR`. Required checks need PASS plus immutable evidence for the current contract and candidate. No `unverifiable` discriminator exists: turn an uncheckable requirement into a scoped human review or revise the contract before admission. Unsupported future check types are denied even if their JSON is structurally valid. Completion enforces both check verdicts and separate action authorization.

## Migration from attached v0.1.0 skill (reference only)

The original `agentos-skills-v0.1.0.zip` remains byte-for-byte preserved. Its validator currently uses `acceptance[].check`, lowercase privacy labels, budget fields in minutes and an older contract envelope. Updating only its enum is insufficient; the user can update the skill using this guide. AgentOS admission must not silently accept or widen a legacy contract.

| Legacy spelling | Canonical type | Migration rule |
|---|---|---|
| `command`, `trusted-command` | `trusted-command-ref` | Replace raw `run` or `command` with a human-reviewed `command_ref`; never auto-register arbitrary shell text |
| `path_scope`, `diff-path-check` | `git-diff-path-check` | Require both allowed and forbidden path lists and exact comparison trees |
| `file_exists` | `artifact-exists` | Import only scope-validated evidence into protected storage; bind artifact reference and actual hash |
| `citations` | `citation-check` | Supply immutable source and claims manifests; legacy citation IDs alone are insufficient |
| `rubric` | `rubric-review` | Add versioned rubric, calibration set and authenticated reviewer; model-only verdict is insufficient |
| `human_review`, `manual-evidence`, `human-approval` | `human-review` | Typed review and evidence; an action approval is a separate digest-bound authorization record |

1. Use `schema_version`, `goal_id`, `contract_version`, `owner_id`, `project_id`, `privacy_class`, trust and autonomy fields from the shared contract. Reject unknown fields; preserve a signed/hashed legacy export for provenance.
2. Rename `check` to `verifier`, normalize explicitly reviewed privacy values to uppercase, convert minutes to integer seconds without changing limits, and fill owner/project/constraint fields through a reviewed migration.
3. Require `required`, typed evidence rules and type-specific fields. Reject duplicate IDs, booleans used as numeric limits, non-finite budgets, paths outside scope and placeholders. Apply JSON Schema plus semantic registry/policy checks.
4. New immutable contract version/hash invalidates prior approval. Do not change old approved JSON in place. Store the source hash and migration version.
5. Skill acceptance tests: all seven canonical variants parse; every old discriminator and arbitrary command field is rejected; future unimplemented runners are denied; missing/UNKNOWN checks block completion; human review cannot bypass merge approval.

R0 example nodes are in `contracts/acceptance-examples.json`. Their data validates against the acceptance-node schema; resolving registry, actor, paths and artifact references remains an implementation test in AOS-002/004/005.
