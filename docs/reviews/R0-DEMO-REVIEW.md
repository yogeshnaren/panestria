> R0 owner acceptance was recorded on 2026-10-13 in [the acceptance record](../../contracts/phase/r0-phase.acceptance.json). Earlier pending-status text below is preserved as the technical handoff history.

# R0 demo repair and current validation — 2026-10-12

**Demo fixed and running. Technical G0: PASS. Owner acceptance: PENDING.**

Current source candidate: `f161193ed31918592015ec9e68163d31d77cb0ae`. The later evidence commit contains no runtime change. The prior [completion report](R0-TECHNICAL-COMPLETION.md) and its evidence remain historical records for `d457242`.

## What changed

`make dev-api` held port 8765 while `make r0-demo` attempted a second bind. The demo now verifies Panestria health and bearer authentication before reusing the listener. It starts an API only when the port is free and stops only that child, including its failure path. An unknown listener or wrong token fails before submission. Settings are validated before contacting a listener. The original running user API was left running.

`make r0-review` runs the same synthetic CLI walkthrough, then serves a read-only snapshot at **http://127.0.0.1:8870/**. This agent started that page separately and verified it in the browser. It displays the completed goal, recorded verification tied to the candidate hash, approvals and event history. It exposes no API proxy, mutation routes, bearer token or filesystem browsing. API Origin denials remain unchanged. The snapshot records automatic synthetic CLI decisions, not the owner's R0 acceptance.

## Observed verification

- All 160 non-live tests passed natively on the host against a disposable synthetic database; the original review database was backed up and restored with identical table fingerprints. The live fresh-host case also passed: 161 tests across all 20 required G0 case groups.
- Fresh frozen bootstrap and offline reinstall passed on the exact candidate. The actual live smoke measured 6.192 seconds startup and 77184 KiB RSS; it was not mocked or copied from the existing host.
- The real CLI demo completed in the VM, and on the host with both an already-running API and a separately started/stopped API. Receipts record the two ownership modes explicitly.
- New regressions cover authenticated listener reuse, refusal of wrong tokens and stalled listeners, HTML escaping, read-only route handling, Host/Origin checks, review-port limits and candidate/hash mismatch remaining UNKNOWN. Ruff, Mypy, import boundaries, frozen lock and secret scanning passed through the suite.
- The host API was temporarily suspended during native regression, then resumed after all review database tables were restored and verified against their saved fingerprints. The browser snapshot stayed available. The original data and API process were preserved. The VM was stopped and its temporary SSH private key removed.


The initial emulated-VM full-suite attempt is retained in `initial-docker-permissions.xml`/`.log`: its original SSH session lacked the newly added Docker group, and its short interpreter/worker-startup timing assumptions also failed under TCG emulation. The full native rerun retained the original deadlines and passed; no test assertion or runtime budget was weakened. The fresh live case ran in a corrected guest login. These historical failures are not labeled PASS or merged into the passing receipts. The first guest demo invocation also correctly rejected a leftover test-only environment variable; its failure log is retained, and the clean application invocation completed.

## Review and reproduce

The currently running [browser review](http://127.0.0.1:8870/) is a snapshot of host goal `f96c9877-7ae3-41c8-99fb-80618c9e36a6`. Its API reused the user's existing process; its API code was not restarted by the demo. The separate VM verifies the fresh bootstrap, live startup and CLI demo on the current source.

From [setup](../SETUP.md), `make db-up` and `make db-migrate` prepare the synthetic database. `make r0-demo` prints a completed result and exits; `make r0-review` stays running until Ctrl+C. `make dev-api` is optional and may remain running in another terminal. If a review page already owns port 8870, stop that page before starting another, or select `--review-port` for a direct module invocation.

[Gate](../../evidence/G0/evaluation.json), [full suite](../../evidence/R0-demo-fix/non-live.xml), [fresh case](../../evidence/R0-demo-fix/fresh-host.xml), [environment](../../evidence/R0-demo-fix/environment-manifest.json), [reused API receipt](../../evidence/R0-demo-fix/reused-api-demo.json), [owned API receipt](../../evidence/R0-demo-fix/owned-api-demo.json), [VM provenance](../../evidence/R0-demo-fix/vm-provenance.json), [checksums](../../evidence/R0-demo-fix/CHECKSUMS.sha256).

The original hardware probe ZIP and prior real host inventory remain preserved. This repair performs no model benchmark or provider call. Owner review of this exact candidate/evidence remains pending under `R0-OWNER-HANDOFF`. R1 has not started.
