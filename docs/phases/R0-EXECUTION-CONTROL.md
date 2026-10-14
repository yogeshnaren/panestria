# R0 execution control

This file is phase planning. It is not part of the immutable goal contract and it is not an approval or owner review.

**Contract:** `contracts/phase/r0-phase.contract.json`  
**Contract version:** 1  
**Approval:** recorded in `contracts/phase/r0-phase.approval.json`. That record is not the R0 handoff review.  
**Baseline HEAD inspected:** `48e378ee2f03a98c2e637b1d4f3b6066a5d13eaf` on `main`, clean before this draft.  
**Tested S1 source:** `af6794e112c888fd61b6e6b98a4824acab9c1681`, named by `evidence/AOS-001-S1/case-result.json`.

The contract field `budget.max_wall_seconds` is the per-slice runtime bound of 3600 seconds. It does not mean the phase finishes in one hour. Fourteen slices are planned, each about one developer day, and each gets its own bound.

## Outcome

A local R0 branch contains AOS-001-S2, AOS-001-S3, and AOS-002 through AOS-005, with tests and candidate-bound evidence. The stopping point is a review handoff. R1 does not start.

## Included work

| Order | Slice | Depends on | Cases |
|---|---|---|---|
| 1 | AOS-001-S2 | reviewed S1 baseline | AOS-001-TC02 |
| 2 | AOS-001-S3 | AOS-001-S2 | AOS-001-TC03; TC04 only on a fresh host |
| 3–5 | AOS-002-S1, S2, S3 | completed AOS-001 | AOS-002-TC01–TC04 |
| 6–8 | AOS-003-S1, S2, S3 | completed AOS-002 | AOS-003-TC01–TC04 |
| 9–11 | AOS-004-S1, S2, S3 | completed AOS-003 | AOS-004-TC01–TC04 |
| 12–14 | AOS-005-S1, S2, S3 | AOS-003 and AOS-004 | AOS-005-TC01–TC04 |

AOS-002 depends on the AOS-001 item, so S2 and S3 come before AOS-002.

## Allowed actions after approval

Create local branch `r0-kernel`. Edit the contract’s allowed paths. Install locked project dependencies. Run disposable PostgreSQL through Docker Compose. Run the reviewed commands below. Make small local commits. Do not push, rewrite history, or remove unrelated work.

Development package and image retrieval is separate from the product `cloud_egress: deny` constraint. Approval of this plan allows `uv sync --frozen` and one pinned PostgreSQL image pull. It does not allow application API spending. `max_api_usd` stays `0`.

## Proposed command references

These names are proposals for owner review. They are not registered product commands, and listing them is not a test result.

| command_ref | argv | exit | timeout | output bound |
|---|---|---|---|---|
| `dev.uv-lock-check` | `uv lock --check` | 0 | 120s | 1 MiB |
| `dev.ruff` | `uv run --frozen ruff check .` | 0 | 300s | 2 MiB |
| `dev.mypy` | `uv run --frozen mypy src/panestria` | 0 | 600s | 2 MiB |
| `dev.import-linter` | `uv run --frozen lint-imports --config .importlinter` | 0 | 300s | 1 MiB |
| `dev.pytest-not-live` | `uv run --frozen pytest -m "not live"` | 0 | 3600s | JUnit under `evidence/` |

`dev.pytest-not-live` is the contract acceptance check `R0-HERMETIC-REGRESSION`. AOS-001-TC04 is marker `live` and is outside that command.

## Gates

G0 requires all 20 case IDs in `docs/testing/release-gates.json`. Nineteen can run on disposable PostgreSQL and local processes. AOS-001-TC04 is the live fresh-Ubuntu case. Without that host, TC04 stays `NOT_RUN` and G0 stays `INCOMPLETE`. That is a handoff fact, not a waiver.

Schema validation of the contract is not execution proof. The v0.1.0 skill validator is not the checker for this envelope. R0 acceptance uses `trusted-command-ref`, `git-diff-path-check`, `policy-decision`, and `human-review`. `artifact-exists` is an available R0 verifier but this version has no artifact hash to bind, so it is omitted. `citation-check` and `rubric-review` stay unused until their later runners exist.

## Initial inventory

This list is the inventory from before implementation. It is not the current status.

- No owner approval record for this contract.
- Slice status still says S1 corrections await acceptance. The code, source commit, and evidence were checked; this plan does not invent an acceptance signature.
- Host `psql` is absent. Docker server 29.1.3 is present and is the planned disposable database.
- No fresh Ubuntu virtual machine is available for AOS-001-TC04.
- DBOS is not installed. AOS-003 must verify the current official transaction and enqueue APIs. If same-session enqueue is unavailable, admission pauses and an ADR records the fail-closed result.
- Ruff, Mypy, and Import Linter are not yet project-locked commands.

## Current status

The phase contract is approved. DBOS, Ruff, Mypy, and Import Linter are installed and used. Domain tables, admission, and the synthetic journey are on `r0-kernel`. AOS-001-TC04 passed in a fresh Ubuntu VM on the recorded candidate. G0 is `PASS`; R0 owner acceptance remains pending. See [technical completion](../reviews/R0-TECHNICAL-COMPLETION.md).

## Stopping condition

Stop when the handoff lists ordered commits, the evidence matrix, known issues, setup/start/stop, rollback and backup, and a reproducible synthetic walkthrough with deliberate failures. Stop earlier if a required external setup is missing, after independent R0 work is committed and the gap is listed. Do not open R1.

## Handoff

The review package is [R0-HANDOFF.md](../reviews/R0-HANDOFF.md). G0 is `PASS` with all required cases observed; the separate owner handoff remains pending. This section is not an owner review.

## Technical completion update

G0 now passes on the recorded fresh-VM candidate. Earlier NOT_RUN/INCOMPLETE status text is historical; see [completion](../reviews/R0-TECHNICAL-COMPLETION.md). R0-OWNER-HANDOFF remains pending and R1 has not started.
