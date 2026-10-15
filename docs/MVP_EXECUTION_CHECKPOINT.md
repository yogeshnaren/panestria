# MVP execution checkpoint

Updated 2026-10-15. The owner authorized implementation through revision-3 R3,
focused task branches/PRs with coherent commits, and sequential merges after
passing CI and verification. Automatic continuation after usage resets is
authorized. Preserve original evidence, specs and skills; stop for actual R3
owner trial/acceptance, without beginning R4-R7.

## Starting point

Planning PR #49 merged at `e1664f54eeeb8b4dd65b44e99639f89e8b774132`.
Its final head passed 437 default tests, with 34 live checks deselected. This
does not certify G1 or the full MVP. R0 retains its source-bound acceptance;
R1 remains in progress; R2/R3 implementation and extension acceptance remain
pending. Follow the [main plan](PANESTRIA_PHASED_IMPLEMENTATION_PLAN.md).

New branches start from freshly fetched `origin/main`. Previously merged task
branches remain historical and must not be used as the base for new work.
Preserve the owner's review checkouts, running demo, databases and services.

## Completed foundation: readiness inventory

Add a read-only reconciliation of required gate cases, the catalog and actual
literal `gate_case_id` registrations in test source. Expose missing/planned
nodes, annotation mismatches and live requirements. Source registration alone
cannot establish execution, assertion completeness or release acceptance.
Do not build a permissive substitute for the planned trusted evidence evaluator.

Catalog at this starting point: 157 scenarios, 20 historical observations and
137 NOT_RUN records. Final G3 requires 157; pretrial readiness excludes only
AOS-030-TC04 and requires 156. Existing source may implement a scenario whose
catalog still says NOT_RUN; inspect its code and collect new source-bound proof
before changing acceptance status.

The inventory is implemented in `panestria.verification.readiness`; see
[usage/limitations](testing/MVP_READINESS.md) and the
[initial source inventory](reviews/MVP-READINESS-2026-10-15.md). Its 17 regression
tests, lint, typing and import checks pass locally. The focused task PR requires
full CI and review before merge. Source navigation is not release acceptance.

## Next work

Use the inventory and existing R1 plans to reconcile implementation and live
gaps. Continue ready local/fixture work while independent live prerequisites
wait. Implement remaining R1, R2 and R3 work plus MVP-X07-X14 in dependency order,
with an independently reviewable outcome per PR. Keep this checkpoint current
with commit/PR/test references and the exact next action before stopping.

No new account configuration, provider fallback, reset credits, credential
provisioning or broad model spending is authorized. Existing synthetic provider
test permissions remain scoped. Use real disposable databases and actual
required live evidence. Automated continuation does not replace the 14-day
owner trial, owner acceptance or a needed human action.

## Latest checkpoint: classification guard

Readiness PR #50 merged into main as d22c9f2 after exact-head CI passed 454 tests,
34 live deselected (run 38713323941). New independent branch
`task/privacy-classification-v3` began from e1664f5 and merged current main before
validation. It introduces the shared canonical goal type, conservative legacy
interpretation, and PRIVATE cloud denial in policy/SDK pre-transport checks.
The goal wire classes, stored records, applied migrations and evidence remain
unchanged. This is the first step of AOS-011-S4, now IN_PROGRESS; TC05 remains
NOT_RUN and sensitive profiles remain disabled. See classification rollout.

Local validation: 29 targeted classification/goal/policy/SDK tests passed,
2 database tests deselected in that targeted run; Ruff, strict mypy and all 10
import contracts passed. SDK tests hung inside the development process sandbox;
the same frozen offline/mock tests passed outside it in 0.90s. Three agent-owned
hanging diagnostic processes were stopped, without touching owner services.
Full PR CI must pass before merge; do not infer a complete slice or live pass.

At 99% usage, publish this focused PR and preserve its exact head. Resume by
checking its CI, reviewing the diff, merging only when passing, fetching main,
then implementing the audited forward classification migration and versioned
source/policy/context compatibility. Continue independent R1 evidence mapping
work as appropriate. Hourly continuation is enabled in the development chat;
no repeated approval to resume or merge verified MVP task PRs is needed.

## Latest checkpoint: immutable classification ledger

PR #51 merged as `2a4db7b` after exact-head CI passed 467 default tests,
34 live deselected (run 38714493560). Work resumed after the usage reset.
Branch `task/classification-ledger` starts from that current main.

