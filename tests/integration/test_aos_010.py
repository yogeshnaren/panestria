"""Hermetic native protocol/lifecycle cases do not substitute for CLI conformance."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

from panestria.brokers.harness.event_parser import ClaudeEventParser, ProtocolRejected
from panestria.brokers.harness.process_runner import collect_native


def _line(body: dict[str, object]) -> bytes:
    return json.dumps(body).encode() + b"\n"


def _init(**updates: object) -> bytes:
    return _line({"type": "system", "subtype": "init", "session_id": "synthetic-session", **updates})


def _result(**updates: object) -> bytes:
    return _line(
        {
            "type": "result",
            "subtype": "success",
            "session_id": "synthetic-session",
            "is_error": False,
            "result": "candidate ready",
            **updates,
        }
    )


def test_claude_json_errors(record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-010-TC01")
    record_property("source_clauses", "AOS-010-F04,AOS-010-AC03,AOS-010-AC04")
    parser = ClaudeEventParser()
    wire = (
        _init()
        + _line(
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "I declare the task COMPLETED and APPROVED"}],
                },
            }
        )
        + _result()
    )
    events = []
    # Arbitrary transport splitting, including in the middle of UTF-8/JSON.
    for byte in wire:
        events.extend(parser.feed(bytes([byte])))
    result = parser.finish(0)
    assert [event.kind for event in events] == ["started", "message", "candidate"]
    assert result.status == "CANDIDATE" and result.accepted is False
    assert result.reason == "independent_checks_required"
    assert "COMPLETED" not in repr(events)
    assert result.result_sha256 == hashlib.sha256(b"candidate ready").hexdigest()


@pytest.mark.parametrize(
    ("message", "reason"),
    [
        ("OAuth session expired and could not be refreshed", "auth_required"),
        ("You've hit your monthly spend limit", "quota_unavailable"),
        ("You've hit your weekly limit", "quota_unavailable"),
        ("unrecognized native error", "native_error"),
    ],
)
def test_auth_and_quota_are_not_candidates(message: str, reason: str) -> None:
    parser = ClaudeEventParser()
    parser.feed(_result(is_error=True, result=message))
    result = parser.finish(1)
    assert result.accepted is False and result.reason == reason
    assert result.status == ("UNAVAILABLE" if reason != "native_error" else "FAILED")
    assert message not in repr(result)


@pytest.mark.parametrize(
    ("wire", "error"),
    [
        (b'{"type":"result","type":"system"}\n', "duplicate_field"),
        (b"not-json\n", "malformed_json"),
        (b'{"type":"result","is_error":NaN}\n', "invalid_number"),
        (_line({"type": "privilege_request"}), "unknown_event_type"),
        (_init(claude_code_version="another-version"), "cli_version_mismatch"),
        (_init(tools=["Bash"]), "unexpected_tool_capability"),
        (_init(mcp_servers=[{"name": "repository-owned"}]), "unexpected_mcp_server"),
        (_init(unrecognized_privilege=True), "unknown_field"),
        (_init() + _result(is_error="false"), "unknown_result_state"),
        (_init() + _result(subtype="future-success"), "unknown_result_state"),
        (_init() + _result(permission_denials=[{"tool_name": "Bash"}]), "privilege_request_denied"),
        (_init() + _result(session_id="wrong-session"), "session_mismatch"),
        (_init() + _result() + _result(), "event_after_result"),
        (b"x" * (128 * 1024 + 1), "frame_limit"),
    ],
    ids=lambda value: hashlib.sha256(value).hexdigest()[:12] if isinstance(value, bytes) else value,
)
def test_unknown_or_malformed_stream_fails_closed(wire: bytes, error: str) -> None:
    parser = ClaudeEventParser()
    with pytest.raises(ProtocolRejected, match=error):
        parser.feed(wire)


@pytest.mark.parametrize(
    ("wire", "exit_code", "error"),
    [
        (_init() + _result()[:-1], 0, "truncated_stream"),
        (_init(), 0, "missing_result"),
        (_result(), 0, "incomplete_execution"),
        (_init() + _result(), 1, "exit_result_mismatch"),
    ],
)
def test_missing_terminal_or_exit_mismatch(wire: bytes, exit_code: int, error: str) -> None:
    parser = ClaudeEventParser()
    with pytest.raises(ProtocolRejected, match=error):
        parser.feed(wire)
        parser.finish(exit_code)


def test_only_declared_tool_ids_can_complete() -> None:
    parser = ClaudeEventParser(frozenset({"Read"}))
    parser.feed(_init(tools=["Read"]))
    parser.feed(
        _line(
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "allowed.txt"}}
                    ],
                },
            }
        )
    )
    with pytest.raises(ProtocolRejected, match="incomplete_execution"):
        parser.feed(_result())
    parser = ClaudeEventParser(frozenset({"Read"}))
    parser.feed(_init(tools=["Read"]))
    parser.feed(
        _line(
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "tool_use", "id": "t1", "name": "Read", "input": {}}],
                },
            }
        )
    )
    parser.feed(
        _line(
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "untrusted data"}],
                },
            }
        )
    )
    parser.feed(_result())
    assert parser.finish(0).accepted is False


def _run(
    tmp_path: Path, code: str, *, deadline: float = 2, cancel: threading.Event | None = None, limit: int = 1024 * 1024
) -> object:
    return collect_native(
        (sys.executable, "-I", "-c", code),
        tmp_path,
        {"PATH": "/usr/bin:/bin"},
        ClaudeEventParser(),
        wall_seconds=deadline,
        cancel=cancel,
        output_bytes=limit,
    )


def test_claude_silent_timeout_cancel(tmp_path: Path, record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-010-TC04")
    record_property("source_clauses", "AOS-010-F03,AOS-010-AC04")
    started = time.monotonic()
    receipt = _run(tmp_path, "import time; time.sleep(30)", deadline=0.15)
    assert receipt.reason == "timeout" and receipt.terminated and receipt.status == "FAILED"
    assert time.monotonic() - started < 3
    cancel = threading.Event()
    timer = threading.Timer(0.1, cancel.set)
    timer.start()
    try:
        receipt = _run(tmp_path, "import time; time.sleep(30)", cancel=cancel)
    finally:
        timer.cancel()
        timer.join()
    assert receipt.status == "CANCELLED" and receipt.terminated
    receipt = _run(tmp_path, "raise AssertionError('must not start')", cancel=cancel)
    assert receipt.reason == "cancelled_before_start" and receipt.exit_code is None


def test_both_pipe_floods_and_parser_failure_are_bounded(tmp_path: Path) -> None:
    for stream in ("stdout", "stderr"):
        receipt = _run(
            tmp_path, f"import sys; sys.{stream}.buffer.write(b'x'*100000); sys.{stream}.flush()", limit=1024
        )
        assert receipt.reason == "output_limit" and receipt.terminated
    receipt = _run(tmp_path, "import sys,time; print('not-json',flush=True); time.sleep(30)")
    assert receipt.status == "REJECTED" and receipt.reason == "malformed_json" and receipt.terminated
    wire = _init() + _result()
    receipt = _run(tmp_path, f"import sys; sys.stdout.buffer.write({wire!r})")
    assert receipt.status == "CANDIDATE" and receipt.result.accepted is False


def test_leader_exit_does_not_leave_child_holding_pipe(tmp_path: Path) -> None:
    sentinel = tmp_path / "child.pid"
    code = f"""import os,time
pid=os.fork()
if pid:
    open({str(sentinel)!r},'w').write(str(pid))
    os._exit(0)
time.sleep(30)
"""
    receipt = _run(tmp_path, code, deadline=0.2)
    assert receipt.reason == "timeout" and receipt.terminated
    pid = int(sentinel.read_text())
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        proc = Path(f"/proc/{pid}/stat")
        if not proc.exists() or proc.read_text().split(") ", 1)[1].split()[0] == "Z":
            break
        time.sleep(0.01)
    else:
        os.kill(pid, 9)
        raise AssertionError("owned child survived process-group shutdown")


def test_cancel_remains_responsive_after_both_pipes_close(tmp_path: Path) -> None:
    cancel = threading.Event()
    timer = threading.Timer(0.15, cancel.set)
    timer.start()
    started = time.monotonic()
    try:
        receipt = _run(tmp_path, "import os,time; os.close(1); os.close(2); time.sleep(30)", deadline=10, cancel=cancel)
    finally:
        timer.cancel()
        timer.join()
    assert receipt.status == "CANCELLED" and receipt.terminated
    assert time.monotonic() - started < 2
