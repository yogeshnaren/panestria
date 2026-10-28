# 0008: Second Build vendor through a pinned Codex CLI adapter

Status: accepted owner decision (2026-10-28). Implementation pending; no code changes in this record.

## Context

AOS-024 requires a second approved vendor harness under exactly the same worker
contract, and checklist B-1 requires "both pinned vendor adapters". Today two-worker
Build means two Claude workers (`execution/native_plan.py`). No code or decision
record covered the second vendor, so this was silent drift D1 in the 2026-10-28 review.

## Decision

Implement an OpenAI Codex CLI adapter as the second vendor. It uses the same worker
contract as Claude:
- a pinned and hash-verified binary;
- a dedicated config directory;
- the OS sandbox and SNI-restricted egress from ADR 0010;
- digest-bound approval and protected merge;
- no automatic resume after an uncertain launch.

Work order:
1. A vendor-neutral `WorkerAdapter` contract (`NormalizedEvent`, `NativeResult`,
   `supports_resume=False`), so kernel and API models carry no vendor-specific fields.
2. An REA source investigation of a pinned `openai/codex` release. It records the
   license, the `exec --json` event schema, sandbox and config isolation, MCP behaviour,
   authentication, contacted hosts, and the account terms for background use.
3. `brokers/harness/codex/`: profile, parser and adapter. It is seeded from
   `docs/fixtures/codex-synthetic.jsonl` and sanitised real recordings.

Additive contract values: `PrivacyDestination` gains `openai-subscription`, and the
quota ledger gains a provider lane for it. Existing values stay valid.

When only one vendor is qualified, a two-worker plan returns WAIT
(`second_vendor_unqualified`). Two Claude workers run only with explicit owner opt-in.
There is no silent substitution.

## Consequences

- AOS-024-TC01..TC03 become hermetic and OS-boundary tests. TC04 and the two-vendor
  live cases (AOS-026-TC04, AOS-027b-TC04, AOS-030-TC03) need the owner's Codex
  sign-in and consent to its terms.
- Native runtime qualification hashes `src/`, so both vendors are re-qualified once,
  on the frozen candidate.
- Residual risk: vendor CLIs change quickly. The pin plus the parser's rejection of
  unknown frames turns drift into a visible ProtocolRejected, not a misread result.
