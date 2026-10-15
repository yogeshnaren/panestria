# Initial revision-3 source inventory

Inspected source `ab7a4ab` with a clean worktree on 2026-10-15 using
`python -m panestria.verification.readiness --gate G3`. This is static source
navigation, with **release verdict NOT_EVALUATED**. Exit 1 reports inventory
gaps; it is neither a failed application test nor a release-gate evaluation.

- Final G3: 157 required scenarios; 56 have a directly discoverable literal
  test registration. Pretrial excludes the owner/trial scenario and requires156.
- Current R1 cumulative manifest: 72 scenarios; 56 have discoverable literal
  registrations. Many expected node names differ from real source, and some
  registrations are dynamic or indirect. Reconcile rather than assuming absent
  functionality or accepting a whole file because its name matches.
- Explicit live annotations disagree with catalog flags for AOS-008-TC01,
  AOS-008-TC02, AOS-008-TC04, AOS-027a-TC01 and AOS-018-TC02. Preserve the actual
  source/OS obligations while correcting their mappings; no mock substitution.
- All33 revision-3 extension scenarios remain required. No existing default
  suite or old124-case evaluator can certify the new MVP.

Historical R0 acceptance remains source-bound and unchanged. Missing literal
registrations here do not invalidate its existing receipts. The inventory does
not establish complete assertion coverage, execution or evidence authenticity.

Local verification of this task:17 inventory regression tests pass, including
manifest drift, duplicate names, source non-execution, symlink escape, live
annotation detection and separate pretrial/final inventories. Ruff, strict
source typing and all10 import-boundary contracts pass. Full PR CI is required
before merging. Required provider/OS/phone/host/trial evidence remains pending.

Next: reconcile the R1 source/receipt mappings and real live prerequisites;
continue independent missing feature slices, beginning with the canonical
classification boundary before sensitive profile storage. Keep implementation,
source registration, executed evidence and owner acceptance separate.
