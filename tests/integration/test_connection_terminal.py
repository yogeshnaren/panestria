"""Actual scoped PG/HTTP/CLI/PTY declaration review; no connector/model/real account."""

import curses
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
from test_ask_tui import terminal
from typer.testing import CliRunner

from connection_support import manifest, proposal
from panestria.api import create_app
from panestria.api.auth import GoalApi
from panestria.api.health import default_readiness_probe
from panestria.api.local_server import server_config
from panestria.api.main import mount_goal_api
from panestria.cli.main import app
from panestria.config import Settings
from panestria.config_local import create_local_token
from panestria.config_profile import ProfileClientSettings
from panestria.kernel.connection_roots import ConnectionRootSession
from panestria.kernel.goals import Actor
from panestria.kernel.policy import PolicyService
from panestria.kernel.uow import UnitOfWork
from panestria.policy.profiles import CertificateStore


@pytest.fixture
def connection_server(r1_migration_task, tmp_path, monkeypatch, record_property):
    f = r1_migration_task
    actor = Actor(f["owner"], f["project"])
    policies = PolicyService(CertificateStore(tmp_path, {}))
    with psycopg.connect(f["dsn"]) as c:
        policies.initialize(UnitOfWork(c), actor, f["task"])

    def forbidden(*a, **k):
        raise AssertionError("declaration review cannot enroll/read a root")

    monkeypatch.setattr(ConnectionRootSession, "enroll", forbidden)
    monkeypatch.setattr(ConnectionRootSession, "snapshot", forbidden)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    token_path = tmp_path / "owner.token"
    create_local_token(token_path)
    token = token_path.read_text().strip()
    config = ProfileClientSettings(
        schema_version=1,
        owner_id=UUID(actor.owner_id),
        project_id=UUID(actor.project_id),
        bind_port=port,
        token_file=token_path,
    )
    path = tmp_path / "owner-client.json"
    path.write_text(config.model_dump_json())
    path.chmod(0o600)
    application = create_app(Settings(database_url=f["dsn"], bind_port=port), default_readiness_probe)
    mount_goal_api(application, GoalApi(token, actor.owner_id, actor.project_id, f["dsn"]))
    state = SimpleNamespace(decisions=0, proposals=0, lose_reply=False)

    @application.middleware("http")
    async def record(request, next_handler):
        decision = request.method == "POST" and request.url.path.endswith("/decision")
        if decision:
            state.decisions += 1
        if request.method == "POST" and request.url.path == "/v2/connections/reviews":
            state.proposals += 1
        result = await next_handler(request)
        if decision and state.lose_reply:
            state.lose_reply = False
            return JSONResponse({"code": "synthetic_lost_reply"}, status_code=503)
        return result

    server = uvicorn.Server(server_config(application))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]})
    thread.start()
    try:
        deadline = time.monotonic() + 8
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline
            time.sleep(0.02)
        record_property(
            "scope",
            "Actual disposable PG/HTTP/CLI/PTY, synthetic declaration/account and postcommit503 fixture; "
            "no live connector/model",
        )
        yield SimpleNamespace(task=f, actor=actor, policies=policies, config=path, token=token, state=state)
    finally:
        server.should_exit = True
        thread.join(timeout=8)
        listener.close()
        assert not thread.is_alive()


def cli(f, *args):
    result = CliRunner().invoke(app, ["connections", *args, "--config", str(f.config)])
    assert result.exit_code == 0, result.output
    assert f.token not in result.output
    return json.loads(result.stdout)


def stage(f, tmp_path):
    scope = cli(f, "scope")
    assert scope["runtime_available"] is False and scope["authority"] == "DECLARATION_ONLY"
    request = {
        "schema_version": 1,
        "task_id": f.task["task"],
        "change": proposal(
            scope["policy_ref"],
            manifest(f.actor.owner_id, f.actor.project_id),
        ).model_dump(mode="json"),
    }
    path = tmp_path / "request.json"
    raw = json.dumps(request)
    path.write_text(raw)
    path.chmod(0o600)
    result = cli(f, "propose", "--request-file", str(path))
    assert result["state"] == "PENDING" and result["manifest"] == request["change"]["manifest"]
    assert path.read_text() == raw
    return result


