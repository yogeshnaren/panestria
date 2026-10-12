# ADR 0002: Global event sequence and effect digest

Status: recorded for the current R0 implementation. This record does not accept R0.

## Context

Design documents require one global event cursor and one approval fingerprint. Bare PostgreSQL identity allocation does not order commits. An approval must name the owner, project, and exact action that may run.

## Decision

- `panestria.task_event.seq` is `bigint GENERATED ALWAYS AS IDENTITY (CACHE 1)` and `UNIQUE`. Application code does not reset or override it. A rolled-back transaction may leave a gap.
- Both append functions take `pg_advisory_xact_lock(106971, 1)` before the insert and hold that lock until the transaction ends. The functions are `append_event` and `append_domain_event`. Callers do not write another domain row after the append in the same transaction.
- Event replay reads that sequence. JSON carries `seq` as a decimal string.
- The only approval fingerprint is `effect_digest`. It is the SHA-256 of the canonical JSON for `ActionPreview`, including `owner_id`, `project_id`, `task_id`, `action_kind`, contract hash and version, policy version, destination, expected base, candidate hash, required checks, minimum actor, and expiry.
- `approval_request` stores that digest and references the goal together with its owner and project. A stored preview whose recomputed digest differs is `digest_mismatch`. Consumption does not replace the dispatch-time checks.

## Consequences

Two transactions cannot commit events in an order that disagrees with `seq` while both hold this lock. A different owner, project, candidate, or check set is a different digest. This ADR does not add a migration diagram, and it does not record a fresh-host result.
