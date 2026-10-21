# Qualify the native Build runtime

`panestria native qualify-build` is an explicit operator command. It runs a
fixed reviewed conformance set in a clean source checkout, then issues a private,
expiring certificate for the pinned PUBLIC Bash Build runtime. It does not run
arbitrary project tests, accept supplied JUnit, approve project policy, or submit
an owner task.

Use a private checkout with frozen dev dependencies, Docker and the existing
pinned worker image. The existing pinned Claude Code 2.1.273 binary and private
authenticated `~/.panestria-native-claude` profile must be available. The command
does not log in, download models, install tools, provision credentials, use an
API key or fall back to another provider. Port 55439 must be free for its
disposable test database; do not run another R1 database suite simultaneously.
Keep source and reviewed runtime scripts free of group/other write permissions.

```bash
uv sync --frozen --group dev --offline
uv run --frozen panestria native qualify-build \
  --evidence-directory "$PWD/.panestria-runtime/native-qualification" \
  --public-subscription-smoke
```

The flag explicitly opts into one bounded PUBLIC synthetic Claude subscription
call. The remaining checks are local. The fixed 11 cases observe actual sandbox
UID, mounts, environment/credential separation, IPv4/IPv6 and DNS denial,
seccomp/cgroups, memory/output/time/process limits, cancellation and cleanup.
The native case checks hostile customization isolation, scoped Bash edits,
independent verification, wrong-digest rejection and exact scripted test-owner
approval. Authentication runs in a trusted host process; only model-invoked
tools run inside the secret-free OS sandbox. This certificate does not claim
that the authenticated CLI itself is containerized or that a human approved a
project change.

Expect JSON `status: PASS`, `cases: 11`, a certificate digest, an expiry and
`release_gate: NOT_EVALUATED`. Each private `run-*` directory retains the raw
JUnit, bounded pytest log and result journal. `latest.json` reports the latest
completed attempt, including failures. `certificates/` stores content-addressed
reports and the certificate. It is local operator state and must stay outside
Git, worker workspaces and cloud context. The certificate lasts 24 hours and
matches the source manifest, pinned CLI binary, tool profile and worker image.
It can be read by the general `CertificateStore`; it is not a fixed-demo or
test-fixture certificate. A separate owner-reviewed project policy must refer
to its digest before admitted Build can use that trust profile.

Expect exit 1 and `UNAVAILABLE` for missing prerequisites, any failed/skipped/
missing/duplicate case, dirty or changed source, fixture evidence, timeout,
interruption or unconfirmed cleanup. There is no automatic provider retry.
Inspect the private log, correct the reported prerequisite, and explicitly
rerun. Stop affected Build admissions after a failed qualification; a failed
run preserves previous certificate history and does not silently revoke prior
project policies. Use existing policy review to remove an affected grant.

The [source-bound result](../../evidence/r1-runtime-qualification-2026-10-18/report.json)
records 11 real passes in 25.82 seconds at clean `3f07e4b`. It is runtime-only
evidence. The supported owner task CLI, cumulative G1 evaluation and human
review remain separate. Paid SDK AOS-016-TC04 is deferred, not passed; no release
gate or owner acceptance status is changed.

The [2026-10-21 compatibility evidence](../../evidence/native-threshold-2026-10-21/report.json)
retains a later 10-pass/1-failure qualification and the corrected 11-pass run at
`686d1af`. The pinned CLI emitted optional `surpassedThreshold` rate metadata;
the parser now requires a finite numeric ratio in `[0,1]`, just as for
`utilization`. Neither value supplies usable quota or renews an observation.
Unknown fields, malformed ratios, rejected quota and paid overage still stop
execution. This is current runtime evidence, not a cumulative release pass.
