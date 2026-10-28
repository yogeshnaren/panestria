# 0013: Bounded Delegate workflow for the MVP

Status: proposed (2026-10-28) for owner confirmation in PR review.

## Context

AOS-023 specifies a bounded Delegate planner and workflow. The implementation offers
manual, guided research stages: policy, stage, collect, synthesize and guide. Search
setup is owner-deferred, so D-1 is not yet an end-to-end journey (drift D4, finding F-P2).

## Decision

Implement AOS-023 as one durable workflow (per ADR 0009) on the `panestria-research` queue.

- **Budgets.** Each `DelegateRequest` carries immutable budgets:

  | Budget | Limit |
  |---|---|
  | Sub-queries | at most 5 |
  | Sources | bounded |
  | Bytes | bounded |
  | Deadline | bounded |
  | Paid spend | 0 |

- **Pipeline.** Local-model planner with validated JSON → configured SearXNG
  `SearchProvider` with a query-disclosure log → public fetch → isolated reader →
  claims → semantic verification (the claim-support verifier) → brief.
- **Brief contents.** Summary, claims with SUPPORTED / CONTRADICTED / INSUFFICIENT /
  UNKNOWN labels, snapshot IDs, contradictions, retrieval errors and limitations.
- **Surfaces.** `POST /v1/research`, `GET /v1/research/{id}/evidence` and
  `panestria delegate`. The existing guided stages stay available as expert commands.
- **Isolation.** Disabling research leaves Ask and Build working (AOS-023-TC03).

## Consequences

- AOS-023-TC01..TC03 become hermetic end-to-end tests with fixture sources. TC04 (live
  brief) needs the owner's SearXNG instance.
- Only PUBLIC questions use web search. Private context never enters search queries;
  this is checked by the disclosure log.
