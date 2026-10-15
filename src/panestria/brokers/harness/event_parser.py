"""Pinned Claude JSON is untrusted transport; a result never accepts a task."""

from __future__ import annotations

import hashlib
import json
import math
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


def _result_metadata(body: dict[str, Any], *, failed: bool) -> None:
    for field in ("first_content_frame_ms", "time_to_request_ms", "ttft_ms", "ttft_stream_ms"):
        if field in body and (type(body[field]) is not int or not 0 <= body[field] <= 900_000):
            raise ProtocolRejected("invalid_result_metadata")
    for field in ("queued_turn_count", "result_index"):
        if field in body and (type(body[field]) is not int or body[field] != 0):
            raise ProtocolRejected("unexpected_native_background_work")
    if body.get("fast_mode_state", "off") != "off" or body.get("fast_mode_disabled_reason") not in (
        None,
        "sdk_opt_in_required",
    ):
        raise ProtocolRejected("unexpected_fast_mode")
    if "terminal_reason" in body:
        terminal = _text(body["terminal_reason"], maximum=128)
        if not failed and terminal != "completed":
            raise ProtocolRejected("incomplete_execution")
    status = body.get("api_error_status")
    if status is not None and (not failed or type(status) is not int or not 400 <= status <= 599):
        raise ProtocolRejected("invalid_result_metadata")
    if "subagent_stats" in body:
        stats = body["subagent_stats"]
        counters = {"spawned", "started_in_background", "max_depth", "spawned_by_subagents", "completed", "failed"}
        maps = {
            "requested": {"background", "foreground", "unset"},
            "killed": {"parent", "user", "system"},
            "refused": {"depth_limit", "concurrency_limit", "budget"},
            "by_type": set(),
        }
        if (
            not isinstance(stats, dict)
            or set(stats) != counters | maps.keys()
            or any(type(stats[key]) is not int or stats[key] != 0 for key in counters)
            or any(
                type(stats[key]) is not dict
                or set(stats[key]) != fields
                or any(type(value) is not int or value != 0 for value in stats[key].values())
                for key, fields in maps.items()
            )
        ):
            raise ProtocolRejected("unexpected_native_subagents")


