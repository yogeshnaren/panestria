# 0015: MVP-X14 deliverables as reuse records with parity evidence

Status: proposed (2026-10-28) for owner confirmation in PR review.

## Context

MVP-X14 requires, for each adopted or borrowed component:
- REA/source investigation decisions;
- pinned evidence covering license and privacy;
- integration parity and rollback;
- representative comparative outcomes.

Only ADR 0005 (build vs adopt) exists. There are no per-component records or parity
evidence (drift D9).

## Decision

Deliver X14 as one reuse record per external component that Panestria pins and depends on:
- DBOS
- OpenTelemetry
- pypdf
- SearXNG
- Ollama with the pinned model
- Claude Code
- Codex CLI
- Playwright
- axe-core

Each record lives in `docs/project/reuse/<component>.md` and is indexed in the
machine-readable `docs/testing/reuse-records.json`. A record contains:
- route (source read via REA, or artifact/runtime analysis);
- pinned identity (version and hash);
- license and usage rights;
- privacy-label inheritance;
- parity test node IDs;
- rollback procedure;
- limits of the investigation.

New hermetic tests in `tests/e2e/test_mvp_x14.py` check that every pin in a record matches
the code constant, and that every parity node exists and passed in the latest gate evidence.

## Consequences

- "Adopt" decisions become auditable and testable. A pin change without a record update
  fails CI.
- Comparative outcome studies stay limited to components where the plan requires an
  EVALUATE verdict.
