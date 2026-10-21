"""Actual PG/crypto/loopback/PTY style editing; synthetic keys, no model or OS-key access."""

import json
import os
import socket
import threading
import time
from types import SimpleNamespace
from uuid import UUID, uuid4

import psycopg
import pytest
import uvicorn
from fastapi.responses import JSONResponse
from pydantic import SecretStr
from test_ask_tui import terminal
from test_profile_vault import profile as profile  # noqa: F401

from panestria.api.activity_server import build_activity_app
from panestria.api.local_server import server_config
from panestria.api.main import mount_profile_api
from panestria.api.routes.profiles import ProfileApi
from panestria.cli.profile_client import ProfileClient
from panestria.cli.tui_client import TerminalUnavailable
from panestria.config import Settings
from panestria.config_activity import ActivitySettings
from panestria.config_local import create_local_token
from panestria.config_profile import ProfileClientSettings
from panestria.contracts.profile import ProfileDocument
from panestria.contracts.style import StyleProfile
from panestria.kernel.uow import UnitOfWork

OTHER = "SYNTHETIC_UNDISPLAYED_PROFILE_FIELD"


@pytest.fixture
def style_server(profile, tmp_path, record_property):  # noqa: F811
    dsn, actor, handle, keys, vault = profile
    token_file = tmp_path / "profile.token"
    create_local_token(token_file)
    token = token_file.read_text().strip()
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    scope = ActivitySettings(
        schema_version=1,
        owner_id=UUID(actor.owner_id),
        project_id=UUID(actor.project_id),
        bind_port=port,
        token_file=token_file,
    )
    settings = Settings(database_url=dsn, bind_port=port).validate_profile()
    app = build_activity_app(scope, settings, token)
    mount_profile_api(app, ProfileApi(vault))
    state = SimpleNamespace(post_count=0, writes=0, lose_reply=False)

    @app.middleware("http")
    async def count(request, next_handler):
        if request.url.path.startswith("/v2/profiles"):
            state.post_count += 1
            if not request.url.path.endswith("/view"):
                state.writes += 1
        result = await next_handler(request)
        if state.lose_reply and request.url.path.startswith("/v2/profiles") and not request.url.path.endswith("/view"):
            state.lose_reply = False
            return JSONResponse({"code": "synthetic_reply_lost"}, status_code=503)
        return result

    config = ProfileClientSettings(
        schema_version=1, owner_id=scope.owner_id, project_id=scope.project_id, bind_port=port, token_file=token_file
    )
    path = tmp_path / "profile-client.json"
    path.write_text(config.model_dump_json())
    path.chmod(0o600)
    server = uvicorn.Server(server_config(app))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]})
    thread.start()
    try:
        deadline = time.monotonic() + 6
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline
            time.sleep(0.02)
        record_property(
            "scope",
            "Actual PG/crypto/HTTP/PTY; synthetic in-memory keys. No inference or actual keyring qualification.",
        )
        yield SimpleNamespace(
            dsn=dsn,
            actor=actor,
            handle=handle,
            keys=keys,
            vault=vault,
            path=path,
            config=config,
            token=token,
            app=app,
            state=state,
        )
    finally:
        server.should_exit = True
        thread.join(timeout=8)
        listener.close()
        assert not thread.is_alive()


def seed(f, *, structured=True):
    text = StyleProfile(detail="concise").model_dump_json() if structured else OTHER
    doc = ProfileDocument(
        fields={"communication": SecretStr(text), "background": SecretStr(OTHER)},
        approved_for_local_context=("background",),
    )
    with psycopg.connect(f.dsn) as c:
        return f.vault.create(UnitOfWork(c), f.actor, f.handle, doc, consent_ref=str(uuid4()))


def test_actual_terminal_reviews_and_corrects_encrypted_style_preserving_other_fields(style_server):
    f = style_server
    seed(f)
    args = ("--profile-id", f.handle.profile_id, "--expected-version", "0", "--owner-review")
    with terminal(f.path, entry=("profile", "style-tui"), arguments=args) as t:
        t.until(b"Panestria encrypted style")
        # Select detail and change concise -> balanced. Edit alone has no write.
        os.write(t.master, b"jjl")
        t.until(b"balanced")
        assert f.state.writes == 0
        os.write(t.master, b"s")
        t.until(b"Press y to save once")
        assert f.state.writes == 0
        os.write(t.master, b"y")
        t.until(b"SAVED row version 1")
        os.write(t.master, b"syy")  # A completed form cannot repeat the write.
        os.write(t.master, b"q")
    assert f.state.writes == 1
    assert (
        OTHER.encode() not in t.transcript
        and f.token.encode() not in t.transcript
        and f.dsn.encode() not in t.transcript
    )
    with psycopg.connect(f.dsn) as c:
        ref, doc = f.vault.read(UnitOfWork(c), f.actor, f.handle.profile_id)
        assert ref.row_version == 1
        assert doc.fields["background"].get_secret_value() == OTHER
        assert doc.approved_for_local_context == ("background",)
        assert StyleProfile.model_validate_json(doc.fields["communication"].get_secret_value()).detail == "balanced"
        for table in ("profile_revision", "profile_event", "memory_source", "context_pack"):
            assert all(OTHER not in row[0] for row in c.execute(f"SELECT to_jsonb(t)::text FROM panestria.{table} t"))
        assert c.execute(
            "SELECT count(*) FROM panestria.ask_request WHERE project_id=%s", (f.actor.project_id,)
        ).fetchone() == (0,)


