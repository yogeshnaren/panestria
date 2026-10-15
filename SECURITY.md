# Security

Panestria contains an accepted R0 synthetic kernel and R1 components; the complete R3 MVP is not accepted. Current release and source-bound evidence are in [the tracker](docs/phase-tracker.json). A merged component/default CI is not certification for arbitrary code, every native harness, sensitive profiles or public deployment.

## Reporting

Report vulnerabilities privately to the repository owner. Share a synthetic reproducer and source commit, not actual passwords, provider tokens or private project data.

## Current boundaries

The API binds loopback (127.0.0.1) by default with scoped authentication, Host/Origin/session/CSRF controls on the relevant flows. Workers use reviewed pinned profiles and separate no-secret verification; each enabled harness needs its exact OS/tool/auth compatibility proof. The native demo is a fixed public isolated exercise, not unrestricted app orchestration. Provider credentials remain in the approved local authentication boundary, not worker mounts, Git, URLs or logs. Preserve owner databases/services and use disposable test projects.

Existing memory filtering/provenance is not application-level profile encryption. Sensitive profile enablement requires [revision-3 classification/vault evidence](docs/specification/architecture/05-PERSONAL-PLATFORM-REVISION-3.md#mvp-x07); [ADR 0003](adr/0003-personal-platform-classification.md) defines the planned compatibility transition. Do not treat legacy PRIVATE as an automatically exportable canonical label. Host administrator compromise is outside application-session isolation claims.

## Planned boundaries

The revision-3 MVP includes explicitly enabled private authenticated TLS read-only phone access; it is not implemented by this documentation. Keep the current API loopback-only and public ingress disabled. A private network is not sufficient authentication. Phone approvals, background push, general desktop actions and voice expand later with their own evidence.

Quota-aware work uses scoped standing policy, reserves and no-extra-spend eligibility; stale/unknown measurements do not imply unlimited funds. Offline knowledge and training rights are separate. No documentation grants new account settings, provider spending, live inference or model-training authorization. API examples remain placeholders; health/errors must not disclose secrets. CI uses no real model credentials.
