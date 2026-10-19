# Credits and inspiration

Panestria builds on ideas and tools from other open-source projects. This page
credits them. It is updated whenever a borrowed idea lands in the code. The
reasoning for each is in [ADR 0005](../adr/0005-build-vs-adopt.md).

**Status of code reuse:** as of this page, no source code from any project below
has been copied into this repository. Ideas are re-implemented independently. If
code is ever copied, its license text goes under `third_party/` and an entry in a
`NOTICE` file in the same pull request, and its row below changes to "code reused".

| Project | Author / steward | License | What Panestria takes | Status |
|---|---|---|---|---|
| [Firstmate](https://github.com/kunchenguid/firstmate) | Kun Chen (kunchenguid) | MIT | Supervision patterns: a zero-token watcher that wakes the supervisor only on actionable events; busy/idle/unknown/dead worker classification from harness lifecycle signals; `ship` versus `scout` task types; merge bound to the live head; teardown that refuses dirty or unlanded worktrees; pooled worktrees; recording the owner's away-mode words verbatim with only mechanical limits enforced by code. | Idea only; planned for R3. |
| [Sandcastle](https://github.com/mattpocock/sandcastle) | Matt Pocock | MIT | Branch strategies for sandboxed agents; parallel-planner and parallel-planner-with-review orchestration; warm sandbox reuse. | Idea only; planned for R3. |
| [Hermes Agent](https://github.com/NousResearch/hermes-agent) | Nous Research | MIT | Messaging, voice and scheduling front end as an untrusted client of the scoped API; ideas for memory nudges, FTS5 session recall and agent-created skills. | Planned client (R5) and ideas (R5–R6). |
| [Agent Skills](https://agentskills.io/specification) | Agent Skills project | open specification | `SKILL.md` skill packaging, progressive disclosure and the `skills-ref` validator. | Planned adoption (R6). |
| [GEPA](https://github.com/gepa-ai/gepa) | Agrawal et al. (GEPA authors) | MIT | Reflective, Pareto-aware prompt and configuration optimization from retained traces. | Planned dependency (R6). |
| [Meta-Harness](https://github.com/stanford-iris-lab/meta-harness) | Lee et al., Stanford and collaborators | MIT | Code-level harness search over a filesystem of prior candidates, scores and traces. | Under evaluation (R6). |
| [Harness²](https://github.com/google-research/harness2) | Google Research | Apache-2.0 | Propose–Probe–Compose probing and an evidence-backed lesson library. Not an officially supported Google product. | Under evaluation; ideas planned (R6). |
| [Managed Agents architecture](https://www.anthropic.com/engineering/managed-agents) | Anthropic | n/a | Brain/hands/session separation, lazy sandbox provisioning, credentials kept out of sandboxes, no irreversible context pruning. | Design validation. |

Considered and not adopted as a base: [OpenClaw](https://github.com/openclaw/openclaw)
(MIT) is deferred as an optional client. Evo 2 was judged out of scope for the
platform.
