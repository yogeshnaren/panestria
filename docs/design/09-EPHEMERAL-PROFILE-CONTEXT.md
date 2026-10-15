# Approved profile context is an ephemeral local overlay

This task builds on PR #55's opt-in ciphertext vault. The existing general
ContextCompiler stores source metadata and unkeyed prompt/question digests in
PostgreSQL, not the prompt body. Passing clear profile fields through that path
would disclose profile-derived search inputs/fingerprints, so use a separate
in-memory overlay and persist only revision/ciphertext/policy/request references.
No Ask/API/worker dispatch is enabled by this foundation.

An explicit request binds a profile, exact row version, purpose, selected fields,
byte budget and offline local-model destination. The encrypted owner document
must independently approve every selected field. Response-style purpose permits
only preferred name/communication preferences; general local assistance permits
the explicitly selected owner statements. These are owner statements, not
inferred psychological facts or new tool/privacy authority.

Selection checks current scoped project policy for RESTRICTED local read,
then loads the active exact profile revision. Locked/missing keys, stale version,
expiry, suppression, non-approved fields, invalid purposes/destinations and excess
bytes deny. It never searches general FTS or silently truncates facts. The result
is masked, labeled RESTRICTED and offline, with opaque source/policy metadata.
It has no plaintext fingerprint, persistent cache or automatic memory promotion.

Revalidation rebuilds from the current vault/policy before a later dispatch and
compares complete protected bytes plus source/policy identity. A correction,
approval change, rotation, suppression, expiry or policy change invalidates the
old selection. Locks protect the caller transaction; later effect admission must
recheck as well. Already delivered content cannot be recalled by suppression.

Actual local inference is a separate integration. A local Claude Code process
still uses remote inference and is denied as an offline destination. The future
Ask overlay must rework its claim/integrity checks and preserve restrictive output
labels without writing plaintext overlays into context packs, telemetry or input
hashes. Provider/runtime identity, mount/bus isolation and no-fallback evidence
are required before enabling personal-profile use. Returning a masked selection
object alone does not certify that runtime or any release gate.
