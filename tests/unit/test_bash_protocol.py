"""The edit profile cannot widen the registered read-check schema or authority."""

import json

import pytest
from test_native_command_protocol import ControllerFixture, decode, frame, initialize

from panestria.brokers.harness.bash_protocol import ScopedBashSession
from panestria.brokers.harness.command_protocol import RegisteredCheckSession


def call(identity="bash", **arguments):
    return frame("tools/call", identity, name="run_scoped_bash", arguments={"job_ref": "build:fixed", **arguments})


def test_separate_bash_profile_exposes_one_bounded_command_and_replay_is_cached():
    executor = ControllerFixture()
    session = ScopedBashSession("build:fixed", executor)
    initialize(session)
    tool = decode(session.handle(frame("tools/list", "list")))["result"]["tools"][0]
    assert tool["name"] == "run_scoped_bash" and tool["annotations"]["readOnlyHint"] is False
    first = session.handle(call(script="printf test"))
    assert session.handle(call(script="printf test")) == first
    assert executor.calls[0][:2] == ("printf test", "build:fixed") and len(executor.calls) == 1
    assert decode(session.handle(call("other", script="printf again")))["error"]["message"] == "call_budget_exhausted"
    read = RegisteredCheckSession(("unit-check",), "candidate:fixed", executor)
    initialize(read)
    assert "error" in decode(read.handle(call(script="printf test"))) and len(executor.calls) == 1


@pytest.mark.parametrize(
    "arguments",
    [
        {"script": ""},
        {"script": " \n"},
        {"script": "nul\0"},
        {"script": "é" * 9000},
        {"script": "a" * 17000},
        {"script": True},
        {"script": "true", "job_ref": "other"},
        {"script": "true", "approved": True},
        {"script": "true", "workspace": "/host"},
    ],
)
def test_bad_scripts_and_model_authority_never_reach_controller(arguments):
    executor = ControllerFixture()
    session = ScopedBashSession("build:fixed", executor)
    initialize(session)
    response = decode(session.handle(call(**arguments)))
    assert "error" in response and not executor.calls
    assert "host" not in json.dumps(response)
