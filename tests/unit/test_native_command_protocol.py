"""MCP session checks use a labeled controller fixture, not live native authority."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from panestria.brokers.harness.command_protocol import VERSION, RegisteredCheckSession
from panestria.contracts.native_command import RegisteredCheckReceipt


def frame(method, identity="request", **params):
    body = {"jsonrpc": "2.0", "method": method, "params": params}
    if identity is not None:
        body["id"] = identity
    return json.dumps(body).encode()


def decode(reply):
    return json.loads(reply) if reply is not None else None


class ControllerFixture:
    def __init__(self):
        self.calls = []
        self.receipt = RegisteredCheckReceipt(outcome="COMPLETED", exit_code=0, report_sha256="ab" * 32)

    def __call__(self, command, candidate, cancel):
        self.calls.append((command, candidate, cancel))
        return self.receipt


def initialize(session):
    response = decode(
        session.handle(
            frame(
                "initialize",
                "init",
                protocolVersion="2025-11-25",
                capabilities={"roots": {"listChanged": True}, "sampling": {}},
                clientInfo={"name": "fixture", "version": "1"},
            )
        )
    )
    assert response["result"]["protocolVersion"] == VERSION
    assert response["result"]["capabilities"] == {"tools": {"listChanged": False}}
    assert session.handle(frame("notifications/initialized", None)) is None


def call(identity="run", **changes):
    return frame(
        "tools/call",
        identity,
        name="run_registered_check",
        arguments={"command_ref": "unit-check", "candidate_ref": "candidate:fixed", **changes},
    )


@pytest.fixture
def ready():
    executor = ControllerFixture()
    session = RegisteredCheckSession(("unit-check",), "candidate:fixed", executor)
    initialize(session)
    return session, executor


def test_only_fixed_schema_and_metadata_are_exposed(ready):
    session, executor = ready
    tools = decode(session.handle(frame("tools/list", "list")))["result"]["tools"]
    assert len(tools) == 1 and tools[0]["name"] == "run_registered_check"
    assert tools[0]["inputSchema"]["additionalProperties"] is False
    assert tools[0]["inputSchema"]["properties"]["candidate_ref"] == {"type": "string", "const": "candidate:fixed"}
    response = decode(session.handle(call()))["result"]
    assert response["isError"] is False
    assert response["structuredContent"] == json.loads(response["content"][0]["text"])
    assert response["structuredContent"] == {"outcome": "COMPLETED", "exit_code": 0, "report_sha256": "ab" * 32}
    assert [(a, b) for a, b, _ in executor.calls] == [("unit-check", "candidate:fixed")]


@pytest.mark.parametrize(
    "field",
    [
        "owner_id",
        "project_id",
        "approved",
        "policy_ref",
        "lease_epoch",
        "path",
        "argv",
        "shell",
        "deadline_seconds",
        "payload_json",
        "credentials",
    ],
)
def test_client_authority_and_shell_fields_never_reach_controller(ready, field):
    session, executor = ready
    response = decode(session.handle(call(**{field: "PRIVATE_SENTINEL"})))
    assert response["error"]["code"] == -32602 and not executor.calls
    assert "PRIVATE_SENTINEL" not in json.dumps(response)


@pytest.mark.parametrize(
    "changes", [{"command_ref": "unregistered"}, {"candidate_ref": "candidate:other"}, {"command_ref": True}]
)
def test_wrong_reference_never_dispatches(ready, changes):
    session, executor = ready
    assert "error" in decode(session.handle(call(**changes)))
    assert not executor.calls


def test_request_id_retry_is_cached_but_changed_reuse_denies(ready):
    session, executor = ready
    first = session.handle(call())
    assert session.handle(call()) == first and len(executor.calls) == 1
    assert decode(session.handle(call(candidate_ref="candidate:other")))["error"]["message"] == "request_id_reused"
    assert len(executor.calls) == 1


@pytest.mark.parametrize(
    "raw",
    [
        b"[{}]",
        b"{",
        b'{"jsonrpc":"2.0","id":1,"id":2}',
        b'{"value":NaN}',
        b"\xff",
        b"x" * 32769,
        b'{"value":' + b"[" * 40 + b"0" + b"]" * 40 + b"}",
    ],
)
def test_bad_json_never_echoes_payload_or_calls_executor(ready, raw):
    session, executor = ready
    assert decode(session.handle(raw))["error"]["code"] == -32700
    assert not executor.calls


@pytest.mark.parametrize("identity", [True, None, 1.5, -1, 2**53, "private secret with spaces", "x" * 65])
def test_invalid_request_id_is_not_reflected(ready, identity):
    session, executor = ready
    request = json.loads(call())
    request["id"] = identity
    response = decode(session.handle(json.dumps(request).encode()))
    assert response["id"] is None and not executor.calls


def test_tools_need_both_handshake_phases_and_notifications_cannot_dispatch():
    executor = ControllerFixture()
    session = RegisteredCheckSession(("unit-check",), "candidate:fixed", executor)
    assert session.handle(frame("notifications/initialized", None)) is None
    assert decode(session.handle(call("before")))["error"]["message"] == "session_not_ready"
    session.handle(
        frame(
            "initialize",
            "init",
            protocolVersion=VERSION,
            capabilities={},
            clientInfo={"name": "fixture", "version": "1"},
        )
    )
    assert decode(session.handle(call("between")))["error"]["message"] == "session_not_ready"
    session.handle(frame("notifications/initialized", None))
    assert (
        session.handle(
            frame(
                "tools/call",
                None,
                name="run_registered_check",
                arguments={"command_ref": "unit-check", "candidate_ref": "candidate:fixed"},
            )
        )
        is None
    )
    assert not executor.calls


def test_no_resources_roots_sampling_or_arbitrary_tool_can_be_requested(ready):
    session, executor = ready
    for i, method in enumerate(("resources/read", "roots/list", "sampling/createMessage", "prompts/get")):
        response = decode(session.handle(frame(method, i, uri="file:///private")))
        assert response["error"]["code"] == -32601
        assert "private" not in json.dumps(response)
    assert not executor.calls


def test_budgets_and_close_never_enable_more_execution():
    executor = ControllerFixture()
    session = RegisteredCheckSession(("unit-check",), "candidate:fixed", executor, max_calls=1, max_frames=8)
    initialize(session)
    assert "result" in decode(session.handle(call("first")))
    assert decode(session.handle(call("second")))["error"]["message"] == "call_budget_exhausted"
    for i in range(20):
        session.handle(frame("ping", i))
    assert session.closed and session.handle(call("last")) is None
    assert len(executor.calls) == 1 and len(session._responses) <= 8


def test_callback_exception_and_invalid_receipt_stay_unknown_and_redacted():
    def denied(*args):
        raise RuntimeError("PRIVATE_SENTINEL")

    for callback in (denied, lambda *args: {"outcome": "COMPLETED", "stdout": "PRIVATE_SENTINEL"}):
        session = RegisteredCheckSession(("unit-check",), "candidate:fixed", callback)
        initialize(session)
        response = decode(session.handle(call()))
        assert response["result"]["structuredContent"]["outcome"] == "UNKNOWN"
        assert response["result"]["isError"] is True
        assert "PRIVATE_SENTINEL" not in json.dumps(response)


def test_busy_and_cancellation_are_available_during_the_callback():
    entered = threading.Event()
    calls = []

    def blocked(command, candidate, cancel):
        calls.append(command)
        entered.set()
        assert cancel.wait(3)
        return RegisteredCheckReceipt(outcome="CANCELLED")

    session = RegisteredCheckSession(("unit-check",), "candidate:fixed", blocked)
    initialize(session)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(session.handle, call("running"))
        assert entered.wait(2)
        assert decode(session.handle(call("other")))["error"]["message"] == "session_busy"
        assert decode(session.handle(call("running")))["error"]["message"] == "request_in_progress"
        assert (
            decode(session.handle(call("running", candidate_ref="candidate:other")))["error"]["message"]
            == "request_id_reused"
        )
        assert (
            session.handle(frame("notifications/cancelled", None, requestId="running", reason="PRIVATE_SENTINEL"))
            is None
        )
        assert future.result(timeout=2) is None
    assert session.handle(call("running")) is None and calls == ["unit-check"]
    assert session.handle(frame("notifications/cancelled", None, requestId="init")) is None
    assert session.handle(frame("notifications/cancelled", None, requestId="unknown")) is None


@pytest.mark.parametrize(
    "receipt",
    [
        {"outcome": "COMPLETED"},
        {"outcome": "COMPLETED", "exit_code": True, "report_sha256": "ab" * 32},
        {"outcome": "DENIED", "exit_code": 0},
        {"outcome": "PASS"},
        {"outcome": "UNKNOWN", "approved": True},
    ],
)
def test_receipts_cannot_self_assert_completion_or_include_arbitrary_output(receipt):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        RegisteredCheckReceipt(**receipt)


def test_failed_command_is_execution_metadata_and_not_a_task_verdict(ready):
    session, executor = ready
    executor.receipt = RegisteredCheckReceipt(outcome="COMPLETED", exit_code=1, report_sha256="ab" * 32)
    reply = decode(session.handle(call()))["result"]
    assert reply["isError"] is True
    assert "verdict" not in reply["structuredContent"] and "accepted" not in reply["structuredContent"]


def test_close_requests_cancellation_without_claiming_a_reaped_process():
    entered = threading.Event()
    observed = []

    def blocked(command, candidate, cancel):
        observed.append(cancel)
        entered.set()
        assert cancel.wait(3)
        return RegisteredCheckReceipt(outcome="UNKNOWN")

    session = RegisteredCheckSession(("unit-check",), "candidate:fixed", blocked)
    initialize(session)
    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(session.handle, call())
        assert entered.wait(2)
        session.close()
        assert session.closed and observed[0].is_set()
        assert running.result(timeout=2) is None
    frames = session._frames
    assert session.handle(call()) is None and session._frames == frames


@pytest.mark.parametrize(
    "changes",
    [
        {"command_refs": ()},
        {"command_refs": ("x", "x")},
        {"command_refs": ([],)},
        {"candidate_ref": "/private/path"},
        {"max_calls": True},
        {"max_frames": 999},
    ],
)
def test_trusted_constructor_is_still_closed_and_bounded(changes):
    args = {
        "command_refs": ("unit-check",),
        "candidate_ref": "candidate:fixed",
        "executor": ControllerFixture(),
        **changes,
    }
    with pytest.raises(ValueError, match="invalid_registered_check_session"):
        RegisteredCheckSession(**args)
