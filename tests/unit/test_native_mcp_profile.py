"""Closed native MCP profile metadata and actual child handle scrubbing."""

import json
import os
import subprocess
import sys

import pytest

from panestria.brokers.harness.claude_check import TOOL, ClaudeRegisteredCheckAdapter
from panestria.brokers.harness.claude_proposal import ProposalUnavailable
from panestria.brokers.harness.command_protocol import RegisteredCheckSession
from panestria.brokers.harness.event_parser import ClaudeEventParser, ProtocolRejected
from panestria.contracts.native_command import RegisteredCheckReceipt


def init(**changes):
    body = {
        "type": "system",
        "subtype": "init",
        "session_id": "synthetic",
        "claude_code_version": "2.1.273",
        "tools": [TOOL],
        "mcp_servers": [{"name": "panestria", "status": "connected"}],
        "model": "claude-haiku-4-5-20251001",
        "permissionMode": "default",
        "apiKeySource": "none",
        "skills": [],
        "plugins": [],
        "slash_commands": [],
        "agents": ["claude", "Explore", "general-purpose", "Plan", "statusline-setup"],
    }
    body.update(changes)
    return json.dumps(body).encode() + b"\n"


def parser():
    return ClaudeEventParser(frozenset({TOOL}), allowed_mcp_servers=frozenset({"panestria"}))


def test_one_connected_server_exact_tool_and_inert_pinned_agent_inventory():
    assert parser().feed(init())[0].kind == "started"
    with pytest.raises(ProtocolRejected, match="unexpected_tool_capability"):
        ClaudeEventParser().feed(init())


@pytest.mark.parametrize(
    "servers",
    [
        None,
        {},
        "panestria",
        [],
        [{"name": "other", "status": "connected"}],
        [{"name": "panestria", "status": "failed"}],
        [{"name": "panestria", "status": "pending"}],
        [{"name": "panestria", "status": "connected", "url": "https://example.test"}],
        [{"name": [], "status": "connected"}],
        [{"name": "panestria", "status": "connected"}] * 2,
    ],
)
def test_unexpected_failed_duplicate_or_malformed_server_metadata_refused(servers):
    with pytest.raises(ProtocolRejected, match="unexpected_mcp_server"):
        parser().feed(init(mcp_servers=servers))


@pytest.mark.parametrize(
    "changes",
    [
        {"tools": []},
        {"tools": [TOOL, TOOL]},
        {"permissionMode": "bypassPermissions"},
        {"skills": ["hostile"]},
        {"plugins": ["hostile"]},
        {"slash_commands": ["hostile"]},
        {"apiKeySource": "api_key"},
        {"model": "claude-opus-5"},
        {"agents": ["hostile"]},
    ],
)
def test_profile_cannot_widen_background_auth_tools_model_or_permissions(changes):
    with pytest.raises(ProtocolRejected, match="unexpected_mcp_profile_metadata"):
        parser().feed(init(**changes))


@pytest.mark.parametrize("tool", ["Bash", "Read", "Agent", "mcp__untrusted__run"])
def test_non_allowlisted_tool_never_becomes_available(tool):
    with pytest.raises(ProtocolRejected, match="unexpected_tool_capability"):
        parser().feed(init(tools=[TOOL, tool]))


def test_bounded_client_display_metadata_has_no_protocol_or_authority_effect():
    state = RegisteredCheckSession(
        ("public-synthetic-check",), "snapshot:" + "ab" * 32, lambda *_: RegisteredCheckReceipt(outcome="DENIED")
    )

    serial = iter(range(10))

    def initialize(info):
        return state.handle(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": next(serial),
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {"roots": {"listChanged": True}, "elicitation": {}},
                        "clientInfo": info,
                    },
                }
            ).encode()
        )

    info = {
        "name": "claude-code",
        "version": "2.1.273",
        "title": "Claude Code",
        "description": "Bounded display only",
        "websiteUrl": "https://claude.com/claude-code",
    }
    for change in [
        {"description": "x" * 257},
        {"websiteUrl": []},
        {"description": "line\ncontrol"},
        {"owner_id": "forged"},
    ]:
        assert json.loads(initialize({**info, **change}))["error"]["code"] == -32602
    result = json.loads(initialize(info))["result"]
    assert result["protocolVersion"] == "2025-06-18" and set(result["capabilities"]) == {"tools"}


@pytest.mark.parametrize(
    "commands,candidate",
    [(("private-check",), "snapshot:" + "ab" * 32), (("public-synthetic-check",), "candidate:other")],
)
def test_public_profile_refuses_non_fixture_references_before_inspection(commands, candidate):
    state = RegisteredCheckSession(commands, candidate, lambda *_: RegisteredCheckReceipt(outcome="DENIED"))
    with pytest.raises(ProposalUnavailable, match="invalid_public_check_profile"):
        ClaudeRegisteredCheckAdapter(None).check(state, candidate_ref="snapshot:" + "ab" * 32)


def test_actual_shim_main_discards_environment_and_inherited_private_handle(tmp_path):
    path = tmp_path / "synthetic-config"
    path.write_text("synthetic only")
    fd = os.open(path, os.O_RDONLY)
    try:
        script = """import os,sys,json
from panestria.brokers.harness.command_stdio import main
fd=int(sys.argv[1]); original=os.fstat(fd)
os.environ['PANESTRIA_DATABASE_URL']='synthetic-only'
sys.argv=['shim','--help']
try:main()
except SystemExit:
 try:
  current=os.fstat(fd); leaked=(current.st_dev,current.st_ino)==(original.st_dev,original.st_ino)
 except OSError:leaked=False
 print(json.dumps({'handle_leaked':leaked,'env_leaked':'PANESTRIA_DATABASE_URL' in os.environ}))
"""
        child = subprocess.run(
            [sys.executable, "-c", script, str(fd)],
            pass_fds=(fd,),
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
        )
        assert json.loads(child.stdout.splitlines()[-1]) == {"handle_leaked": False, "env_leaked": False}
        assert child.stderr == ""
    finally:
        os.close(fd)
