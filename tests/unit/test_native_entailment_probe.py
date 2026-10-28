"""Injected native data/launch guards only, never actual subscription inference."""

import json
from pathlib import Path

import pytest

import panestria.execution.native_entailment_probe as module
from panestria.brokers.harness.claude_proposal import PINNED_BINARY_SHA256
from panestria.brokers.harness.cli_profile import BinaryPin
from panestria.brokers.harness.event_parser import ProtocolRejected
from panestria.brokers.harness.process_runner import ProcessReceipt
from panestria.contracts.native_model import NATIVE_MODELS
from panestria.verification.entailment import load_snli_subset

CORPUS = Path(__file__).resolve().parents[1] / "fixtures/research/snli-v1/corpus.json"


def init():
    return {
        "type": "system",
        "subtype": "init",
        "session_id": "synthetic",
        "claude_code_version": "2.1.273",
        "model": "claude-haiku-4-5-20251001",
        "apiKeySource": "none",
        "permissionMode": "default",
        **{key: [] for key in ("tools", "mcp_servers", "skills", "plugins", "slash_commands")},
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("tools", ["Bash"]),
        ("mcp_servers", [{"name": "untrusted"}]),
        ("model", "other-model"),
        ("apiKeySource", "env"),
        ("permissionMode", "bypassPermissions"),
        ("skills", ["repo-skill"]),
    ],
)
def test_unapproved_profile_never_becomes_native_data_candidate(field, value):
    body = init()
    body[field] = value
    with pytest.raises(ProtocolRejected):
        module._PublicFixtureParser().feed((json.dumps(body) + "\n").encode())


@pytest.mark.parametrize("change", ["missing", "duplicate", "extra-field", "unknown-id", "duplicate-json"])
def test_batch_must_cover_exact_case_ids_and_closed_fields(change):
    cases = load_snli_subset(CORPUS).model_inputs("calibration")
    body = {"predictions": [{"case_id": c.case_id, "verdict": "UNKNOWN"} for c in cases]}
    if change == "missing":
        body["predictions"].pop()
    elif change == "duplicate":
        body["predictions"][0] = body["predictions"][1]
    elif change == "extra-field":
        body["approved"] = True
    elif change == "unknown-id":
        body["predictions"][0]["case_id"] = "ff" * 12
    raw = json.dumps(body)
    if change == "duplicate-json":
        raw = raw[:-1] + ',"predictions":[]}'
    with pytest.raises((ValueError, ProtocolRejected)):
        module._decode(raw, {c.case_id for c in cases})


def test_overage_signal_is_rejected_and_remaining_quota_not_invented():
    parser = module._PublicFixtureParser()
    with pytest.raises(ProtocolRejected, match="unapproved_overage"):
        parser.feed(
            json.dumps(
                {"type": "rate_limit_event", "rate_limit_info": {"status": "allowed", "isUsingOverage": True}}
            ).encode()
            + b"\n"
        )