class ClaudeEventParser:
    def __init__(
        self,
        allowed_tools: frozenset[str] = frozenset(),
        *,
        capture_candidate: bool = False,
        allowed_mcp_servers: frozenset[str] = frozenset(),
    ) -> None:
        self.allowed_tools = allowed_tools
        self.allowed_mcp_servers = allowed_mcp_servers
        self.session: str | None = None
        self.result: NativeResult | None = None
        self._pending = bytearray()
        self._tool_ids: set[str] = set()
        self._frames = 0
        self._capture_candidate = capture_candidate
        self.candidate_text: str | None = None

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
        if kind == "system" and body.get("subtype") == "thinking_tokens":
            _keys(body, {"type", "subtype", "session_id", "uuid", "estimated_tokens", "estimated_tokens_delta"})
            self._session(body)
            if not isinstance(body.get("session_id"), str):
                raise ProtocolRejected("invalid_session")
            for field in ("estimated_tokens", "estimated_tokens_delta"):
                value = body.get(field)
                if type(value) is not int or not 0 <= value <= 1_000_000:
                    raise ProtocolRejected("invalid_thinking_estimate")
            # UI estimates carry no completion, usage-billing or quota authority.
            # Do not retain or expose chain-of-thought content or numeric values.
            return NativeEvent("thinking_estimate", digest, "unverified_estimate")
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
                    "analytics_disabled",
                    "product_feedback_disabled",
                    "capabilities",
                    "terminal_slash_commands",
                    "fast_mode_state",
                    "fast_mode_disabled_reason",
                    "messaging_socket_path",
                },
            )
            if body.get("subtype") != "init" or self.session is not None:
                raise ProtocolRejected("unexpected_system_event")
            session = _text(body.get("session_id"), maximum=128)
            if not session:
                raise ProtocolRejected("invalid_session")
            if body.get("claude_code_version", CLAUDE_VERSION) != CLAUDE_VERSION:
                raise ProtocolRejected("cli_version_mismatch")
            if self._capture_candidate and not {"tools", "mcp_servers", "claude_code_version"}.issubset(body):
                raise ProtocolRejected("missing_profile_metadata")
            # These are pinned transport/UI metadata, not model tool grants.
            capabilities = body.get("capabilities", [])
            if not isinstance(capabilities, list) or any(
                not isinstance(item, str)
                or item not in {"interrupt_receipt_v1", "interrupt_cancel_queued_v1", "msg_lifecycle_v1"}
                for item in capabilities
            ):
                raise ProtocolRejected("unexpected_transport_capability")
            commands = body.get("terminal_slash_commands", [])
            if not isinstance(commands, list) or any(
                not isinstance(item, str) or item not in {"doctor", "color", "reload-plugins"} for item in commands
            ):
                raise ProtocolRejected("unexpected_terminal_command")
            if body.get("fast_mode_state", "off") != "off" or body.get(
                "fast_mode_disabled_reason", "sdk_opt_in_required"
            ) not in (None, "sdk_opt_in_required"):
                raise ProtocolRejected("unexpected_fast_mode")
            for flag in ("analytics_disabled", "product_feedback_disabled"):
                if flag in body and body[flag] is not True:
                    raise ProtocolRejected("telemetry_not_disabled")
            if "messaging_socket_path" in body:
                _text(body["messaging_socket_path"], maximum=1024)
            tools = body.get("tools", [])
            if not isinstance(tools, list) or any(not isinstance(tool, str) for tool in tools):
                raise ProtocolRejected("invalid_tools")
            if set(tools) - self.allowed_tools:
                raise ProtocolRejected("unexpected_tool_capability")
            servers = body.get("mcp_servers", [])
            if (
                not isinstance(servers, list)
                or len(servers) != len(self.allowed_mcp_servers)
                or any(
                    not isinstance(server, dict)
                    or set(server) != {"name", "status"}
                    or type(server["name"]) is not str
                    or server["name"] not in self.allowed_mcp_servers
                    or server["status"] != "connected"
                    for server in servers
                )
                or len({server["name"] for server in servers}) != len(servers)
            ):
                raise ProtocolRejected("unexpected_mcp_server")
            if self.allowed_mcp_servers:
                if (
                    set(tools) != self.allowed_tools
                    or len(tools) != len(self.allowed_tools)
                    or body.get("permissionMode") != "default"
                    or any(body.get(field, []) != [] for field in ("skills", "slash_commands", "plugins"))
                    or body.get("apiKeySource") != "none"
                    or body.get("model") != "claude-haiku-4-5-20251001"
                    or body.get("agents") != ["claude", "Explore", "general-purpose", "Plan", "statusline-setup"]
                ):
                    raise ProtocolRejected("unexpected_mcp_profile_metadata")
            self.session = session
            return NativeEvent("started", digest)
        if kind == "rate_limit_event":
            _keys(body, {"type", "session_id", "uuid", "rate_limit_info"})
            self._session(body, allow_before_init=True)
            info = body.get("rate_limit_info")
            if not isinstance(info, dict):
                raise ProtocolRejected("invalid_rate_limit")
            _keys(
                info,
                {
                    "status",
                    "rateLimitType",
                    "resetsAt",
                    "isUsingOverage",
                    "overageStatus",
                    "overageDisabledReason",
                    "unifiedWindows",
                    "utilization",
                },
            )
            if info.get("status") not in ("allowed", "allowed_warning", "rejected"):
                raise ProtocolRejected("invalid_rate_limit")
            if "utilization" in info:
                utilization = info["utilization"]
                if type(utilization) not in {int, float} or not 0 <= utilization <= 1 or not math.isfinite(utilization):
                    raise ProtocolRejected("invalid_rate_limit")
            if "isUsingOverage" in info and info["isUsingOverage"] is not False:
                raise ProtocolRejected("unapproved_overage")
            if info["status"] == "rejected":
                # Stop the process rather than allowing native backoff/fallback
                # to turn a denied subscription route into further attempts.
                raise ProtocolRejected("quota_unavailable")
            return NativeEvent("rate_limit", digest)
        if kind in {"assistant", "user"}:
            metadata = {"request_id", "timestamp"} if kind == "assistant" else set()
            _keys(
                body,
                {"type", "message", "session_id", "parent_tool_use_id", "uuid", "error", "isSynthetic", "isReplay"}
                | metadata,
            )
            self._session(body)
            for field in metadata:
                if field in body:
                    # Correlation strings are bounded opaque transport metadata,
                    # never trusted task identity, timing or authorization.
                    _text(body[field], maximum=128 if field == "request_id" else 64)
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
                    "api_error_status",
                    "fast_mode_disabled_reason",
                    "fast_mode_state",
                    "first_content_frame_ms",
                    "queued_turn_count",
                    "result_index",
                    "subagent_stats",
                    "terminal_reason",
                    "time_to_request_ms",
                    "ttft_ms",
                    "ttft_stream_ms",
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
            _result_metadata(body, failed=failed)
            if body.get("permission_denials"):
                raise ProtocolRejected("privilege_request_denied")
            text = _text(body.get("result", ""))
            if not failed and subtype == "success":
                if self.session is None or self._tool_ids:
                    raise ProtocolRejected("incomplete_execution")
                status, reason = "CANDIDATE", "independent_checks_required"
                if self._capture_candidate:
                    self.candidate_text = text
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
