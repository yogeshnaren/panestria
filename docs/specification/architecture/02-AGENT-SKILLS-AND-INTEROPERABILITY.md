# Agent Skills, Protocol Integration and Asset Reconciliation

## Design decision
Adopt the **portable Agent Skills `SKILL.md` convention** for reusable procedural capabilities, with a separate AgentOS-owned `capability.yaml` or equivalent permission manifest. SKILL.md instructions are **not trusted policy** and cannot grant filesystem/network authority.

The original seven-skill archive is attached unchanged with supplied checksums, a full file inventory and observed synthetic smoke results; see [asset inspection](../attachments/SKILLS-INVENTORY.md). Status is source-attached and smoke-tested, not installed or production-integrated. First planning inventories actual assets, resolves format/license/permission gaps and adapts relevant code.

## Skill adoption workflow
1. Inventory exact skill directories, SKILL.md frontmatter, scripts, references, assets, licenses and dependencies. Record hashes.
2. Validate SKILL.md syntax with a pinned validator; check metadata, clear invocation and no undocumented execution.
3. Scan dependencies and scripts; classify which permissions the capability really needs.
4. Create a separate `capability.yaml` with `capability_id`, `skill_ref_sha`, `input_schema`, `output_schema`, `required_tools`, `filesystem_scopes`, `network_allowlist`, `allowed_privacy_classes`, `max_runtime`, `secret_scopes`, `trust_profile_requirement`.
5. Test in `SYNTHETIC_DEV` sandbox and assert output schema, prohibited-network denial and no secret access.
6. Bind registry entry to approved version/hash. Load description on demand; provide full instructions only for a scoped task after authorization.
7. On upgrade, re-run security fixtures and emit versioned approval/rollback evidence.

| Reported asset | Backlog mapping | Required reconciliation |
|---|---|---|
| `hardware-probe` / `hwprobe.py` | AOS-015 | inspect code and five simulated profiles; benchmark actual machine |
| `claude-code-worker` | AOS-010 | verify safe/restricted settings, auth and malicious repo hook fixture |
| `verified-research-brief` | AOS-021 | add content hash + retained text offsets + unsupported claim rejection |
| `egress-preflight` | AOS-008/012/029 | distinguish authorized/accessible/observed; manifest never replaces network guard |
| `milestone-handoff` | AOS-025/027a/027b | structured checkpoint IDs, clean git commit and verifier evidence |
| `capture-learning` | AOS-011/012/036 | five memory-use stages and provenance/consent |
| `goal-contract` | AOS-002/025 | structured machine-run verifiers, not prose-only acceptance |

**Spelling in shipping schema:** `accessible` (not `accesssible`).

## Interfaces and protocol positioning
- **Internal WorkerAdapter**: stable kernel contract. Worker-specific extensions do not change task policy.
- **MCP server (post-R1)**: exposes scoped platform tools to Hermes, other assistants, or an IDE. MVP tools: `submit_goal`, `get_goal_status`, `list_tasks`, `get_artifact`, later `request_approval` with user sign-in; no `approve_anything` tool.
- **MCP client (staged)**: consumes reviewed external tool servers with per-tool capabilities/approvals and source isolation.
- **ACP**: optional harness broker adapter for compatible coding agents; verify precise version/agent behavior before claiming conformance.
- **A2A**: future integration for full autonomous agent platforms; never bypass kernel policy on inbound agent messages.

## MCP security rules
- Treat all tool input and output as untrusted; server validates schemas, per-request auth, rate limits and output sanitization.
- A local stdio connection does not equal trusted user authorization; bind calls to a delegated owner/project/capability scope.
- HTTP transport requires current MCP authorization standard for negotiated protocol version; do not invent bearer forwarding/implicit token trust.
- Every mutation uses kernel API and project trust + data privacy + action autonomy check. An MCP client cannot promote its own policy.
- Hermes only becomes an alternative front-end after the kernel status/approval API is stable; do not fork Hermes to become kernel.

## Acceptance
- Every installed Skill validates, has a hashed approved version, and cannot gain privileges by modifying SKILL.md text.
- A malicious SKILL.md/tool description requesting data exfil does not cause a denied outbound call to execute.
- MCP client attempting to submit RESTRICTED data to cloud is rejected and audited; no unapproved actor can consume an approval token.
- Tool registry returns only installed approved capabilities matching a task's trust/privacy/action context.

## References
- Agent Skills: https://agentskills.io/specification
- MCP protocol spec 2026-07-28: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/basic/index.mdx
- MCP tools spec: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/server/tools.mdx
- Hermes Agent: https://github.com/NousResearch/hermes-agent
