# Classification compatibility rollout

This implements the conservative first step of
[ADR 0003](../../adr/0003-personal-platform-classification.md) under AOS-011-S4.
It does not complete that slice or AOS-011-TC05 and does not enable profiles.

## Step 1: restrictive interpretation before migration

The goal contract's PUBLIC/INTERNAL/CONFIDENTIAL/RESTRICTED wire vocabulary and
hashing stay unchanged, now using a shared canonical type. A pure compatibility
resolver returns canonical values, UNKNOWN diagnostic state, or effective
RESTRICTED for legacy PRIVATE. Derived classification preserves the strictest
source; missing/invalid lineage denies classification. This resolver grants no
authority to reclassify a stored record or weaken source-purpose constraints.

The existing version-1 policy/inference request vocabulary still accepts legacy
PRIVATE for compatibility, and existing local workflows remain available under
their other policy constraints. Cloud policy decisions and the SDK's own
pre-transport guard now deny unresolved PRIVATE. The old allow_private_cloud
field remains in policy bodies/hashes for historical compatibility but cannot
override this restriction. No caller approval, autonomy mode, destination or
trust increase can turn unresolved legacy data into public data.

No existing policy, task, source, context, model request or evidence row is
rewritten. No migration or new public canonical-label API is deployed here.
Policy decision reasons and original request/policy digests retain the legacy
input distinction. SDK denial happens before authorization/reservation/client
creation; tests use synthetic credentials and mocked transport only. The shared
interpretation is not a claim that every future connector is already migrated.

## Remaining steps in the same slice

1. Design and test an additive migration from the actual Alembic head. Persist
   source/original/effective label, policy/actor/version and resolution evidence;
   preserve immutable history and keep unresolved PRIVATE effectively restricted.
2. Introduce versioned policy/memory/context/learning/grant interfaces using the
   canonical classes together. Recheck every read, derived label and outbound
   boundary; old clients must not acquire a new export path.
3. Test real PostgreSQL upgrade/restore, existing PRIVATE data, stale clients,
   downgrade attempts and the complete class/destination/action matrix. Run the
   independent source-bound acceptance scenario before completing TC05/S4.
4. Only then implement and certify profile encryption/key/restore/context checks
   in S5/S6. Sensitive profiles remain disabled until that boundary is verified.

Deploy this first step as a conservative admission restriction. An unresolved
private cloud request is denied rather than rewritten or retried against another
provider. Reverting only this restriction would reopen the old PRIVATE export
path and is not an acceptable privacy recovery action; stop affected admissions
and forward-repair while preserving history. This change makes no live provider
compatibility or whole-platform security certification claim.
