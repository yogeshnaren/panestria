# 0012: Local OpenTelemetry trace store instead of Phoenix

Status: proposed (2026-10-28) for owner confirmation in PR review. If accepted, the
AOS-029-TC04 catalog amendment is applied as an additive field.

## Context

AOS-029-TC04 asks for "pinned local Phoenix". The AOS-029 spec text also calls
Phoenix optional. The implementation records bounded, redaction-first local OTel spans
(`telemetry/tracing.py`) and does not run Phoenix. No decision record resolved this
tension, so it was drift D3.

## Decision

- Keep local OpenTelemetry. Spans are stored in a bounded `trace_span` table with the
  existing allow-list redaction, and served read-only through `/v1/traces/{goal}` to a
  Mission Control trace waterfall.
- Do not add Phoenix as a runtime dependency for the MVP.
- Amend TC04 additively. The catalog case gains `amended_by: ADR-0012`; its original
  `expected` text is kept. The amended expectation is "a pinned local trace store and
  viewer with bounded footprint, redaction and export-down truth preservation".
- AOS-029-TC03 still requires that losing trace export never changes canonical state.

## Consequences

- One fewer service to install, pin and secure. Footprint is measured with
  `panestria metrics` on the target host.
- Phoenix stays an R5 candidate, evaluated under ADR 0005's EVALUATE rule.