@pytest.mark.parametrize(
    "native_model,tamper",
    [(None, value) for value in (None, "rubric", "mcp", "hostile-hook")] + [(model, None) for model in NATIVE_MODELS],
)
def test_injected_launch_uses_only_public_pinned_corpus_and_preserves_profile_controls(
    tmp_path, monkeypatch, native_model, tamper
):
    binary = tmp_path / "binary"
    binary.write_bytes(b"synthetic")
    binary.chmod(0o700)
    config = tmp_path / "config"
    config.mkdir(mode=0o700)
    monkeypatch.setattr(module.ClaudeProposalAdapter, "inspect", lambda _self: None)
    monkeypatch.setattr(module, "_unchanged", lambda *_a: None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "SYNTHETIC_MUST_NOT_PASS")
    directories = []

    def injected(argv, cwd, env, parser, **kwargs):
        directories.append(cwd)
        assert argv[0].startswith("/proc/self/fd/") and env["CLAUDE_CONFIG_DIR"].startswith("/proc/self/fd/")
        assert argv[argv.index("--tools") + 1] == "" and "--safe-mode" in argv and "--restricted" in argv
        assert argv[argv.index("--setting-sources") + 1] == "" and "--disable-slash-commands" in argv
        assert "--strict-mcp-config" in argv
        assert json.loads(Path(argv[argv.index("--mcp-config") + 1]).read_bytes()) == {"mcpServers": {}}
        settings = json.loads(Path(argv[argv.index("--settings") + 1]).read_bytes())
        assert settings == {
            **module.SETTINGS,
            **(
                {"availableModels": [native_model], "fallbackModel": [], "switchModelsOnFlag": False}
                if native_model is not None
                else {}
            ),
        }
        assert argv[argv.index("--model") + 1] == (native_model or "haiku")
        assert "--fallback-model" not in argv
        assert env["CLAUDE_CODE_DISABLE_CLAUDE_MDS"] == "1" and env["ENABLE_CLAUDEAI_MCP_SERVERS"] == "false"
        assert argv[argv.index("--max-budget-usd") + 1] == "0.25"
        assert "ANTHROPIC_API_KEY" not in env and env["HOME"] == str(cwd)
        assert Path(argv[argv.index("--system-prompt-file") + 1]).read_text() == module.BATCH_RUBRIC
        data = json.loads(argv[-1])
        assert set(data) == {"cases"}
        assert all(set(c) == {"case_id", "premise", "hypothesis"} for c in data["cases"])
        result = {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "session_id": "synthetic",
            "result": json.dumps(
                {"predictions": [{"case_id": c["case_id"], "verdict": "UNKNOWN"} for c in data["cases"]]}
            ),
        }
        startup = init()
        if native_model is not None:
            startup["model"] = native_model
            result["modelUsage"] = {native_model: {}}
        parser.feed((json.dumps(startup) + "\n").encode())
        parser.feed(
            (
                json.dumps(
                    {"type": "assistant", "message": {"role": "assistant", "model": startup["model"], "content": []}}
                )
                + "\n"
            ).encode()
        )
        parser.feed((json.dumps(result) + "\n").encode())
        parsed = parser.finish(0)
        if tamper == "rubric":
            Path(argv[argv.index("--system-prompt-file") + 1]).write_text("changed")
        elif tamper == "mcp":
            Path(argv[argv.index("--mcp-config") + 1]).write_text("changed")
        elif tamper == "hostile-hook":
            (cwd / "unexpected-hook").touch()
        return ProcessReceipt("CANDIDATE", True, 0, "independent_checks_required", "ab" * 32, "cd" * 32, parsed)

    monkeypatch.setattr(module, "collect_native", injected)
    probe = module.NativeEntailmentProbe(
        BinaryPin(binary, PINNED_BINARY_SHA256), config, tmp_path / "unused.zip", native_model=native_model
    )
    result = probe.run(CORPUS, "calibration")
    if tamper is None:
        assert result.status == "COMPLETE" and len(result.predictions) == 36
        assert result.score.supported_precision is None and result.cash_actual_microusd is None
        assert json.loads(module.native_observation_json(result))["status"] == "COMPLETE"
        assert result.requested_model == native_model
        assert result.model == (native_model or "claude-haiku-4-5-20251001")
        serialized = json.loads(module.native_observation_json(result))
        assert ("requested_model" in serialized) is (native_model is not None)
    else:
        assert result.status == "UNAVAILABLE" and result.score is None and not result.predictions
    assert len(directories) == 1 and all(not p.exists() for p in directories)
    private = tmp_path / "private.json"
    private.write_text("private input")
    with pytest.raises(ValueError, match="entailment_corpus_unconfirmed"):
        probe.run(private, "calibration")


@pytest.mark.parametrize("where", ["startup", "assistant", "usage", "missing-usage", "empty-usage"])
def test_selected_public_probe_refuses_changed_model_transport(where):
    selected, other = "claude-sonnet-5", "claude-opus-5"
    parser = module._PublicFixtureParser(selected)
    startup = {**init(), "model": other if where == "startup" else selected}
    if where == "startup":
        body = startup
    else:
        parser.feed((json.dumps(startup) + "\n").encode())
        body = (
            {"type": "assistant", "message": {"role": "assistant", "model": other, "content": []}}
            if where == "assistant"
            else {"type": "result", "subtype": "success", "is_error": False, "modelUsage": {selected: {}, other: {}}}
        )
        if where == "missing-usage":
            body.pop("modelUsage")
        elif where == "empty-usage":
            body["modelUsage"] = {}
    with pytest.raises(ProtocolRejected, match="model|profile"):
        parser.feed((json.dumps(body) + "\n").encode())
    assert parser.result is None


def test_model_alias_is_refused_before_any_auth_or_process_access(tmp_path):
    with pytest.raises(ValueError, match="unsupported_native_model"):
        module.NativeEntailmentProbe(
            BinaryPin(tmp_path / "absent-binary", PINNED_BINARY_SHA256),
            tmp_path / "absent-auth",
            tmp_path / "absent-archive",
            native_model="opus",
        )


def test_local_single_case_rubric_hash_remains_unchanged_by_shared_rules_refactor():
    from panestria.execution.entailment_probe import RUBRIC_SHA256

    report = Path(__file__).resolve().parents[2] / "evidence/local-entailment-2026-10-16/actual-observations.json"
    assert RUBRIC_SHA256 == json.loads(report.read_text())[0]["rubric_sha256"]