The next substep adds migration 0018 and a scoped read-only classification
service. Existing sources backfill without changing original rows; new source
and classification records commit atomically. Consumed exact owner reviews
remain linked to new revisions, while old PRIVATE sources stay restricted.
Populated classification audit cannot be dropped by schema downgrade. The
active schema snapshots were regenerated from real isolated PostgreSQL and
contain additive changes only; applied migrations and old evidence are intact.

Eight targeted real database tests passed: old-data upgrade, audit preservation,
atomic rollback, scope/immutability, review consumption, existing memory review,
actual dump/restore and schema drift/round-trip. Ruff, strict mypy and import
boundaries pass. Full exact-head PR CI and final review remain required.

Next: merge only after CI/review, then implement versioned canonical memory
interfaces and canonical derived labels with conservative cloud defaults,
keeping old API/history/active-attempt compatibility explicit. Complete the
whole class/source/context/destination matrix before completing S4/TC05.
Profile encryption remains disabled and later MVP work remains pending.

## Latest checkpoint: key-store foundation

PR #53 merged as `b22c46c9e28f84b2a5ed9fc02e96cabecbe0b248` after corrected
exact-head CI passed 482 default tests, 34 live deselected (run 38730813894).
Branch `task/profile-secret-store` began at fresh main 2f8c983, then merged this
verified main. It pins cryptography/SecretStorage/Jeepney and adds a scoped,
bounded, non-prompting Linux key adapter. It does not enable profile storage.

Local source `3ec27b3eb921ec58c15f574a27133c8f52b497d3` passed 34 adapter checks
and one actual isolated OS keyring test, including daemon restart. Qualification
exposed GNOME's generic schema insertion; explicit schema binding fixes the
compatibility issue while preserving exact scope checks. Ruff, strict mypy
(150 files) and all 10 import contracts pass. See PROFILE_KEYS.md and component
evidence; no full vault case or release gate is promoted. Full exact-head PR CI
and final review remain required. Next implement bounded authenticated profile
ciphertext storage, broker-only reads and its real database failure matrix.

## Latest checkpoint: ciphertext vault storage

PR #54 merged as `df485486133a770f6059cb866a30c18fe58e5228` after exact-head CI
passed 516 default tests, 35 live deselected (run 38732648397). The isolated OS
key-store test passed separately. Branch `task/profile-ciphertext-vault` started
from that explicit prerequisite and merged verified main before validation.

Migration 0020 adds separate encrypted profile revisions, a scoped deferred
current pointer and immutable metadata-only lifecycle audit using the kernel's
global event counter. The caller-owned transaction commits state, ciphertext
and event together. The opt-in trusted vault loads existing scoped keys only;
it never provisions keys in database transactions. No profile API/dispatch is
enabled. General memory, FTS and historical data remain unchanged.

Thirty targeted real crypto/database/restore/schema checks pass. They include
tamper/scope/AAD swaps, CAS/concurrent writes, rollback, correction/rotation,
suppression/expiry, old/new actual snapshots with external retained keys and
refusal of destructive populated downgrade. Strict mypy (152 files), Ruff and
11 import contracts pass. See PROFILE_VAULT.md and component evidence. Full
exact-head PR CI and review remain required; TC06/TC07 and release gates are
not promoted. Next: approved-field local context selection and trusted local
setup/admission, then runtime privacy qualification and remaining MVP work.

## Latest checkpoint: canonical memory version 2

PR #52 merged as `2f8c983` after CI run 38727911700 passed 471 default tests, 34 live deselected. The dependent canonical branch incorporated that verified main merge before final CI. Separate commits cover design, canonical domain/migration, v2 API and execution tracking.

Migration 0019 accepts canonical labels without rewriting records. New contexts use effective canonical labels; v1 history and old pending pack identities remain compatible. V2 memory requires integer schema_version 2, canonical labels and exact version-bound owner reviews. Non-public cloud requests remain denied; missing classification or falsely public contexts stop before dispatch. Profiles are not enabled.

All 41 affected tests passed locally, including the class/action/destination matrix, actual PostgreSQL upgrade/restore, v1/v2 review isolation, scope, suppression and legacy context identity. Ruff, strict mypy, all 10 import contracts and secret scan passed. The active schema snapshot was generated from isolated actual PostgreSQL. Full exact-head CI/review is still required before merge. TC05 node mapping now points to the implemented integration file; formal G3 evidence and the full MVP remain pending.

Next: verify/merge the canonical PR, then implement the bounded encrypted profile broker/vault and fail-closed OS secret-store adapter under S5/S6, with actual key-store conformance separate from fake fixtures. Keep new sensitive-profile use disabled until that boundary is verified. Continue independent R1 and other MVP work while live prerequisites wait.
