# 0010: Run native vendor CLIs inside an OS sandbox with SNI-checked egress

Status: accepted owner decision (2026-10-28). Implementation pending; no code changes in this record.

## Context

The native Claude CLI runs on the host as the owner uid
(`brokers/harness/process_runner.py`: "lifecycle control, not an OS security boundary").
Its containment rests on four things:
- CLI flags (`--tools ""`, `--setting-sources ""`, `--strict-mcp-config`, `disableAllHooks`);
- a binary hash pin;
- a private config directory;
- post-hoc stream parsing.

Only the scoped-bash MCP tool runs in Docker. The egress gateway
(`sandbox/egress.py`) tunnels CONNECT to allowed hosts without checking that the TLS
server name matches (review SEC-M2). The container relay `sandbox/native_proxy_relay.py`
exists but no production code calls it.

## Decision

1. **`native-cli` sandbox profile.** Each native CLI (Claude, and Codex per ADR 0008)
   runs in a pinned container:
   - `--network none`, read-only root filesystem, all capabilities dropped,
     `no-new-privileges`, pids/memory/CPU limits;
   - a tmpfs `HOME`, and the owner's non-root uid:gid;
   - mounts limited to:
     - a read-only, content-addressed copy of the hash-verified binary (the hash is
       checked on the copy, closing the check-then-use window);
     - the relay;
     - the gateway socket directory;
     - the dedicated vendor config directory, read-write because sign-in refresh needs it;
     - the disposable task workspace;
     - the MCP socket directory.
2. **Network path.** `HTTPS_PROXY` points at the in-container relay, which reaches the
   host egress gateway over a pinned Unix socket.
3. **SNI enforcement at the gateway.** After `200 Connection Established`, the gateway
   reads a bounded TLS ClientHello and checks:
   - an SNI is present;
   - the SNI, casefolded, equals the CONNECT host;
   - Encrypted ClientHello (ECH) is denied.

   Allow-lists are per vendor, configuration-driven and bound into the sandbox
   manifest digest. Each connection is recorded in an egress-observation table that
   feeds the exposure view.
4. **Peer and process hardening.**
   - MCP peer verification adds container pid ancestry to the uid check.
   - Process receipts record the terminating signal, the last frame kind and
     OOMKilled. These diagnose the open "intermittent native-worker stop".

## Consequences

- Hostile `.claude/settings.json` hooks, `.mcp.json`, `CLAUDE.md`, home-directory
  secrets, raw sockets and mismatched-SNI tunnels all have OS-boundary tests using a
  hash-pinned stub CLI.
- Residual risks:
  - The vendor config directory is writable by the CLI.
  - Traffic to an allowed vendor host could carry data under the vendor account. The
    privacy and export rules in ADR 0011 bound what reaches the workspace.
- Supersedes the "accepted residual risk" alternative. The owner chose the sandbox.
