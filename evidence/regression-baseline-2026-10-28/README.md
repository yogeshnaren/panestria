# Regression surface baseline (2026-10-28)

`snapshot.json` was produced by `python tools/compat.py snapshot` on a checkout
whose `src/`, `migrations/` and `docs/` surfaces equal `main` at
`33e61dc0bb254c158bed94f3677701d92d213a1e` (the snapshot's `source_commit`).
It records:
- the OpenAPI hash;
- the CLI command tree;
- the typed denial-code set;
- the schema fingerprint and snapshot hashes;
- the exported contract-schema hashes;
- the package import graph.

It holds no JUnit node set, because `main` CI for that commit reused PR evidence and
retained no lane XML. Per-PR JUnit comparison uses that PR's base run.

This is a comparison baseline for behavior-preserving refactors, not a test
result or a release-gate verdict. `python tools/compat.py check --baseline
evidence/regression-baseline-2026-10-28/snapshot.json` must report zero
undeclared changes. Intended feature changes are listed in
`docs/testing/compat-exceptions.json`.
