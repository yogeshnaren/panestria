# Upstream sources checked for this detailed design

Checked 2026-10-11. These references support interface choices; they do not establish installed-runtime conformance. Keep exact version/behavior evidence in implementing compatibility manifests.

- [DBOS datasource transactions](https://docs.dbos.dev/python/tutorials/transaction-tutorial): tracked database outcomes commit with callback writes; the datasource session is the transaction boundary. This supports the atomic state/event design. Outside a workflow a normal transaction still needs request deduplication.
- [DBOS client](https://docs.dbos.dev/python/reference/client): atomic enqueue participates in a caller-owned transaction against the system database; pin/test the chosen client API.
- [PostgreSQL sequences](https://www.postgresql.org/docs/current/functions-sequence.html): allocation is not rollback-safe/contiguous. The global cursor design adds serialized commit ordering rather than assuming sequence values are commit timestamps.
- [Claude CLI](https://code.claude.com/docs/en/cli-reference): customization/tool/permission controls and prompt-file interfaces are version-specific. Managed policy exceptions and combined auth behavior require testing.
- [Codex non-interactive execution](https://learn.chatgpt.com/docs/non-interactive-mode): exec/JSONL is the supported process integration route; saved authentication and structured output do not grant kernel authorization.
- [Codex command reference](https://learn.chatgpt.com/docs/developer-commands?surface=cli): login status and permission/sandbox profiles are documented. Probe their effective read/write/config/network restrictions on the actual binary; never infer arbitrary host secrecy from a mode name.
- [Docker resource constraints](https://docs.docker.com/engine/containers/resource_constraints/): container resource limits must be configured explicitly; this plan requires measured effective caps.
- [SearXNG search API](https://docs.searxng.org/dev/search_api.html): instance configuration controls permitted formats; JSON/setup/rate behavior is a compatibility check, not assumed availability.
- [Cursor rules](https://cursor.com/docs/rules): project rules are .mdc files under .cursor/rules; the supplied rule template is optional persistent coding guidance. It is not an OS or policy guard.
- [uv project layout](https://docs.astral.sh/uv/concepts/projects/layout/): one project metadata/lockfile and installed src package; use frozen dependency checks when implementing.

The source-order workflow for Codex guidance used the OpenAI Docs skill. This package contains no copied full external documentation pages.
