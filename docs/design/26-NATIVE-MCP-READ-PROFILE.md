# Pinned native registered-read profile

Prerequisite: #75 durable read-check authority, #74 private transport and #73
protocol. Preserve the existing no-tools safe-mode proposal profile unchanged.
This task creates a separate explicit synthetic PUBLIC read-check conformance
profile. Never enable general shell/file tools, native subagents, external MCP,
provider fallback, API-key auth, extra usage spending or arbitrary owner prompts.

The CLI is the existing hash/version-pinned Claude Code subscription binary and
dedicated private authentication directory. Authentication remains owned by that
CLI; do not read/copy credentials. Launch only from a fresh controlled attempt
folder containing synthetic hostile project fixtures. Refuse managed policy,
pin all explicit settings/MCP/prompt files, and bound process pipes and deadline.
Only the private controller socket's refs and metadata can reach the agent. The
shim must discard inherited private environment/descriptors before connecting.

Official CLI documentation says safe mode disables MCP, while restricted mode
ignores user/project settings, removes code-running builtins unless explicitly
requested and retains managed policy. Therefore validate a separate explicit
restricted/settings/strict-MCP combination against the pinned artifact and
actual observed behavior. Do not claim that reusing safe-mode flags proves MCP
works. Bare mode is excluded because it skips subscription OAuth credentials;
do not supply a replacement API key. Disable hooks, autodiscovered agents/skills/plugins/memory/connectors;
allow only the exact internal MCP tool and any unavoidable inert terminal tool.
Every additional event/tool/server or permission escalation fails closed.

First test native metadata/server discovery without inference. Then use one small
synthetic PUBLIC subscription request asking for the one reviewed check. Retain
its report/hash, exact allowed server/tool stream, actual PostgreSQL/Docker claim,
no hidden repository hook/MCP execution and no replay. Only metadata receipt is
returned; raw candidate/check output and credentials do not enter the prompt.
Actual cash remains unknown for subscription estimates; no paid SDK call or
fallback is authorized by this profile. A component pass is not the full native
shell tier, G1 or R3 acceptance.

Primary references: [CLI controls](https://code.claude.com/docs/en/cli-reference),
[MCP configuration](https://code.claude.com/docs/en/mcp) and
[settings](https://code.claude.com/docs/en/settings).
