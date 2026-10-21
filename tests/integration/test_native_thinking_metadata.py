"""Pinned auxiliary counters never grant native authority or candidate success."""

from __future__ import annotations

import json

import pytest

from panestria.brokers.harness.claude_proposal import _decode_candidate
from panestria.brokers.harness.event_parser import ClaudeEventParser, ProtocolRejected


def line(body):
    return json.dumps(body).encode() + b"\n"


def init(parser):
    parser.feed(line({"type": "system", "subtype": "init", "session_id": "synthetic-native-session"}))


def metadata(**updates):
    return {
        "type": "system",
        "subtype": "thinking_tokens",
        "session_id": "synthetic-native-session",
        "estimated_tokens": 128,
        "estimated_tokens_delta": 16,
        **updates,
    }


def test_estimates_are_metadata_until_a_separate_valid_terminal_result():
    parser = ClaudeEventParser()
    init(parser)
    event = parser.feed(line(metadata()))[0]
    assert event.kind == "thinking_estimate" and event.reason == "unverified_estimate"
    assert parser.result is None and parser.candidate_text is None
    assert not {"estimated_tokens", "estimated_tokens_delta", "thinking"} & vars(event).keys()
    with pytest.raises(ProtocolRejected, match="missing_result"):
        parser.finish(0)
    parser.feed(
        line(
            {
                "type": "result",
                "subtype": "success",
                "session_id": "synthetic-native-session",
                "is_error": False,
                "result": "candidate",
            }
        )
    )
    result = parser.finish(0)
    assert result.status == "CANDIDATE" and result.accepted is False
    with pytest.raises(ProtocolRejected, match="event_after_result"):
        parser.feed(line(metadata()))


@pytest.mark.parametrize("field", ["estimated_tokens", "estimated_tokens_delta"])
@pytest.mark.parametrize("value", [None, True, -1, 1_000_001, "16", 16.0, {}])
def test_unknown_or_invalid_numeric_values_fail_closed(field, value):
    parser = ClaudeEventParser()
    init(parser)
    with pytest.raises(ProtocolRejected, match="invalid_thinking_estimate"):
        parser.feed(line(metadata(**{field: value})))
    assert parser.result is None


def test_thinking_metadata_requires_current_initialized_session():
    parser = ClaudeEventParser()
    with pytest.raises(ProtocolRejected, match="missing_init"):
        parser.feed(line(metadata()))
    init(parser)
    with pytest.raises(ProtocolRejected, match="session_mismatch"):
        parser.feed(line(metadata(session_id="another-session")))
    missing = metadata()
    del missing["session_id"]
    with pytest.raises(ProtocolRejected, match="invalid_session"):
        parser.feed(line(missing))


@pytest.mark.parametrize("extra", [{"approved": True}, {"tools": ["Bash"]}, {"thinking": "PRIVATE_SENTINEL"}])
def test_auxiliary_metadata_cannot_hide_privilege_or_thinking_text(extra):
    parser = ClaudeEventParser()
    init(parser)
    with pytest.raises(ProtocolRejected, match="unknown_field") as exc:
        parser.feed(line(metadata(**extra)))
    assert "PRIVATE_SENTINEL" not in str(exc.value) and parser.result is None


def test_assistant_correlation_metadata_does_not_replace_session_or_complete_work():
    parser = ClaudeEventParser()
    init(parser)
    body = {
        "type": "assistant",
        "session_id": "synthetic-native-session",
        "request_id": "untrusted-correlation-id",
        "timestamp": "untrusted-time-not-an-authoritative-clock",
        "message": {"role": "assistant", "content": []},
    }
    assert parser.feed(line(body))[0].kind == "message" and parser.result is None
    with pytest.raises(ProtocolRejected, match="session_mismatch"):
        parser.feed(line({**body, "session_id": "wrong-session"}))
    with pytest.raises(ProtocolRejected, match="unknown_field"):
        parser.feed(line({**body, "approved": True}))


@pytest.mark.parametrize(
    "field,value", [("request_id", 3), ("request_id", "x" * 129), ("timestamp", None), ("timestamp", "x" * 65)]
)
def test_assistant_correlation_metadata_is_bounded_text(field, value):
    parser = ClaudeEventParser()
    init(parser)
    with pytest.raises(ProtocolRejected, match="invalid_text"):
        parser.feed(
            line(
                {
                    "type": "assistant",
                    "session_id": "synthetic-native-session",
                    field: value,
                    "message": {"role": "assistant", "content": []},
                }
            )
        )


