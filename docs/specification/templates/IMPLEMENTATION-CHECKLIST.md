# Checklist plan — AOS-001 or AOS-004

Read the chosen spec, common requirements, canonical contracts, actual repository state and attached skill inventory. This is planning only. AOS-001/004 need this checklist; AOS-002/003/005 use the full template. Future release scopes remain draft.

Create plans/AOS-NNN-checklist.md:
- [ ] Outcome and scope, known existing source/hash/test facts and any relevant attached skill migration.
- [ ] Exact file/interface changes; one package layout and import checks for 001, synthetic adapter/verifier/evidence boundaries for 004.
- [ ] Slices targeting about one developer-day each; prerequisites, touched files and acceptance command per slice. Split oversized slices.
- [ ] Spec-specific positive and negative fixtures, command, expected exit/verdict and evidence artifact for each acceptance requirement.
- [ ] Applicable database changes or N/A; limits, cancellation/retry and safe cleanup.
- [ ] Minimal logging, setup/diagnosis and rollback; reviewer checkpoint and next slice.
- [ ] Open blocking questions only; explicit reversible assumptions otherwise. Never claim tests/implementation were observed when only proposed.

Do not duplicate the full production-plan sections when the above covers the slice. A shorter document does not waive the spec's acceptance/security tests. Implement only a reviewed first slice after planning.
