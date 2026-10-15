# Explicit local Ask application setup

The current R0 server starts synthetic work; Ask is only mounted in tests. A
supported local Ask server first needs project policy without inventing a goal
or task to satisfy `PolicyService.initialize`. Keep that historical API intact.

`panestria local setup --offline-ask --owner-id UUID --project-id UUID` is an
explicit local operator action using an existing PostgreSQL connection from the
environment. It creates only missing principal/project identities and a version-1
read-only policy in one caller-owned transaction. It never changes existing
policy, project ownership or repository paths. Repeated setup returns the same
audited policy; an already configured different project is refused.

The policy keeps SYNTHETIC_DEV (uncertified), permits only local read and denies
all cloud destinations, spending, tools, edits, merge and deletion. Setup is not
runtime certification, a trust promotion, a user grant, key provisioning or a
release pass. A later certified Build setup still uses exact owner review.

Migration 0022 adds an immutable `local_project_setup` receipt with owner/project,
fixed intent OFFLINE_ASK, schema version, policy version/hash and timestamp. Its
sequence uses the existing global task-event counter. It is project-scoped and
does not manufacture task events. Foreign keys and a trigger bind the receipt to
the exact scoped policy revision. Downgrade refuses populated setup history.
No credentials, profile values, prompt text or arbitrary operator notes enter it.

Prove atomic rollback, simultaneous repeated setup, conflicting ownership/policy,
read-only policy decisions, immutable receipt, schema upgrade/reapply and actual
dump/restore. CLI errors use fixed codes; no database URL/driver exception output.
The next focused task supplies the actual listener/model lifecycle, pairing and
Ask routes. R0 and the preserved review demo remain separate entry points.
