# R3 readiness review: supporting material (2026-10-28)

These are the supporting files for [the consolidated review](../R3-READINESS-REVIEW-2026-10-28.md), inspected at `33e61dc`.
The consolidated review holds the final scores, severities and plan inputs. Where it differs from a lens report, the
consolidated review governs. The lens reports are kept unchanged so each reviewer's reasoning and file:line evidence can
be audited.

| File | Contents |
|---|---|
| [process-and-rubric.md](process-and-rubric.md) | The researched review process, the anchored 1-10 rubric, the adversarial checklist per component, and references tagged `[F]` (fetched or searched) or `[K]` (from knowledge) |
| [lens-product-owner.md](lens-product-owner.md) | Requirements fidelity, status truth, the traceability table, the drift register and product gaps |
| [lens-architect.md](lens-architect.md) | System design, the import graph, core-invariant verdicts, the SOTA comparison and structural simplification proposals |
| [lens-qa.md](lens-qa.md) | Test inventory, assertion quality sample, coverage table, CI and gate integrity, tests to add or delete |
| [lens-security.md](lens-security.md) | Red-team findings, attacks that failed, supply chain |
| [lens-ai-research.md](lens-ai-research.md) | Citation verification, calibration recomputation, quota, learning, memory and eval methodology |
| [lens-code-quality.md](lens-code-quality.md) | Complexity, docstring, typing, smell, duplication and dead-code metrics, plus the lean-up candidates |

The lens reports mention proof-of-concept scripts under `<review-scratchpad>/`. Those were disposable review artifacts
and are not retained. Each finding the plan accepts should become a regression test in its task PR rather than a
retained script.
