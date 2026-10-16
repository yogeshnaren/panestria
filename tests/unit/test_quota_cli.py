"""Bounded loopback client, held file handling and hostile-response redaction."""

import json
import os
from uuid import uuid4

import httpx2 as httpx
import pytest
from typer.testing import CliRunner

from panestria.cli import quota
from panestria.cli.main import app
from quota_support import observation

SENTINEL = "SYNTHETIC_TOKEN_AND_HOSTILE_ERROR_CONTENT"


def view(body):
    return {
        "observation": body.model_dump(mode="json"),
        "freshness": "FRESH",
        "confidence": "REPORTED",
        "effective_remaining": body.remaining,
        "authority": "OBSERVATION_ONLY",
    }


@pytest.fixture
def files(tmp_path):
    token = tmp_path / "token"
    token.write_text(SENTINEL)
    token.chmod(0o600)
    value = observation()
    payload = {"schema_version": 1, "task_id": str(uuid4()), "observation": value.model_dump(mode="json")}
    source = tmp_path / "quota.json"
    source.write_text(json.dumps(payload))
    source.chmod(0o600)
    return token, source, value


def invoke(files, command=None):
    token, source, _ = files
    return CliRunner().invoke(
        app, ["quota", *(command or ["report", "--input-file", str(source)]), "--token-file", str(token)]
    )


