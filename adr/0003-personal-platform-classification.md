# ADR 0003 — Canonical classification for the personal platform

**Date:** 2026-10-15. **Decision:** accepted planning contract; implementation/migration pending. **Owners:** AOS-007/011, MVP-X07. **Baseline inspected:** `7f39028`.

## Context

The goal contract and design use PUBLIC/INTERNAL/CONFIDENTIAL/RESTRICTED. Runtime policy/memory use PUBLIC/PRIVATE/RESTRICTED/UNKNOWN. A profile vault, exported context and connection grants require one defined interpretation. Code presence and historical R0 acceptance do not resolve this later boundary.

## Decision

Use PUBLIC < INTERNAL < CONFIDENTIAL < RESTRICTED as canonical authorized data classes. UNKNOWN remains a deny-only diagnostic; invalid/unknown input cannot become an authorized goal classification. Every derived output retains the strictest source classification and all applicable purpose/destination constraints unless a separately authorized, evidence-bound reclassification applies.

PRIVATE is a legacy runtime value with no automatic lower-class synonym. Preserve its historical representation and introduce an audited compatibility resolution. Until explicitly resolved, give it effective RESTRICTED treatment. Store source identity, original value, effective canonical value, resolving policy/actor/version and evidence, without rewriting immutable original rows. Restrictive compatibility must not silently enable a previously prohibited action or cloud route. New APIs stop emitting PRIVATE only after versioned compatibility is implemented.

Introduce forward migrations from the actual applied head, update policy/source/derived/context/model/grant boundaries together, and prove the full classification-by-destination/action matrix including stale clients, existing PRIVATE records, downgrade attempts and unknowns. Do not mechanically edit old evidence, frozen schemas or deployed migrations as if this decision were already implemented. Existing goal-contract classification semantics remain intact; runtime APIs/policies use versioned migration.

The first encrypted owner profile is a bounded local object. Keys are outside DB/worker/backups; plaintext restricted profile text is excluded from general FTS and prohibited egress. Local decryption necessarily trusts the profile service and authorized inference process, not an imaginary model-only cryptographic boundary. This decision does not claim immunity from host compromise.

## Consequences and rollout

Full design/migration analysis is required before enabling sensitive profiles. Public/synthetic fixture work and independent R1 implementation can continue. Historical G0 acceptance remains for its original candidate/scope. New compatibility/vault evidence is required by revision-3 G3, and sensitive-profile enablement requires it earlier if exposed. Unknown migration/eligibility denies the affected sensitive action instead of widening permissions. On failure stop admissions, preserve audit and use compatible restore/forward repair.
