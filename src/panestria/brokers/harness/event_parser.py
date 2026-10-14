"""Pinned Claude JSON is untrusted transport; a result never accepts a task."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

CLAUDE_VERSION = "2.1.273"
MAX_FRAME_BYTES = 128 * 1024


class ProtocolRejected(Exception):
    """Only a bounded error code is safe for diagnostics."""


@dataclass(frozen=True)
class NativeEvent:
    kind: str
    content_sha256: str
    reason: str = ""


@dataclass(frozen=True)
class NativeResult:
    status: str
    accepted: bool
    reason: str
    result_sha256: str


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ProtocolRejected("duplicate_field")
        out[key] = value
    return out


def _invalid_constant(value: str) -> None:
    raise ProtocolRejected("invalid_number")


def _text(value: object, *, maximum: int = MAX_FRAME_BYTES) -> str:
    if not isinstance(value, str) or len(value.encode()) > maximum:
        raise ProtocolRejected("invalid_text")
    return value


def _keys(body: dict[str, Any], allowed: set[str]) -> None:
    if set(body) - allowed:
        raise ProtocolRejected("unknown_field")


def _reason(text: str) -> str:
    lowered = text.lower()
    if any(term in lowered for term in ("spend limit", "usage limit", "weekly limit", "quota", "hit your limit")):
        return "quota_unavailable"
    if any(term in lowered for term in ("oauth", "authentication", "not logged in", "unauthorized", "login required")):
        return "auth_required"
    return "native_error"


class ClaudeEventParser:
    def __init__(self, allowed_tools: frozenset[str] = frozenset()) -> None:
        self.allowed_tools = allowed_tools
        self.session: str | None = None
        self.result: NativeResult | None = None
        self._pending = bytearray()
        self._tool_ids: set[str] = set()
        self._frames = 0

    def feed(self, chunk: bytes) -> tuple[NativeEvent, ...]:
        events: list[NativeEvent] = []
        for part in chunk.splitlines(keepends=True):
            self._pending.extend(part)
            if len(self._pending) > MAX_FRAME_BYTES:
                raise ProtocolRejected("frame_limit")
            if part.endswith(b"\n"):
                frame = bytes(self._pending).rstrip(b"\r\n")
                self._pending.clear()
                events.append(self._frame(frame))
        return tuple(events)

    def finish(self, exit_code: int) -> NativeResult:
        if self._pending:
            # A truncated JSON document and a complete frame without a newline
            # are both incomplete stream transport, never candidate success.
            raise ProtocolRejected("truncated_stream")
        if self.result is None:
            raise ProtocolRejected("missing_result")
        if self.result.status == "CANDIDATE" and exit_code != 0:
            raise ProtocolRejected("exit_result_mismatch")
        return self.result

    def _frame(self, raw: bytes) -> NativeEvent:
        if self.result is not None:
            raise ProtocolRejected("event_after_result")
        self._frames += 1
        if self._frames > 4096:
            raise ProtocolRejected("event_limit")
        try:
            body = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_invalid_constant)
        except (UnicodeError, ValueError, RecursionError):
            raise ProtocolRejected("malformed_json") from None
        if not isinstance(body, dict):
            raise ProtocolRejected("invalid_event")
        digest = hashlib.sha256(raw).hexdigest()
        kind = body.get("type")
        if kind == "system":
            _keys(
                body,
                {
                    "type",
                    "subtype",
                    "session_id",
                    "cwd",
                    "tools",
                    "mcp_servers",
                    "model",
                    "permissionMode",
                    "slash_commands",
                    "apiKeySource",
                    "claude_code_version",
                    "output_style",
                    "agents",
                    "skills",
                    "plugins",
                    "uuid",
                    "fast_mode_status",
                },
            )
            if body.get("subtype") != "init" or self.session is not None:
                raise ProtocolRejected("unexpected_system_event")
            session = _text(body.get("session_id"), maximum=128)
            if not session:
                raise ProtocolRejected("invalid_session")
            if body.get("claude_code_version", CLAUDE_VERSION) != CLAUDE_VERSION:
                raise ProtocolRejected("cli_version_mismatch")
            tools = body.get("tools", [])
            if not isinstance(tools, list) or any(not isinstance(tool, str) for tool in tools):
                raise ProtocolRejected("invalid_tools")
            if set(tools) - self.allowed_tools:
                raise ProtocolRejected("unexpected_tool_capability")
            servers = body.get("mcp_servers", [])
            if servers:
                raise ProtocolRejected("unexpected_mcp_server")
            self.session = session
            return NativeEvent("started", digest)
        if kind in {"assistant", "user"}:
            _keys(
                body,
                {"type", "message", "session_id", "parent_tool_use_id", "uuid", "error", "isSynthetic", "isReplay"},
            )
            self._session(body)
            message = body.get("message")
            if (
                not isinstance(message, dict)
                or message.get("role") != kind
                or not isinstance(message.get("content"), list)
            ):
                raise ProtocolRejected("invalid_message")
            for block in message["content"]:
                if not isinstance(block, dict):
                    raise ProtocolRejected("invalid_block")
                self._block(block, kind)
            return NativeEvent("message", digest)
        if kind == "result":
            _keys(
                body,
                {
                    "type",
                    "subtype",
                    "is_error",
                    "result",
                    "session_id",
                    "duration_ms",
                    "duration_api_ms",
                    "num_turns",
                    "total_cost_usd",
                    "usage",
                    "modelUsage",
                    "permission_denials",
                    "uuid",
                    "stop_reason",
                    "errors",
                    "structured_output",
                },
            )
            self._session(body, allow_before_init=True)
            failed = body.get("is_error")
            subtype = body.get("subtype")
            if type(failed) is not bool or subtype not in {
                "success",
                "error_during_execution",
                "error_max_turns",
                "error_max_budget_usd",
                "error_max_structured_output_retries",
            }:
                raise ProtocolRejected("unknown_result_state")
            if body.get("permission_denials"):
                raise ProtocolRejected("privilege_request_denied")
            text = _text(body.get("result", ""))
            if not failed and subtype == "success":
                if self.session is None or self._tool_ids:
                    raise ProtocolRejected("incomplete_execution")
                status, reason = "CANDIDATE", "independent_checks_required"
            else:
                errors = body.get("errors", [])
                if not isinstance(errors, list) or any(not isinstance(error, str) for error in errors):
                    raise ProtocolRejected("invalid_errors")
                reason = _reason(text + " ".join(errors))
                if subtype == "error_max_budget_usd":
                    reason = "budget_exhausted"
                elif subtype == "error_max_turns":
                    reason = "turns_exhausted"
                status = "UNAVAILABLE" if reason in {"quota_unavailable", "auth_required"} else "FAILED"
            self.result = NativeResult(status, False, reason, hashlib.sha256(text.encode()).hexdigest())
            return NativeEvent("candidate" if status == "CANDIDATE" else "unavailable", digest, reason)
        raise ProtocolRejected("unknown_event_type")

    def _session(self, body: dict[str, Any], *, allow_before_init: bool = False) -> None:
        session = body.get("session_id", self.session)
        if self.session is None and not allow_before_init:
            raise ProtocolRejected("missing_init")
        if self.session is not None and session != self.session:
            raise ProtocolRejected("session_mismatch")

    def _block(self, block: dict[str, Any], role: str) -> None:
        kind = block.get("type")
        if kind == "text":
            _keys(block, {"type", "text", "citations"})
            _text(block.get("text"))
        elif kind == "thinking" and role == "assistant":
            _keys(block, {"type", "thinking", "signature"})
            _text(block.get("thinking"))
        elif kind == "tool_use" and role == "assistant":
            _keys(block, {"type", "id", "name", "input"})
            tool_id = _text(block.get("id"), maximum=128)
            if block.get("name") not in self.allowed_tools or not isinstance(block.get("input"), dict):
                raise ProtocolRejected("unapproved_tool")
            if not tool_id or tool_id in self._tool_ids:
                raise ProtocolRejected("duplicate_tool")
            self._tool_ids.add(tool_id)
        elif kind == "tool_result" and role == "user":
            _keys(block, {"type", "tool_use_id", "content", "is_error"})
            tool_id = _text(block.get("tool_use_id"), maximum=128)
            if tool_id not in self._tool_ids:
                raise ProtocolRejected("unmatched_tool_result")
            self._tool_ids.remove(tool_id)
        else:
            raise ProtocolRejected("unknown_content_type")
