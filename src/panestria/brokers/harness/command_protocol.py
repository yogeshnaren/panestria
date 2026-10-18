"""Internal MCP wire state machine; execution authority belongs to its trusted callback."""

from __future__ import annotations

import hashlib
import json
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeGuard

from panestria.contracts.native_command import RegisteredCheckReceipt
from panestria.contracts.native_tools import MAX_PAYLOAD_BYTES, canonical_payload

VERSION = "2025-06-18"
RequestId = str | int
Key = tuple[type[str] | type[int], RequestId]
CheckExecutor = Callable[[str, str, threading.Event], RegisteredCheckReceipt]


@dataclass(frozen=True)
class PreparedCheck:
    identity: RequestId
    key: Key
    digest: str
    command_ref: str
    cancel: threading.Event


def _id(value: object) -> TypeGuard[RequestId]:
    return (type(value) is int and 0 <= value <= 2**53 - 1) or (
        type(value) is str and bool(re.fullmatch(r"[a-zA-Z0-9._:-]{1,64}", value))
    )


def _wire(body: dict[str, Any]) -> bytes:
    return json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _error(identity: RequestId | None, code: int, reason: str) -> bytes:
    return _wire({"jsonrpc": "2.0", "id": identity, "error": {"code": code, "message": reason}})


def _result(identity: RequestId, body: dict[str, Any]) -> bytes:
    return _wire({"jsonrpc": "2.0", "id": identity, "result": body})


