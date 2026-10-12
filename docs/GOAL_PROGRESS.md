# Goal progress

**Phase:** R0 technical validation complete; owner review pending. R1 has not started.
**Branch:** r0-kernel.
**Verified source commit:** `d457242e9e6ee2c54fbd99db99cb35319b1c8783`.
**Gate:** G0 PASS — 153 non-live tests and one fresh-Ubuntu live test, all 20 required case groups, no failures/skips/unmapped tests. Documentation/evidence commits after this source do not change the tested runtime.

## Completed

The missing submission mapping is fixed. A new Ubuntu 22.04 QEMU VM was booted from a checksum-verified image, using an isolated disk and no host directory mounts. The exact source candidate was transferred as a Git bundle. Frozen bootstrap and an offline dependency-cache reinstall passed. AOS-001-TC04 measured the actual server process: 6.447 seconds startup, 76,728 KiB RSS, one loopback listener and no non-loopback connection observed by the smoke check. The real CLI demo completed a goal. The VM database was reset, VM stopped, and temporary SSH key removed.

Actual read-only hwprobe runs are retained for the host and guest. Host: Intel i7-14650HX, 29.1 GiB reported RAM, RTX 4060 Laptop GPU with 8 GiB VRAM. Guest: two virtual CPUs, 1.9 GiB reported RAM, no GPU. Model catalog sizing/speed values remain estimates; no model downloads, model benchmarks, or provider calls ran.

Ruff, Mypy, all ten import-boundary contracts, frozen lock check and tracked-file secret scan passed. Prior review/correction receipts remain historical and are not rewritten.

## Evidence

See `evidence/G0/evaluation.json`, `evidence/R0-completion/`, `docs/reviews/R0-HANDOFF.md` and `docs/reviews/R0-TECHNICAL-COMPLETION.md`. Reports, environment identities, raw bootstrap/demo output, hardware manifests, scripts and hashes are retained. G0 is a technical gate, not the owner-review record in the phase contract.

## Remaining acceptance

No technical G0 case is missing. `R0-OWNER-HANDOFF` still requires the repository owner to review the exact candidate and evidence; approval to execute this validation was not a post-result acceptance signature. R0 status is AWAITING_OWNER_REVIEW. No R1/SOTA work is authorized by this completion run.

## Resume

Review the technical completion and reproduce `make db-up`, `make db-migrate`, and `make r0-demo` as desired. Record accept/reject against `d457242e9e6ee2c54fbd99db99cb35319b1c8783` and its evidence manifest. A later R1 instruction is separate. Preserve the source/evidence distinction on any further commits.
