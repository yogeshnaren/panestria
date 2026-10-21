"""Actual scoped encrypted profile HTTP/PTY; explicitly synthetic keys/model/capacity."""

import asyncio
import hashlib
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx2 as httpx
import psycopg
import pytest
from test_ask_kernel import initialize
from test_ask_tui import terminal
from test_local_provider import valid_frames
from test_profile_style_terminal import style_server as style_server  # noqa: F401
from test_profile_vault import profile as profile  # noqa: F401

from panestria.api.main import mount_ask_api
from panestria.api.routes.ask import AskApi
from panestria.cli.profile_ask import ProfileAskClient
from panestria.cli.profile_client import ProfileClient, StyleSource
from panestria.cli.tui_client import TerminalUnavailable
from panestria.contracts.profile_context import ProfileSelectionRequest
from panestria.contracts.style import StyleProfile
from panestria.inference.local import LocalProvider
from panestria.resources.hardware import HardwareProbe, ProbeUnavailable

ROOT = Path(__file__).resolve().parents[2]
ANSWER = "SYNTHETIC_PROFILE_ONLY_ANSWER"


@pytest.fixture
def profile_terminal(style_server, r1_task, tmp_path):  # noqa: F811
    f = style_server
    initialize(r1_task, tmp_path)
    ProfileClient(f.path).save(
        StyleSource(f.handle.profile_id, f.handle.key_id, None), StyleProfile(detail="concise"), True
    )
    selection = ProfileSelectionRequest(
        profile_id=f.handle.profile_id,
        expected_row_version=0,
        purpose="STRUCTURED_RESPONSE_STYLE",
        fields=("communication",),
        destination="OFFLINE_LOCAL_MODEL",
    )
    path = tmp_path / "selection.json"
    path.write_text(selection.model_dump_json())
    path.chmod(0o600)
    state = SimpleNamespace(calls=[], slow=False)

    async def model(request):
        if request.url.path == "/api/tags":
            from test_local_provider import MODEL, MODEL_DIGEST

            return httpx.Response(200, json={"models": [{"name": MODEL, "digest": MODEL_DIGEST}]})
        state.calls.append(json.loads(request.content))
        if state.slow:
            await asyncio.sleep(8)
        frames = valid_frames()
        frames[0]["response"] = ANSWER
        return httpx.Response(200, content="\n".join(json.dumps(v) for v in frames))

    probe = HardwareProbe(ROOT / "docs/specification/attachments/agentos-skills-v0.1.0.zip")
    mount_ask_api(
        f.app,
        AskApi(
            LocalProvider(Path("/synthetic"), transport=httpx.MockTransport(model)),
            lambda: probe.collect(preset="omen-8gb"),
        ),
    )
    return f, path, state


def args(path):
    return ("--selection", str(path), "--restricted-offline")


def test_actual_profile_terminal_uses_pinned_style_and_omits_response_fingerprints(profile_terminal):
    f, selection, state = profile_terminal
    with terminal(f.path, entry=("profile", "ask-tui"), arguments=args(selection)) as t:
        t.until(b"CONNECTED")
        t.until(f.handle.profile_id.encode(), after=0)
        os.write(t.master, b"nExplain a synthetic fact\r")
        t.until(b"COMPLETED")
        t.until(ANSWER.encode(), after=0)
        os.write(t.master, b"q")
    assert len(state.calls) == 1
    prompt = json.loads(state.calls[0]["prompt"])
    assert prompt["untrusted_owner_profile"]["structured_style"]["preferences"]["detail"] == "concise"
    assert "assistant_charter" in prompt
    with psycopg.connect(f.dsn) as c:
        request_id, mode, digest = c.execute(
            "SELECT id::text,response_digest_mode,response_sha256 FROM panestria.ask_request WHERE project_id=%s",
            (f.actor.project_id,),
        ).fetchone()
        assert mode == "OMITTED_RESTRICTED_PROFILE" and digest is None
        assert ANSWER not in str(
            c.execute("SELECT metadata FROM panestria.ask_request WHERE id=%s", (request_id,)).fetchone()
        )
    client = ProfileAskClient(f.path, selection)
    receipt = client.receipt(request_id)
    assert "text" not in receipt and len(state.calls) == 1
    for update in (
        {"response_sha256": hashlib.sha256(ANSWER.encode()).hexdigest()},
        {"profile_context": {**receipt["profile_context"], "row_version": 1}},
    ):
        with pytest.raises(TerminalUnavailable, match="profile_receipt_unconfirmed"):
            client.profile_receipt({**receipt, **update}, request_id)
    assert f.token.encode() not in t.transcript and f.dsn.encode() not in t.transcript


