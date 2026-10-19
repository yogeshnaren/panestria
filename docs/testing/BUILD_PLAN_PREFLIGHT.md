# Check a Build task plan before scheduling

This is a developer preflight for AOS-025-S1. It checks a proposed task dependency
graph against a goal contract and inventory. It does **not** generate code, call a
model, inspect a real repository, certify workers, submit tasks or grant actions.
Use the existing [owner Build CLI](OWNER_BUILD_CLI.md) for the delivered one-worker
path. Two-worker execution is still under implementation.

Prepare three new owner-only `0600` files in a private directory:

- Your valid existing goal contract, including required checks, allowed paths,
  permitted capabilities and explicit budgets.
- An inventory following `ProjectInventory` in `src/panestria/contracts/plan.py`:
  owner/project, base commit, project snapshot SHA256, worker refs with pinned
  binary/profile SHA256, capability refs and maximum parallel count (1–2).
- A `PlanProposal`: exact IDs, contract SHA256, **complete inventory envelope**
  SHA256, privacy class and task nodes. Each node names task UUID/dependencies,
  worker, permitted capabilities, literal file paths, existing acceptance keys,
  expected artifact names, attempts and per-attempt time/API-cash microunits.

The illustrative fixture and parser calls in `tests/contract/test_build_plan.py`
show a three-task graph: two independent changes followed by a join. They use
synthetic inventory digests; never treat those values as live certification.
For canonical hashes, call the typed inventory's `sha256()` and existing
`contract_sha256()` after parsing the files; do not hash pretty-printed JSON.

```bash
uv run --frozen panestria plan validate <owner-UUID> <project-UUID> \
  --contract /absolute/private/contract.json \
  --inventory /absolute/private/inventory.json \
  --proposal /absolute/private/proposal.json
```

Expect deterministic task layers and conservative aggregate envelope totals with
`authority: PROPOSAL_ONLY`. A rejected proposal exits1 with a fixed safe reason.
No database or server is needed for this preflight. A pass is not an admission:
current policy, actual certified worker inventory, leases, quotas, resources,
conflict handling and final integrated verification are separate required work.
Do not put real private inputs, credentials or model data into Git.