@pytest.mark.parametrize("value", [0, 0.4, 1.0])
@pytest.mark.parametrize("field", ["utilization", "surpassedThreshold"])
def test_rate_limit_ratios_are_only_metadata_not_usable_quota(field, value):
    parser = ClaudeEventParser()
    init(parser)
    event = {
        "type": "rate_limit_event",
        "session_id": "synthetic-native-session",
        "rate_limit_info": {"status": "allowed_warning", field: value, "isUsingOverage": False},
    }
    assert parser.feed(line(event))[0].kind == "rate_limit" and parser.result is None
    with pytest.raises(ProtocolRejected, match="unknown_field"):
        parser.feed(line({**event, "rate_limit_info": {**event["rate_limit_info"], "approved": True}}))
    with pytest.raises(ProtocolRejected, match="unapproved_overage"):
        parser.feed(line({**event, "rate_limit_info": {**event["rate_limit_info"], "isUsingOverage": True}}))
    with pytest.raises(ProtocolRejected, match="quota_unavailable"):
        parser.feed(line({**event, "rate_limit_info": {**event["rate_limit_info"], "status": "rejected"}}))


@pytest.mark.parametrize("value", [None, True, -0.1, 1.1, "0.4", float("inf"), 10**400])
@pytest.mark.parametrize("field", ["utilization", "surpassedThreshold"])
def test_malformed_rate_limit_ratio_never_grants_capacity(field, value):
    parser = ClaudeEventParser()
    init(parser)
    with pytest.raises(ProtocolRejected, match="invalid_rate_limit|invalid_number"):
        parser.feed(
            line(
                {
                    "type": "rate_limit_event",
                    "session_id": "synthetic-native-session",
                    "rate_limit_info": {"status": "allowed", field: value},
                }
            )
        )


def result_metadata():
    return {
        "api_error_status": None,
        "terminal_reason": "completed",
        "result_index": 0,
        "queued_turn_count": 0,
        "fast_mode_state": "off",
        "fast_mode_disabled_reason": "sdk_opt_in_required",
        "first_content_frame_ms": 1,
        "time_to_request_ms": 2,
        "ttft_ms": 3,
        "ttft_stream_ms": 4,
        "subagent_stats": {
            "spawned": 0,
            "started_in_background": 0,
            "max_depth": 0,
            "spawned_by_subagents": 0,
            "completed": 0,
            "failed": 0,
            "requested": {"background": 0, "foreground": 0, "unset": 0},
            "killed": {"parent": 0, "user": 0, "system": 0},
            "refused": {"depth_limit": 0, "concurrency_limit": 0, "budget": 0},
            "by_type": {},
        },
    }


def terminal(**extra):
    return {
        "type": "result",
        "subtype": "success",
        "session_id": "synthetic-native-session",
        "is_error": False,
        "result": "candidate",
        **result_metadata(),
        **extra,
    }


def test_result_metadata_still_needs_independent_acceptance():
    parser = ClaudeEventParser()
    init(parser)
    parser.feed(line(terminal()))
    result = parser.finish(0)
    assert result.status == "CANDIDATE" and result.accepted is False


@pytest.mark.parametrize(
    "extra,reason",
    [
        ({"terminal_reason": "interrupted"}, "incomplete_execution"),
        ({"queued_turn_count": 1}, "unexpected_native_background_work"),
        ({"result_index": 1}, "unexpected_native_background_work"),
        ({"result_index": False}, "unexpected_native_background_work"),
        ({"api_error_status": 429}, "invalid_result_metadata"),
        ({"ttft_ms": -1}, "invalid_result_metadata"),
        ({"time_to_request_ms": 900_001}, "invalid_result_metadata"),
        ({"fast_mode_state": "on"}, "unexpected_fast_mode"),
        ({"fast_mode_disabled_reason": "unknown"}, "unexpected_fast_mode"),
    ],
)
def test_contradictory_result_metadata_never_becomes_a_candidate(extra, reason):
    parser = ClaudeEventParser()
    init(parser)
    with pytest.raises(ProtocolRejected, match=reason):
        parser.feed(line(terminal(**extra)))


@pytest.mark.parametrize("field", list(result_metadata()["subagent_stats"]))
def test_any_native_subagent_activity_or_unknown_stats_fails_closed(field):
    parser = ClaudeEventParser()
    init(parser)
    stats = result_metadata()["subagent_stats"]
    stats[field] = 1 if type(stats[field]) is int else {"unknown": 0}
    with pytest.raises(ProtocolRejected, match="unexpected_native_subagents"):
        parser.feed(line(terminal(subagent_stats=stats)))


@pytest.mark.parametrize(
    "text",
    [
        'prose {"path":"calculator.py","content":"def add(a,b): return a+b"}',
        '```json\n{"path":"calculator.py","content":"def add(a,b): return a+b"}\n``` extra',
        '```json\n{"path":"calculator.py","content":"def add(a,b): return a+b"}\n```\n```json\n{}\n```',
        '```python\n{"path":"calculator.py","content":"def add(a,b): return a+b"}\n```',
        '```json\n{"path":"calculator.py","path":"calculator.py","content":"def add(a,b): return a+b"}\n```',
        '```json\n{"path":"calculator.py","content":"import os"}\n```',
        '```json\n{"path":"calculator.py","content":"def add(a,b): return a+b","approved":true}\n```',
    ],
)
def test_presentation_normalization_never_extracts_arbitrary_prose_or_weakens_candidate_guards(text):
    with pytest.raises((ValueError, ProtocolRejected)):
        _decode_candidate(text)
