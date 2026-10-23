"""Selected requests are exact permission/certificate inputs, never billing evidence."""

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_native_qualification import CANDIDATE, report

from panestria.brokers.harness import claude_check
from panestria.brokers.harness.claude_build import ClaudeScopedBashAdapter
from panestria.brokers.harness.claude_proposal import PINNED_BINARY_SHA256, ClaudeProposalAdapter
from panestria.brokers.harness.cli_profile import BinaryPin
from panestria.brokers.harness.event_parser import ClaudeEventParser, ProtocolRejected
from panestria.contracts.native_model import NATIVE_MODELS, validate_native_model
from panestria.execution.native_build import runtime_versions
from panestria.execution.native_qualification import QualificationUnavailable, validate_report

TOOL = "mcp__panestria__run_scoped_bash"


def init(model):
    return {
        "type": "system",
        "subtype": "init",
        "session_id": "synthetic-model-test",
        "claude_code_version": "2.1.273",
        "model": model,
        "tools": [TOOL],
        "mcp_servers": [{"name": "panestria", "status": "connected"}],
        "permissionMode": "default",
        "apiKeySource": "none",
        "agents": ["claude", "Explore", "general-purpose", "Plan", "statusline-setup"],
    }


def frame(body):
    return json.dumps(body).encode() + b"\n"


@pytest.mark.parametrize("model", NATIVE_MODELS)
def test_selected_argv_and_readonly_settings_disallow_switches_without_native_execution(tmp_path, monkeypatch, model):
    binary = tmp_path / "not-executed"
    binary.write_bytes(b"SYNTHETIC_NOT_A_CLI")
    native = ClaudeProposalAdapter(BinaryPin(binary, PINNED_BINARY_SHA256), tmp_path / "no-login", tmp_path / "unused")
    monkeypatch.setattr(claude_check, "_unchanged", lambda *a: None)
    monkeypatch.setattr(claude_check, "RegisteredCheckSocket", lambda *a, **k: SimpleSocket())
    calls = []

    def metadata(fd, args, directory, env, deadline, config_fd):
        calls.append(args)
        assert args[args.index("--model") + 1] == model
        assert "--fallback-model" not in args and "--bare" not in args
        settings = Path(args[args.index("--settings") + 1])
        assert settings.stat().st_mode & 0o777 == 0o400
        assert json.loads(settings.read_bytes()) == {
            **claude_check.SETTINGS,
            "availableModels": [model],
            "fallbackModel": [],
            "switchModelsOnFlag": False,
        }
        assert not any(k.startswith("ANTHROPIC") or "TOKEN" in k or "KEY" in k for k in env)
        assert Path(env["CLAUDE_CONFIG_DIR"]).is_dir()
        return SimpleNamespace(stdout=frame(init(model)))

    monkeypatch.setattr(claude_check, "run_metadata", metadata)
    observed = ClaudeScopedBashAdapter(native, native_model=model)._launch(
        object(),
        prompt_text="PUBLIC synthetic",
        instruction="no inference",
        tool=TOOL,
        profile="claude-subscription-public-bash-v1",
        startup_only=True,
        cancel=None,
        native_model=model,
    )
    assert len(calls) == 1 and observed.process is None and observed.startup_observed
    assert observed.requested_model == model and observed.hostile_configuration_ignored


class SimpleSocket:
    identity = (1, 2)
    path = Path("/tmp/synthetic-not-connected")
    pid = 1

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


@pytest.mark.parametrize("where", ["startup", "assistant", "usage"])
def test_actual_transport_frames_refuse_model_switches(where):
    selected, other = "claude-sonnet-5", "claude-opus-5"
    parser = ClaudeEventParser(frozenset({TOOL}), allowed_mcp_servers=frozenset({"panestria"}), expected_model=selected)
    if where == "startup":
        with pytest.raises(ProtocolRejected, match="unexpected_mcp_profile_metadata"):
            parser.feed(frame(init(other)))
        assert parser.session is None
        return
    parser.feed(frame(init(selected)))
    if where == "assistant":
        body = {"type": "assistant", "message": {"role": "assistant", "model": other, "content": []}}
    else:
        body = {"type": "result", "subtype": "success", "is_error": False, "modelUsage": {selected: {}, other: {}}}
    with pytest.raises(ProtocolRejected, match="native_model"):
        parser.feed(frame(body))
    assert parser.result is None


def test_selected_model_and_legacy_runtime_identities_are_distinct():
    legacy = runtime_versions()
    assert "requested_model" not in legacy
    for model in NATIVE_MODELS:
        assert runtime_versions(model) == {**legacy, "requested_model": model}
    for bad in ("opus", "sonnet", "best", "default", "opusplan", "fable", "claude-opus-5[1m]", "claude-opus-5,haiku"):
        with pytest.raises(ValueError, match="unsupported_native_model"):
            validate_native_model(bad)


def test_model_specific_qualification_requires_original_requested_and_reported_models():
    selected = "claude-sonnet-5"
    root, suite = report()
    live = next(c for c in suite if c.get("name") == "test_actual_claude_subscription_bash_build_and_exact_review")
    props = live.find("properties")
    with pytest.raises(QualificationUnavailable, match="evidence_incomplete"):
        validate_report(ET.tostring(root), CANDIDATE, selected)
    observation = {"requested_model": selected, "process": {"result": {"reported_init_model": selected}}}
    item = ET.SubElement(props, "property", name="native_observation", value=json.dumps(observation))
    assert len(validate_report(ET.tostring(root), CANDIDATE, selected)) == 11
    observation["process"]["result"]["reported_init_model"] = "claude-opus-5"
    item.set("value", json.dumps(observation))
    with pytest.raises(QualificationUnavailable, match="evidence_incomplete"):
        validate_report(ET.tostring(root), CANDIDATE, selected)