def test_profile_terminal_cancellation_then_resource_denial_is_visible_without_new_model(profile_terminal):
    f, selection, state = profile_terminal
    state.slow = True
    with terminal(f.path, entry=("profile", "ask-tui"), arguments=args(selection)) as t:
        t.until(b"CONNECTED")
        os.write(t.master, b"nSynthetic slow question\r")
        deadline = time.monotonic() + 3
        while not state.calls:
            assert time.monotonic() < deadline
            time.sleep(0.02)
        os.write(t.master, b"c")
        t.until(b"CANCELLED")
        os.write(t.master, b"q")
    state.slow = False

    def denied():
        raise ProbeUnavailable("synthetic_capacity_unavailable")

    f.app.state.ask_api.probe = denied
    with terminal(f.path, entry=("profile", "ask-tui"), arguments=args(selection)) as t:
        t.until(b"CONNECTED")
        os.write(t.master, b"nSynthetic pressure question\r")
        t.until(b"database_or_resource_unavailable")
        os.write(t.master, b"r")
        t.until(b"UNAVAILABLE")
        os.write(t.master, b"q")
    assert len(state.calls) == 1
    with psycopg.connect(f.dsn) as c:
        assert {
            r[0]
            for r in c.execute("SELECT state FROM panestria.ask_request WHERE project_id=%s", (f.actor.project_id,))
        } == {"CANCELLED", "UNAVAILABLE"}


def test_profile_mode_status_is_metadata_only_and_disabled_stale_selection_never_falls_back(profile_terminal):
    f, selection, state = profile_terminal
    client = ProfileAskClient(f.path, selection)
    f.keys.loads.clear()
    assert client.status()["readiness"] == "KEY_MODEL_CHECKED_PER_REQUEST"
    assert not f.keys.loads and not state.calls
    f.vault.enabled = False
    with pytest.raises(TerminalUnavailable, match="profile_disabled"):
        client.ask(str(uuid4()), "Must not dispatch")
    assert not f.keys.loads and not state.calls
    f.vault.enabled = True
    owner_client = ProfileClient(f.path)
    source = owner_client.source(f.handle.profile_id, 0)
    owner_client.save(source, StyleProfile(detail="detailed"), True)
    with pytest.raises(TerminalUnavailable, match="version_conflict"):
        client.ask(str(uuid4()), "Must not silently use corrected selection")
    assert not state.calls
    with psycopg.connect(f.dsn) as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.ask_request WHERE project_id=%s", (f.actor.project_id,)
        ).fetchone() == (0,)


def test_lost_profile_ask_reply_and_transient_receipt_error_keep_original_request(profile_terminal):
    from panestria.cli.tui import AskTerminal

    f, selection, state = profile_terminal
    client = ProfileAskClient(f.path, selection)
    original = client._request
    fault = {"receipt": False}

    def lost(method, route, body=None):
        if method == "GET" and route.startswith("/v1/ask/") and fault["receipt"]:
            fault["receipt"] = False
            raise TerminalUnavailable("database_unavailable", clear=True)
        result = original(method, route, body)
        if method == "POST" and route == "/v2/ask":
            raise TerminalUnavailable("connection_unconfirmed_check_receipt", clear=True)
        return result

    client._request = lost
    terminal_view = AskTerminal(client)

    def drained():
        deadline = time.monotonic() + 4
        while terminal_view.busy:
            terminal_view.drain()
            assert time.monotonic() < deadline
            time.sleep(0.01)

    try:
        terminal_view.refresh()
        drained()
        terminal_view.view.question = "Synthetic lost answer reply"
        terminal_view.submit()
        identity = terminal_view.view.request_id
        drained()
        assert identity and terminal_view.view.request_id == identity and not terminal_view.view.answer
        fault["receipt"] = True
        terminal_view.refresh()
        drained()
        assert terminal_view.view.request_id == identity
        terminal_view.refresh()
        drained()
        assert terminal_view.view.state == "COMPLETED" and not terminal_view.view.answer
        assert len(state.calls) == 1
    finally:
        terminal_view.close()
