# R0 technical completion — 2026-10-12

**Technical G0: PASS. Owner handoff acceptance: PENDING.**

Tested source: `d457242e9e6ee2c54fbd99db99cb35319b1c8783`. Branch: `r0-kernel`. The completion commit contains evidence/documents only; it does not alter that runtime candidate.

- 153 host non-live tests passed; one live test was deselected there.
- The separately booted fresh Ubuntu 22.04 VM passed AOS-001-TC04, with actual startup 6.447 s and RSS 76,728 KiB (~74.9 MiB).
- All 20 G0 case groups are represented; no missing/skipped/failed/unmapped test is promoted to PASS.
- The pinned uv/frozen bootstrap and offline reinstall both passed in the VM.
- The real CLI demo completed goal `9eeb028d-dc25-47c0-b9fd-eaa0a3e5829d` with task version 11.
- The original skills ZIP and its hwprobe.py are preserved unchanged, with verified archive integrity and [script/output hashes](../../evidence/R0-completion/hardware-probe-provenance.json). Actual host and VM inventories are retained. Prototype model estimates are not measured speeds or approved model selections.
- Static lint/type/import/lock/secret checks passed. The evaluator rejects missing, skipped, failed, wrong-candidate and mocked-live cases.
- The fresh VM used QEMU TCG, two virtual CPUs and 2 GiB assigned RAM. It had a private new disk, no host filesystem mounts, and a generated temporary SSH key. [Provenance](../../evidence/R0-completion/vm-provenance.json) includes the official Ubuntu image SHA256. It is a real separate guest kernel/boot, not a container or an attestation written for the existing host.
- Disposable VM PostgreSQL was removed, VM stopped and its temporary private key removed. Host test PostgreSQL was also cleaned up.

## Evidence

[Gate](../../evidence/G0/evaluation.json), [live case receipt](../../evidence/R0-completion/case-result-TC04.json), [host suite](../../evidence/R0-completion/non-live.xml), [fresh suite](../../evidence/R0-completion/fresh-host.xml), [fresh environment](../../evidence/R0-completion/environment-manifest.json), [host hardware](../../evidence/R0-completion/host-hardware.json), [guest hardware](../../evidence/R0-completion/guest-hardware.json), [bootstrap log](../../evidence/R0-completion/guest-bootstrap.log), [demo](../../evidence/R0-completion/demo.txt), [SHA256 manifest](../../evidence/R0-completion/CHECKSUMS.sha256).

## Reproduce / review

Use [setup](../SETUP.md). On the current checkout, run `make db-up`, `make db-migrate`, then `make r0-demo`; `make db-down` stops the database without deleting its volume. `make reset-synthetic-data` removes only the synthetic volume. The recorded VM recipe is in `evidence/R0-completion/scripts/`; paths and candidate are deliberately tied to this observed run, not a universal installer. Recorded Python recipes use `.py.txt` to preserve their executed bytes as documentation outside runtime lint discovery.

The phase contract's `R0-OWNER-HANDOFF` calls for owner review of the exact candidate/evidence. Its decision remains pending; no owner identity or signature is fabricated. The prior review findings have correction regressions in the observed suite; these reports establish technical validation, not proof against every possible bug. R1 and the R3 MVP trial remain separate work.
