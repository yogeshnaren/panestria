# 0011: Build on private repositories through explicit grants

Status: accepted owner decision (2026-10-28). Implementation pending; no code changes in this record.

## Context

Subscription-worker Build accepts only PUBLIC synthetic repositories. About twenty
separate `!= "PUBLIC"` checks enforce this; examples are `execution/owner_build.py`,
`execution/native_build.py`, `execution/native_plan.py`, `kernel/plan_run.py` and
`kernel/background.py`. Private data reaches only local-model workers. The spec's
trust, privacy and autonomy axes apply to the owner's real work, so this narrowing was
silent drift D2.

## Decision

1. **One policy function.** `policy.build_export_decision(contract, worker, grant)`
   replaces the scattered checks. It returns allow or deny with a typed reason.
2. **Rules by data class.**

   | Data class | Cloud subscription workers (Claude, Codex) | Local-model workers |
   |---|---|---|
   | PUBLIC | Allowed (unchanged) | Allowed |
   | INTERNAL | Allowed only with all three conditions below | Allowed |
   | CONFIDENTIAL / RESTRICTED | Denied: `cloud_export_denied_by_class` | Allowed |

   The three conditions for INTERNAL on a cloud worker:
   - a per-repository connection grant, reviewed through the existing connection
     broker and root handles;
   - `PrivacyAxis.allow_private_cloud` set, with the destination listed;
   - a per-run approval bound to the grant digest and an **export manifest** (paths and
     content hashes).
3. **Export snapshot.** The workspace given to a cloud worker is a snapshot taken
   through the root handle. It excludes `.git`, `.env*`, `.ssh`, `.aws` and similar
   credential paths, and the repository secret scanner blocks export on any hit.
4. **CLI.** `panestria connections grant-repo` creates and reviews the grant.

## Consequences

- B-1 becomes usable on real INTERNAL work. CONFIDENTIAL and RESTRICTED material
  never reaches a vendor CLI.
- The decision function gets an exhaustive matrix test, property tests and a mutation
  target of 90%.
- Residual risk: content the owner labels INTERNAL may still be sensitive. Labelling
  stays an owner responsibility, and the approval shows the export manifest.