def test_terminal_create_needs_explicit_save_and_local_context_choice(style_server):
    f = style_server
    args = ("--profile-id", f.handle.profile_id, "--key-id", f.handle.key_id, "--owner-review")
    with terminal(f.path, entry=("profile", "style-tui"), arguments=args) as t:
        t.until(b"Panestria encrypted style")
        os.write(t.master, b"s")
        t.until(b"Press y to save once")
        os.write(t.master, b"q")  # Cancel the review and quit; creates nothing.
        os.write(t.master, b"q")
    assert f.state.writes == 0 and not f.keys.loads
    with terminal(f.path, entry=("profile", "style-tui"), arguments=args) as t:
        t.until(b"Panestria encrypted style")
        os.write(t.master, b"jjjjjl")
        t.until(b"YES")
        os.write(t.master, b"sy")
        t.until(b"SAVED row version 0")
        os.write(t.master, b"q")
    assert f.state.writes == 1
    with psycopg.connect(f.dsn) as c:
        _, doc = f.vault.read(UnitOfWork(c), f.actor, f.handle.profile_id)
        assert set(doc.fields) == {"communication"}
        assert doc.approved_for_local_context == ("communication",)


def test_scoped_client_refuses_stale_freeform_disabled_and_wrong_scope_without_overwrite(style_server):
    f = style_server
    seed(f)
    client = ProfileClient(f.path)
    source = client.source(f.handle.profile_id, 0)
    receipt = client.save(source, StyleProfile(detail="detailed"), True)
    assert receipt.row_version == 1
    with pytest.raises(TerminalUnavailable, match="version_conflict"):
        client.save(source, StyleProfile(), False)
    assert f.state.writes == 2  # one confirmed, one exact-version refusal; no retry.
    f.vault.enabled = False
    f.keys.loads.clear()
    with pytest.raises(TerminalUnavailable, match="profile_disabled"):
        client.source(f.handle.profile_id, 1)
    assert not f.keys.loads
    f.vault.enabled = True
    wrong = f.config.model_copy(update={"project_id": uuid4()})
    f.path.write_text(wrong.model_dump_json())
    before = f.state.post_count
    with pytest.raises(TerminalUnavailable, match="server_scope_mismatch"):
        ProfileClient(f.path).source(f.handle.profile_id, 1)
    assert f.state.post_count == before and not f.keys.loads
    f.path.write_text(f.config.model_dump_json())
    with psycopg.connect(f.dsn) as c:
        doc = ProfileDocument(fields={"communication": SecretStr(OTHER)})
        f.vault.revise(UnitOfWork(c), f.actor, f.handle, 1, doc, consent_ref=str(uuid4()))
    with pytest.raises(TerminalUnavailable, match="structured_style_not_available"):
        client.source(f.handle.profile_id, 2)
    assert f.state.writes == 2


def test_lost_save_reply_keeps_one_canonical_revision_and_no_terminal_retry(style_server):
    f = style_server
    f.state.lose_reply = True
    args = ("--profile-id", f.handle.profile_id, "--key-id", f.handle.key_id, "--owner-review")
    with terminal(f.path, entry=("profile", "style-tui"), arguments=args) as t:
        t.until(b"Panestria encrypted style")
        os.write(t.master, b"sy")
        t.until(b"SAVE UNCONFIRMED")
        os.write(t.master, b"syysy")
        os.write(t.master, b"q")
    assert f.state.writes == 1
    with psycopg.connect(f.dsn) as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.profile_revision WHERE profile_id=%s", (f.handle.profile_id,)
        ).fetchone() == (1,)
    source = ProfileClient(f.path).source(f.handle.profile_id, 0)
    assert source.row_version == 0 and source.style == StyleProfile()


def test_profile_client_requires_private_loopback_scope_and_existing_token(tmp_path):
    from panestria.config_local import LocalApplicationRejected
    from panestria.config_profile import load_profile_client

    token = tmp_path / "existing.token"
    create_local_token(token)
    config = tmp_path / "client.json"
    original = ProfileClientSettings(schema_version=1, owner_id=uuid4(), project_id=uuid4(), token_file=token)
    config.write_text(original.model_dump_json())
    config.chmod(0o600)
    assert load_profile_client(config)[0] == original
    for update in ({"bind_host": "192.0.2.1"}, {"schema_version": True}, {"enable_profiles": True}):
        config.write_text(json.dumps({**original.model_dump(mode="json"), **update}))
        with pytest.raises(LocalApplicationRejected, match="invalid_profile_client_configuration"):
            load_profile_client(config)
    config.write_text(original.model_dump_json())
    token.chmod(0o644)
    with pytest.raises(LocalApplicationRejected, match="local_file_must_be_private"):
        load_profile_client(config)
    token.chmod(0o600)
    linked = tmp_path / "linked.json"
    linked.symlink_to(config)
    with pytest.raises(LocalApplicationRejected, match="profile_client_path_invalid"):
        load_profile_client(linked)
