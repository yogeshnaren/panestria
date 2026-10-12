# Goal progress

**Phase:** R0, contract version 1 approved. The 2026-10-12 review did not accept R0. R1 has not started.  
**Slice:** Corrections through the loopback server are committed. No further phase is authorized.  
**Branch:** `r0-kernel`.  
**Last verified source commit:** `0eb6cefcefae01ca529b4bce956e800a6b71f2ac`.  
**Evidence commit:** recorded after that source commit; this file is not part of the tested tree.  
**Gate:** G0 is `INCOMPLETE`. Nineteen required cases were collected. AOS-001-TC04 is `NOT_RUN`. A collected case id is not a claim that every source clause passed, and it is not owner acceptance.

## Completed

AOS-001-S1 through AOS-005-S3 and the review corrections are on `r0-kernel`. The non-live suite on `0eb6cefcefae01ca529b4bce956e800a6b71f2ac` collected 122 tests, 0 failures, and 0 skips in `evidence/R0-corrections.xml`, and deselected the live fresh-host test. That run includes the per-node verifier denials, latest-result selection, admitted DBOS restart, Git reconciliation, dispatch-time authorization, artifact epoch checks, stored-graph cycles, goal idempotency, malformed envelopes, body and database bounds, and a separate loopback process driven by the CLI. Items AOS-001 through AOS-005 remain `IN_PROGRESS`.

## Failures and blockers

AOS-001-TC04 is `tests/integration/test_aos_001.py::test_fresh_host_loopback` in `ae4e142`. It is marked `live`. It fails with `fresh_host_not_attested` before starting a server. The same measurement passed against the disposable database on this machine and recorded that process's loopback socket, startup, and RSS. That run is not a fresh Ubuntu host. That failure is not a gate pass. G0 cannot pass while the case is `NOT_RUN`. No owner review of the corrected candidate has been recorded. ADR 0002 records the global event lock and the effect-digest binding already implemented in this tree. The earlier group PASS marks on `af3d431` did not exercise the review counterexamples; those receipts stay historical and are not rewritten. `tests/e2e/test_aos_005.py::test_loopback_submit_scope_and_replay` still has no `gate_case_id`. `make r0-demo` was run on this machine against the disposable database after `fc359b0` and printed one `COMPLETED` goal. On 2026-10-12, `make db-up` and `make db-migrate` reached Alembic head `0004_check_candidate`, `make db-down` left `panestria_s3_pgdata` in place, and `make reset-synthetic-data` removed that volume. Those runs are not AOS-001-TC04 and do not accept R0.

## Evidence

`evidence/R0-corrections.xml` and `evidence/G0/evaluation.json` name `0eb6cefcefae01ca529b4bce956e800a6b71f2ac`. `evidence/R0-demo-transcript.json` records two completed `make r0-demo` runs on the disposable database. `docs/design/schema-erd.md` is the diagram generated from that migrated schema. `evidence/R0-dbos-crash-transcript.txt` is a separate two-test restart run on that same source. `docs/ARCHITECTURE.md` describes that implementation. None of these artifacts is AOS-001-TC04. `docs/SETUP.md` records the local install, database reset, and demo commands. It does not record a fresh-host startup time or idle RSS.  
Earlier slice receipts remain under `evidence/AOS-001-S1/` through `evidence/AOS-005-S3/` and name their own source commits.  
The review package is `docs/reviews/R0-HANDOFF.md`.

## Approved permissions

`contracts/phase/r0-phase.approval.json` records the owner approval of contract version 1. It is not the R0 handoff review and it does not authorize a product effect. Application API spend remains zero. Disposable PostgreSQL and frozen `uv` installs are allowed.

## Next action

Stop for review of the corrected candidate. Do not start R1, do not mark G0 or any R0 item accepted, and do not invent the owner review or a fresh-host result.

## Resume

Continue from the latest commit on `r0-kernel`. Inspect Git and `evidence/` before changing anything. The immutable contract stays at the approved hash until a new version is approved. A fresh Ubuntu host is required before AOS-001-TC04 or a G0 pass can be recorded.
