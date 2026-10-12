# Goal progress

**Phase:** R0, contract version 1 approved. The 2026-10-12 review did not accept R0. R1 has not started.  
**Slice:** Corrections through the loopback server are committed. No further phase is authorized.  
**Branch:** `r0-kernel`.  
**Last verified source commit:** `fc359b02bece73de30d07e7bf60f6e0af3372438`.  
**Evidence commit:** recorded after that source commit; this file is not part of the tested tree.  
**Gate:** G0 is `INCOMPLETE`. Nineteen required cases were collected. AOS-001-TC04 is `NOT_RUN`. A collected case id is not a claim that every source clause passed, and it is not owner acceptance.

## Completed

AOS-001-S1 through AOS-005-S3 and the review corrections are on `r0-kernel`. The non-live suite on `fc359b02bece73de30d07e7bf60f6e0af3372438` collected 109 tests, 0 failures, and 0 skips in `evidence/R0-corrections.xml`. That run includes the per-node verifier denials, latest-result selection, admitted DBOS restart, Git reconciliation, dispatch-time authorization, artifact epoch checks, stored-graph cycles, goal idempotency, malformed envelopes, body and database bounds, and a separate loopback process driven by the CLI. Items AOS-001 through AOS-005 remain `IN_PROGRESS`.

## Failures and blockers

AOS-001-TC04 has no fresh Ubuntu host. G0 cannot pass while that live case is `NOT_RUN`. No owner review of the corrected candidate has been recorded. The earlier group PASS marks on `af3d431` did not exercise the review counterexamples; those receipts stay historical and are not rewritten. `tests/e2e/test_aos_005.py::test_loopback_submit_scope_and_replay` still has no `gate_case_id`. `make r0-demo` starts the loopback server and the real CLI; it needs a migrated database and does not replace the fresh-host case.

## Evidence

`evidence/R0-corrections.xml` and `evidence/G0/evaluation.json` name `fc359b02bece73de30d07e7bf60f6e0af3372438`.  
Earlier slice receipts remain under `evidence/AOS-001-S1/` through `evidence/AOS-005-S3/` and name their own source commits.  
The review package is `docs/reviews/R0-HANDOFF.md`.

## Approved permissions

`contracts/phase/r0-phase.approval.json` records the owner approval of contract version 1. It is not the R0 handoff review and it does not authorize a product effect. Application API spend remains zero. Disposable PostgreSQL and frozen `uv` installs are allowed.

## Next action

Stop for review of the corrected candidate. Do not start R1, do not mark G0 or any R0 item accepted, and do not invent the owner review or a fresh-host result.

## Resume

Continue from the latest commit on `r0-kernel`. Inspect Git and `evidence/` before changing anything. The immutable contract stays at the approved hash until a new version is approved. A fresh Ubuntu host is required before AOS-001-TC04 or a G0 pass can be recorded.
