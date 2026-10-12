# Goal progress

**Phase:** R0, contract version 1 approved.  
**Slice:** AOS-005-S2 evidenced. Next is AOS-005-S3.  
**Branch:** `r0-kernel`.  
**Last verified source commit:** `eb5d6c333fef26abd1daad9ca46563e2128f3c21`.  
**Evidence commit:** recorded after that source commit; this file is not part of the tested tree.  
**Branch inspected:** `r0-kernel`.

## Completed

AOS-001-S1 hermetic TC01 passed on `af6794e112c888fd61b6e6b98a4824acab9c1681`. AOS-001-S2 toolchain gates passed on `99afb1a319e22fb24e86b7a4cc638a03e2557c0c`. AOS-001-S3 disposable PostgreSQL TC03 passed on `61d9e4729ded8e39d7a5ebc1048d803a6cdcab2b`. AOS-002-S1 canonical contracts passed on `834ae35db83126e9c96e8e9e320d0514ee39077a`. AOS-002-S2 kernel migration passed on `dee9dc2a316e46411e57efabaad01821b92a4d9e`. AOS-002-S3 scoped mutations passed on `57935008ce22ae484bd5065b72e587736180e132`. AOS-003-S1 atomic admission passed on `655a0c5fad43ec242bc4c2ea95d2bacadff86cd2`. AOS-003-S2 replay passed on `9a652c13f3cece672b25ec5b20b33e25f97ea2ea`. AOS-003-S3 lost-effect reconciliation and restore passed on `cd2b6b4e9512108bbb52cce1460c229f613f6874`. AOS-004-S1 scripted worker passed on `abf45f8634ebd326a0ce692ef8e0a0665e0905ea`. AOS-004-S2 independent checks passed on `9f4b764cbe0e32eaf22eccb7463bcac84ae57cae`. AOS-004-S3 watchdog and orphan cleanup passed on `c0ae53c634b1de8345e4a0901e2b46dfc9637e58`. AOS-005-S1 loopback submit, scoped reads, and typed replay passed on `44d30f0c159f0bc154da65f3497dffe617d1d5d9`. AOS-005-S2 locked approval decisions passed on `eb5d6c333fef26abd1daad9ca46563e2128f3c21`. G0 is `NOT_RUN`.

## Failures and blockers

AOS-001-TC04 has no fresh Ubuntu host. G0 cannot pass while that live case is `NOT_RUN`. AOS-003, AOS-004, and AOS-005 are awaiting review and are not accepted items. AOS-005-TC01, TC03, and TC04 were not collected. The CLI was forwarded through the test client; a separate TCP listener was not proven.

## Evidence

`evidence/AOS-001-S1/` names `af6794e112c888fd61b6e6b98a4824acab9c1681`.  
`evidence/AOS-001-S2/` names `99afb1a319e22fb24e86b7a4cc638a03e2557c0c`.  
`evidence/AOS-001-S3/` names `61d9e4729ded8e39d7a5ebc1048d803a6cdcab2b`.  
`evidence/AOS-002-S1/` names `834ae35db83126e9c96e8e9e320d0514ee39077a`.  
`evidence/AOS-002-S2/` names `dee9dc2a316e46411e57efabaad01821b92a4d9e`.  
`evidence/AOS-002-S3/` names `57935008ce22ae484bd5065b72e587736180e132`.  
`evidence/AOS-003-S1/` names `655a0c5fad43ec242bc4c2ea95d2bacadff86cd2`.  
`evidence/AOS-003-S2/` names `9a652c13f3cece672b25ec5b20b33e25f97ea2ea`.  
`evidence/AOS-003-S3/` names `cd2b6b4e9512108bbb52cce1460c229f613f6874`.  
`evidence/AOS-004-S1/` names `abf45f8634ebd326a0ce692ef8e0a0665e0905ea`.  
`evidence/AOS-004-S2/` names `9f4b764cbe0e32eaf22eccb7463bcac84ae57cae`.  
`evidence/AOS-004-S3/` names `c0ae53c634b1de8345e4a0901e2b46dfc9637e58`.  
`evidence/AOS-005-S1/` names `44d30f0c159f0bc154da65f3497dffe617d1d5d9`.  
`evidence/AOS-005-S2/` names `eb5d6c333fef26abd1daad9ca46563e2128f3c21`.

## Approved permissions

`contracts/phase/r0-phase.approval.json` records the owner approval of contract version 1. It is not the R0 handoff review and it does not authorize a product effect. Application API spend remains zero. Disposable PostgreSQL and frozen `uv` installs are allowed.

## Next action

Implement AOS-005-S3: the synthetic journey through consent, a mock candidate, independent evidence, and one approved effect. Restart and deny paths stay in this slice.

## Resume

Continue from the latest commit on `r0-kernel`. Do not restart from the initial README commit. The immutable contract stays at the approved hash until a new version is approved.