def _params(body: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
    params = body.get("params", {})
    if not isinstance(params, dict) or not set(params) <= allowed | {"_meta"}:
        raise ValueError
    if "_meta" in params:
        meta = params["_meta"]
        allowed_meta = {"progressToken"} | ({"claudecode/toolUseId"} if body.get("method") == "tools/call" else set())
        if not isinstance(meta, dict) or not set(meta) <= allowed_meta:
            raise ValueError
        if any(not _id(value) for value in meta.values()):
            raise ValueError
        # Native call correlation is opaque display data, never scope/lease/approval authority.
    return params


class RegisteredCheckSession:
    server_name = "panestria-registered-check"

    def __init__(
        self,
        command_refs: tuple[str, ...],
        candidate_ref: str,
        executor: CheckExecutor,
        *,
        max_calls: int = 4,
        max_frames: int = 64,
    ) -> None:
        if (
            type(command_refs) is not tuple
            or not 1 <= len(command_refs) <= 16
            or any(type(ref) is not str or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", ref) for ref in command_refs)
            or len(set(command_refs)) != len(command_refs)
            or type(candidate_ref) is not str
            or not re.fullmatch(r"[a-z0-9][a-z0-9:._-]{0,127}", candidate_ref)
            or type(max_calls) is not int
            or not 1 <= max_calls <= 16
            or type(max_frames) is not int
            or not max_calls + 2 <= max_frames <= 128
            or not callable(executor)
        ):
            raise ValueError("invalid_registered_check_session")
        self._commands, self._candidate, self._executor = command_refs, candidate_ref, executor
        self._max_calls, self._max_frames = max_calls, max_frames
        self._calls = self._frames = 0
        self._state = "NEW"
        self._lock = threading.RLock()
        self._responses: dict[Key, tuple[str, bytes | None]] = {}
        self._active: dict[Key, PreparedCheck] = {}
        self._running: set[Key] = set()

    @property
    def references(self) -> tuple[tuple[str, ...], str]:
        return self._commands, self._candidate

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._state == "CLOSED"

    def close(self) -> None:
        with self._lock:
            self._state = "CLOSED"
            for pending in self._active.values():
                pending.cancel.set()  # Request cancellation, never claim process reaping.

    def _notification(self, body: dict[str, Any]) -> None:
        method = body["method"]
        try:
            if method == "notifications/initialized":
                _params(body, set())
                if self._state == "INITIALIZING":
                    self._state = "READY"
            elif method == "notifications/cancelled":
                params = _params(body, {"requestId", "reason"})
                identity = params.get("requestId")
                if not _id(identity):
                    return
                if "reason" in params and (type(params["reason"]) is not str or len(params["reason"]) > 256):
                    return
                pending = self._active.get((type(identity), identity))
                if pending:
                    pending.cancel.set()
        except ValueError:
            return

    def _initialize(self, identity: RequestId, body: dict[str, Any]) -> bytes:
        if self._state != "NEW":
            return _error(identity, -32600, "session_already_initialized")
        params = _params(body, {"protocolVersion", "capabilities", "clientInfo"})
        version, caps, info = params.get("protocolVersion"), params.get("capabilities"), params.get("clientInfo")
        if (
            type(version) is not str
            or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", version)
            or not isinstance(caps, dict)
            or len(caps) > 16
            or any(type(value) is not dict or len(key) > 64 for key, value in caps.items())
            or not isinstance(info, dict)
            or not {"name", "version"} <= set(info) <= {"name", "version", "title", "description", "websiteUrl"}
            or any(
                type(value) is not str
                or not 1 <= len(value) <= (256 if key in {"description", "websiteUrl"} else 64)
                or any(ord(character) < 32 for character in value)
                for key, value in info.items()
            )
        ):
            raise ValueError
        # Newer client display metadata is bounded and ignored. Negotiated wire
        # version and server capabilities remain the pinned June dialect.
        self._state = "INITIALIZING"
        return _result(
            identity,
            {
                "protocolVersion": VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": self.server_name, "version": "1"},
            },
        )

    def _tool_list(self) -> dict[str, Any]:
        return {
            "tools": [
                {
                    "name": "run_registered_check",
                    "description": "Run a controller-bound reviewed check on the fixed candidate.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "command_ref": {"type": "string", "enum": list(self._commands)},
                            "candidate_ref": {"type": "string", "const": self._candidate},
                        },
                        "required": ["command_ref", "candidate_ref"],
                        "additionalProperties": False,
                    },
                    "annotations": {
                        "readOnlyHint": True,
                        "destructiveHint": False,
                        "idempotentHint": False,
                        "openWorldHint": False,
                    },
                }
            ]
        }

    def handle(self, raw: bytes) -> bytes | None:
        prepared = self.prepare(raw)
        return self.run(prepared) if isinstance(prepared, PreparedCheck) else prepared

    def _command(self, params: dict[str, Any]) -> str:
        args = params.get("arguments")
        if (
            params.get("name") != "run_registered_check"
            or not isinstance(args, dict)
            or set(args) != {"command_ref", "candidate_ref"}
            or type(args["command_ref"]) is not str
            or args["command_ref"] not in self._commands
            or args["candidate_ref"] != self._candidate
        ):
            raise ValueError
        return args["command_ref"]

    def prepare(self, raw: bytes) -> bytes | PreparedCheck | None:
        """Accept frames in wire order before moving only actual execution to a worker."""
        with self._lock:
            if self.closed:
                return None
            self._frames += 1
            if self._frames > self._max_frames:
                self.close()
            if self.closed:
                return None
        try:
            if type(raw) is not bytes or len(raw) > MAX_PAYLOAD_BYTES:
                raise ValueError
            canonical = canonical_payload(raw.decode("utf-8"))
            body = json.loads(canonical)
        except (ValueError, UnicodeError, RecursionError):
            return _error(None, -32700, "invalid_json")
        if (
            not set(body) <= {"jsonrpc", "id", "method", "params"}
            or body.get("jsonrpc") != "2.0"
            or type(body.get("method")) is not str
        ):
            return _error(None, -32600, "invalid_request")
        if "id" in body and not _id(body["id"]):
            return _error(None, -32600, "invalid_request_id")
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        with self._lock:
            if self.closed:
                return None
            if "id" not in body:
                self._notification(body)
                return None
            identity = body["id"]
            key: Key = (type(identity), identity)
            previous = self._responses.get(key)
            if previous:
                return previous[1] if previous[0] == digest else _error(identity, -32600, "request_id_reused")
            pending = self._active.get(key)
            if pending:
                return (
                    _error(identity, -32000, "request_in_progress")
                    if pending.digest == digest
                    else _error(identity, -32600, "request_id_reused")
                )
            method, signal, command = body["method"], None, None
            try:
                if method == "initialize":
                    response = self._initialize(identity, body)
                elif method == "ping":
                    _params(body, set())
                    response = _result(identity, {})
                elif self._state != "READY":
                    response = _error(identity, -32000, "session_not_ready")
                elif method == "tools/list":
                    _params(body, set())
                    response = _result(identity, self._tool_list())
                elif method == "tools/call":
                    params = _params(body, {"name", "arguments"})
                    requested = self._command(params)
                    if self._active:
                        response = _error(identity, -32000, "session_busy")
                    elif self._calls >= self._max_calls:
                        response = _error(identity, -32000, "call_budget_exhausted")
                    else:
                        self._calls += 1
                        command, signal = requested, threading.Event()
                        self._active[key] = PreparedCheck(identity, key, digest, command, signal)
                        response = None
                else:
                    response = _error(identity, -32601, "method_not_found")
            except (ValueError, TypeError):
                response = _error(identity, -32602, "invalid_params")
            if signal is None or command is None:
                self._responses[key] = (digest, response)
                return response
            return self._active[key]

    def run(self, operation: PreparedCheck) -> bytes | None:
        """Consume an accepted operation once; never accept model-supplied dispatch objects."""
        with self._lock:
            if self._active.get(operation.key) is not operation or operation.key in self._running:
                return _error(None, -32600, "invalid_or_consumed_dispatch")
            self._running.add(operation.key)
        identity, key, digest, signal = operation.identity, operation.key, operation.digest, operation.cancel
        try:
            receipt = (
                RegisteredCheckReceipt(outcome="CANCELLED")
                if signal.is_set() or self.closed
                else RegisteredCheckReceipt.model_validate(
                    self._executor(operation.command_ref, self._candidate, signal)
                )
            )
        except Exception:
            receipt = RegisteredCheckReceipt(outcome="UNKNOWN")
        payload = receipt.model_dump()
        response: bytes | None = _result(
            identity,
            {
                "content": [{"type": "text", "text": json.dumps(payload, sort_keys=True, separators=(",", ":"))}],
                "structuredContent": payload,
                "isError": receipt.outcome != "COMPLETED" or receipt.exit_code != 0,
            },
        )
        with self._lock:
            self._active.pop(key, None)
            self._running.discard(key)
            if signal.is_set() or self.closed:
                response = None  # Cancelled requests have no protocol completion response.
            self._responses[key] = (digest, response)
            return response