def transport(monkeypatch, handler):
    original = httpx.Client

    def client(**options):
        assert options == {"trust_env": False, "follow_redirects": False, "timeout": 5}
        return original(**options, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(quota.httpx, "Client", client)


def test_exact_report_and_show_use_shared_owner_contract_and_sanitized_output(files, monkeypatch):
    _, _, value = files
    seen = []

    def handle(request):
        seen.append(request)
        assert request.headers["authorization"] == "Bearer " + SENTINEL
        return httpx.Response(200, json={**view(value), "untrusted_extra": SENTINEL})

    transport(monkeypatch, handle)
    for command in (None, ["show", value.observation_id]):
        result = invoke(files, command)
        assert result.exit_code == 0 and SENTINEL not in result.output
        assert json.loads(result.output)["observation"] == value.model_dump(mode="json")
    assert [r.method for r in seen] == ["POST", "GET"]
    assert str(seen[0].url) == "http://127.0.0.1:8766/v2/quota/observations"
    assert json.loads(seen[0].content)["observation"] == value.model_dump(mode="json")


@pytest.mark.parametrize(
    "origin",
    [
        "https://127.0.0.1:8766",
        "http://provider.example:8766",
        "http://localhost:8766",
        "http://192.0.2.1:8766",
        "http://127.0.0.1:8766/redirect",
        "http://user:pass@127.0.0.1:8766",
        "http://127.0.0.1:8766?x=1",
    ],
)
def test_nonliteral_or_nonloopback_origins_never_open_client_or_send_token(files, monkeypatch, origin):
    def forbidden(**_):
        raise AssertionError("client must not open")

    monkeypatch.setattr(quota.httpx, "Client", forbidden)
    token, source, _ = files
    result = CliRunner().invoke(
        app, ["quota", "report", "--input-file", str(source), "--token-file", str(token), "--base-url", origin]
    )
    assert result.exit_code == 2 and result.output.strip() == "quota_input_or_api_unavailable"
    assert SENTINEL not in result.output


@pytest.mark.parametrize(
    "kind", ["symlink", "parent_symlink", "hardlink", "public", "fifo", "directory", "oversize", "control"]
)
def test_unsafe_token_sources_fail_before_http_and_never_echo_content(files, monkeypatch, kind):
    token, _, _ = files
    if kind == "symlink":
        real = token.with_name("real-token")
        token.rename(real)
        token.symlink_to(real)
    elif kind == "parent_symlink":
        link = token.parent / "alias"
        link.symlink_to(token.parent, target_is_directory=True)
        token = link / token.name
    elif kind == "hardlink":
        os.link(token, token.with_name("alias"))
    elif kind == "public":
        token.chmod(0o644)
    elif kind == "fifo":
        token.unlink()
        os.mkfifo(token, mode=0o600)
    elif kind == "directory":
        token.unlink()
        token.mkdir()
    elif kind == "oversize":
        token.write_text(SENTINEL * 20)
    else:
        token.write_text(SENTINEL + "\r\nINJECTED: true")

    def forbidden(**_):
        raise AssertionError("client must not open")

    monkeypatch.setattr(quota.httpx, "Client", forbidden)
    result = invoke((token, *files[1:]))
    assert result.exit_code == 2 and result.output.strip() == "quota_input_or_api_unavailable"


def test_changed_held_token_is_denied_before_sending(files, monkeypatch):
    token, _, _ = files
    original = os.read

    def changed(descriptor, size):
        data = original(descriptor, size)
        if size == 257:
            token.write_text(SENTINEL + "changed")
        return data

    monkeypatch.setattr(quota.os, "read", changed)
    result = invoke(files)
    assert result.exit_code == 2 and SENTINEL not in result.output


@pytest.mark.parametrize(
    "kind", ["error", "redirect", "large", "malformed", "mismatch", "bad_type", "promoted_estimate", "stale_known"]
)
def test_hostile_api_results_cannot_echo_credentials_or_promote_unknown(files, monkeypatch, kind):
    _, _, value = files

    def handle(_):
        if kind == "error":
            return httpx.Response(401, text=SENTINEL)
        if kind == "redirect":
            return httpx.Response(302, headers={"Location": "https://provider.example/"}, text=SENTINEL)
        if kind == "large":
            return httpx.Response(200, content=(SENTINEL * 1000).encode())
        if kind == "malformed":
            return httpx.Response(200, text=SENTINEL)
        body = view(value)
        if kind == "mismatch":
            body["observation"]["observation_id"] = str(uuid4())
        elif kind == "bad_type":
            body["freshness"] = {"untrusted": SENTINEL}
        elif kind == "promoted_estimate":
            body["observation"].update(source="ESTIMATED", source_sha256="ab" * 32)
        else:
            body["freshness"] = "STALE"
        return httpx.Response(200, json=body)

    transport(monkeypatch, handle)
    result = invoke(files)
    assert result.exit_code == 2 and result.output.strip() == "quota_input_or_api_unavailable"


def test_current_preserves_empty_unknown_and_denies_mixed_scope_or_duplicate_sources(files, monkeypatch):
    _, _, value = files
    command = ["current", "--account-ref", value.scope.account_ref, "--window", value.scope.window_ref]
    cases = [[], [view(value)], [view(value), view(value)], [view(observation())]]
    for lanes in cases:
        transport(
            monkeypatch,
            lambda _, lanes=lanes: httpx.Response(200, json={"lanes": lanes, "authority": "OBSERVATION_ONLY"}),
        )
        # Restore the genuine Client between independent transports.
        result = invoke(files, command)
        if len(lanes) < 2 and (not lanes or lanes[0]["observation"]["scope"] == value.scope.model_dump()):
            assert result.exit_code == 0 and json.loads(result.output)["lanes"] == lanes
        else:
            assert result.exit_code == 2
        monkeypatch.undo()


def test_source_forgery_and_large_input_fail_before_reading_token(files, monkeypatch):
    _, source, value = files
    payload = json.loads(source.read_text())
    payload["observation"].update(source="PROVIDER_REPORTED", source_sha256="ab" * 32)
    source.write_text(json.dumps(payload))

    def forbidden(*_, **__):
        raise AssertionError("no token or HTTP")

    original = quota._read

    def input_only(path, **options):
        if options["private"]:
            forbidden()
        return original(path, **options)

    monkeypatch.setattr(quota, "_read", input_only)
    assert invoke(files).exit_code == 2
    source.write_text("x" * 4097)
    assert invoke(files).exit_code == 2
