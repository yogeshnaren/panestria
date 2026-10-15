"""Pinned auxiliary counters never grant native authority or candidate success."""

from __future__ import annotations

import json

import pytest

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
