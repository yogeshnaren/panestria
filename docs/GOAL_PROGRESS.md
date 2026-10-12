# Goal progress

**Phase:** R0, contract version 1 approved.  
**Slice:** AOS-001-S2 evidenced. Next is AOS-001-S3.  
**Branch:** `r0-kernel`.  
**Last verified source commit:** `99afb1a319e22fb24e86b7a4cc638a03e2557c0c`.  
**Evidence commit:** recorded after that source commit; this file is not part of the tested tree.  
**Branch inspected:** `r0-kernel`.

## Completed

AOS-001-S1 hermetic TC01 passed on `af6794e112c888fd61b6e6b98a4824acab9c1681`. AOS-001-S2 toolchain gates passed on `99afb1a319e22fb24e86b7a4cc638a03e2557c0c`: lock check, Ruff, Mypy, Import Linter, secret scan, and 68 non-live tests. G0 is `NOT_RUN`.

## Failures and blockers

AOS-001-TC04 has no fresh Ubuntu host. G0 cannot pass while that live case is `NOT_RUN`. TC03 is not implemented.

## Evidence

`evidence/AOS-001.xml` and `evidence/AOS-001-S1/` name `af6794e112c888fd61b6e6b98a4824acab9c1681`.  
`evidence/AOS-001-S2.xml` and `evidence/AOS-001-S2/` name `99afb1a319e22fb24e86b7a4cc638a03e2557c0c`.

## Approved permissions

`contracts/phase/r0-phase.approval.json` records the owner approval of contract version 1. It is not the R0 handoff review and it does not authorize a product effect. Application API spend remains zero. Disposable PostgreSQL and frozen `uv` installs are allowed.

## Next action

Implement AOS-001-S3: scoped PostgreSQL, Alembic scaffold, and the setup runbook. Keep AOS-001-TC04 `NOT_RUN` until a fresh Ubuntu host exists.

## Resume

Continue from the latest commit on `r0-kernel`. Do not restart from the initial README commit. The immutable contract stays at the approved hash until a new version is approved.
