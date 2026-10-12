# Goal progress

**Phase:** R0, contract version 1 approved. Review handoff is ready. R1 has not started.  
**Slice:** AOS-005-S3 evidenced. No further R0 slice is authorized.  
**Branch:** `r0-kernel`.  
**Last verified source commit:** `af3d431e775c2f3f23722d272dd00f2863689d5b`.  
**Evidence commit:** recorded after that source commit; this file is not part of the tested tree.  
**Gate:** G0 is `INCOMPLETE`. Nineteen required cases were collected on that commit. AOS-001-TC04 is `NOT_RUN`.

## Completed

AOS-001-S1 through AOS-005-S3 are implemented on `r0-kernel` with candidate-bound evidence. The integrated non-live suite on `af3d431e775c2f3f23722d272dd00f2863689d5b` collected 93 tests, 0 failures, and 0 skips. The synthetic journey completed one approved goal with one attempt and one confirmed git effect. Restart, deny, stale compare-and-swap, and the decision race were observed in the same report. Items AOS-001 through AOS-005 remain `IN_PROGRESS` and await review.

## Failures and blockers

AOS-001-TC04 has no fresh Ubuntu host. G0 cannot pass while that live case is `NOT_RUN`. No owner review of this handoff has been recorded. `make r0-demo` is still the nonzero stub. `/v1/artifacts/{id}`, `artifact show`, and `goal cancel` are not implemented; the journey reads the artifact hash from `evidence.recorded`. The CLI was forwarded through the test client; a separate TCP listener was not proven. `/readyz` does not open PostgreSQL.

## Evidence

`evidence/AOS-005-S3/` names `af3d431e775c2f3f23722d272dd00f2863689d5b`.  
`evidence/G0/evaluation.json` derives the incomplete gate from `evidence/AOS-005-S3.xml`.  
Earlier slice receipts remain under `evidence/AOS-001-S1/` through `evidence/AOS-005-S2/` and name their own source commits.  
The review package is `docs/reviews/R0-HANDOFF.md`.

## Approved permissions

`contracts/phase/r0-phase.approval.json` records the owner approval of contract version 1. It is not the R0 handoff review and it does not authorize a product effect. Application API spend remains zero. Disposable PostgreSQL and frozen `uv` installs are allowed.

## Next action

Stop for review of `docs/reviews/R0-HANDOFF.md`. Do not start R1, do not mark G0 or any R0 item accepted, and do not invent the owner review.

## Resume

Continue from the latest commit on `r0-kernel`. Inspect Git and `evidence/` before changing anything. The immutable contract stays at the approved hash until a new version is approved. A fresh Ubuntu host is required before AOS-001-TC04 or a G0 pass can be recorded.