def review(f, view, *, expected=b"RECORDED APPROVED"):
    with terminal(f.config, entry=("connections", "review"), arguments=("--proposal-id", view["proposal_id"])) as t:
        t.until(b"CONNECTION DECLARATION")
        os.write(t.master, b"ay")
        t.until(b"Read to the end first")
        with psycopg.connect(f.task["dsn"]) as c:
            assert c.execute(
                "SELECT count(*) FROM panestria.connection_grant_decision WHERE review_id=%s", (view["proposal_id"],)
            ).fetchone() == (0,)
        curses.setupterm(term="xterm-256color")
        os.write(t.master, curses.tigetstr("knp") * 8)
        t.until(b"END OF EXACT DECLARATION", after=0)
        os.write(t.master, b"a")
        t.until(b"CONFIRM APPROVE")
        os.write(t.master, b"y")
        t.until(expected)
        os.write(t.master, b"yyyadq")  # Settled/uncertain attempts cannot automatically repeat.
        assert f.token.encode() not in t.transcript


def test_terminal_exact_review_and_fresh_policy_revocation_never_connect(connection_server, tmp_path):
    f = connection_server
    malformed = tmp_path / "invalid.json"
    malformed.write_text('{"schema_version":1,"schema_version":1,"private":"DO_NOT_ECHO_PRIVATE"}')
    malformed.chmod(0o600)
    bad = CliRunner().invoke(
        app, ["connections", "propose", "--config", str(f.config), "--request-file", str(malformed)]
    )
    assert bad.exit_code == 2 and "DO_NOT_ECHO_PRIVATE" not in bad.output and f.state.proposals == 0
    with psycopg.connect(f.task["dsn"]) as c:
        before = c.execute(
            "SELECT state,row_version,lease_epoch FROM panestria.task WHERE id=%s", (f.task["task"],)
        ).fetchone()
    view = stage(f, tmp_path)
    review(f, view)
    current = cli(f, "show", "--grant-id", view["grant_id"])
    assert current["state"] == "DECLARED_ACTIVE" and current["version"] == 1
    assert current["runtime_available"] is False and current["conformance_status"] == "UNVERIFIED"
    with psycopg.connect(f.task["dsn"]) as c:
        assert (
            c.execute(
                "SELECT state,row_version,lease_epoch FROM panestria.task WHERE id=%s", (f.task["task"],)
            ).fetchone()
            == before
        )
        old = f.policies.get(UnitOfWork(c), f.actor)
        update = f.policies.propose(UnitOfWork(c), f.actor, f.task["task"], old.model_copy(update={"version": 2}))
    with psycopg.connect(f.task["dsn"]) as c:
        f.policies.decide(UnitOfWork(c), f.actor, update.review_id, update.effect_digest, "approve")
    with psycopg.connect(f.task["dsn"]) as c:
        f.policies.apply(UnitOfWork(c), f.actor, update.review_id, update.effect_digest)
    assert cli(f, "show", "--grant-id", view["grant_id"])["policy_status"] == "STALE"
    revoke_id = str(uuid4())
    revoked = cli(f, "revoke", "--grant-id", view["grant_id"], "--task-id", f.task["task"], "--proposal-id", revoke_id)
    assert revoked["operation"] == "REVOKE" and revoked["policy_ref"] != view["policy_ref"]
    review(f, revoked)
    assert cli(f, "show", "--grant-id", view["grant_id"])["state"] == "DECLARED_REVOKED"
    assert f.state.decisions == 2 and f.state.proposals == 2
    with psycopg.connect(f.task["dsn"]) as c:
        assert c.execute("SELECT count(*) FROM panestria.worker_invocation").fetchone() == (0,)
        assert c.execute("SELECT count(*) FROM panestria.task_attempt").fetchone() == (0,)


def test_postcommit_error_never_retries_or_optimistically_reports_approval(connection_server, tmp_path):
    f = connection_server
    view = stage(f, tmp_path)
    f.state.lose_reply = True
    review(f, view, expected=b"DECISION UNCONFIRMED")
    assert f.state.decisions == 1
    current = cli(f, "show", "--grant-id", view["grant_id"])
    assert current["version"] == 1 and current["state"] == "DECLARED_ACTIVE" and not current["runtime_available"]
    with psycopg.connect(f.task["dsn"]) as c:
        assert c.execute("SELECT count(*) FROM panestria.connection_grant_decision").fetchone() == (1,)
