# Bounded Build proposal preflight

AOS-025-S1 introduces typed Build task proposals and a deterministic validator,
a prerequisite for the two-worker scheduler. It adds no dependency, database
schema/state, model/harness call, credential, worktree, permission or merge effect.
The existing one-worker Build path and frozen original specifications are intact.

A proposal binds exact owner/project/goal, canonical immutable goal-contract hash,
privacy class and the hash of the complete project/worker inventory envelope.
The inventory binds a base commit, project snapshot digest (`snapshot_sha256`),
worker binary/profile digests and capability/parallel limits. Its own canonical
hash becomes `proposal.inventory_sha256`. Caller-provided inventory metadata is
an input, not proof that its workers or capabilities are currently certified.
Future trusted inventory/admission must resolve those actual bytes/certificates.

Up to16 task nodes declare explicit dependency UUIDs, a selected worker, capability
refs, literal relative file paths, existing acceptance keys, expected artifact
names and per-attempt time/API-cash envelopes. Up to8 dependency levels and2
parallel slots are configurable downward. No model-generated command, shell,
path glob or new acceptance check is executable through this schema.

Validation rechecks typed instances and binds every scope/hash/class. It rejects
duplicate tasks, unknown/self dependencies, cycles, excess nodes/depth, unavailable
workers or capabilities, paths outside the immutable contract, unknown/missing
required checks, excess attempts and aggregate overbudget. Canonical path policy
uses the existing shared verifier pattern matcher; proposed paths themselves must
be literal, canonical, ASCII, without `.git`, traversal, shell characters or globs.
This deliberately narrow first proposal schema abstains on unsupported filenames.
Every node references at least one expected artifact and acceptance key, and all
required goal checks must be assigned. It cannot invent a new verifier command.

Aggregate API cash and serial wall envelopes include **every permitted retry**.
Concurrency is not assumed to reduce the admission bound. Quota observations,
foreground reserves, CPU/GPU capacity and exact provider eligibility are future
current-authority scheduler inputs; a validated DAG does not reserve them.
Ready layers are deterministic topological groupings, not grants to run every
node in parallel. The scheduler must obey total and per-worker parallel limits
and serialize overlapping path changes or present a conflict for review.

`panestria plan validate` reads bounded private contract/inventory/proposal files.
It prints hashes, task layers and envelope totals with `authority: PROPOSAL_ONLY`.
It prints no task paths, full input documents or raw failure. No plan/task row is
created. Subsequent AOS-025-S2/S3 must connect direct structured local proposal,
immutable canonical plan/task bindings, handoff, reviewed revisions and bounded
repair. AOS-026/027b must then integrate actual scoped workers and verify the final
tree before exact approval. Original case obligations and G3 remain open.

Validation covers independent branches with a join, a direct one-node plan,
cycle/scope/capability/check/budget refusals, safe literal paths, forged typed
instances and the actual private-file CLI. These are hermetic proposal checks,
not worker conformance, two-worker Build, final merge or full TC01/G3 evidence.
No external source code was borrowed; this is original code over existing schemas.
