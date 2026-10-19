"""Actual PTY/keyboard and scoped PG/HTTP; explicitly fixture-only model output."""

import asyncio
import curses
import fcntl
import json
import os
import pty
import select
import signal
import socket
import struct
import subprocess
import termios
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx2 as httpx
import psycopg
import pytest
import uvicorn
from fastapi.responses import StreamingResponse
from test_local_server import configured  # noqa: F401 -- scoped canonical app fixture
from typer.testing import CliRunner

from panestria.api import local_server
from panestria.cli import tui_client
from panestria.cli.main import app as cli
from panestria.cli.tui import AskTerminal, TerminalView, literal, wrapped
from panestria.cli.tui_client import LocalAskClient, TerminalUnavailable
from panestria.inference.runtime import MODEL, MODEL_DIGEST

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def terminal_server(configured, tmp_path, record_property):  # noqa: F811
    config, token, settings, old, _ = configured
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    config = config.model_copy(update={"bind_port": listener.getsockname()[1]})
    path = tmp_path / "tui.json"
    path.write_text(config.model_dump_json())
    path.chmod(0o600)
    old.state.health.shutdown()
    server_app = local_server.build_local_app(config, settings, token)
    state = SimpleNamespace(
        started=threading.Event(),
        delay=False,
        slow_status=False,
        status_reads=0,
        calls=0,
        requests=[],
        text="SYNTHETIC TUI ANSWER",
    )

    @server_app.middleware("http")
    async def slow_status(request, call_next):
        if request.url.path == "/v1/local/status":
            state.status_reads += 1
        if state.slow_status and request.url.path == "/v1/local/status":

            async def drip():
                yield b'{"synthetic":'
                await asyncio.sleep(1)
                yield b"true}"

            return StreamingResponse(drip(), media_type="application/json")
        return await call_next(request)

    async def model(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": MODEL, "digest": MODEL_DIGEST}]})
        state.calls += 1
        state.requests.append(json.loads(request.content))
        state.started.set()
        if state.delay:
            await asyncio.sleep(8)
        return httpx.Response(
            200,
            content="\n".join(
                json.dumps(frame)
                for frame in [
                    {"model": MODEL, "response": state.text, "done": False},
                    {
                        "model": MODEL,
                        "response": "",
                        "done": True,
                        "done_reason": "stop",
                        "prompt_eval_count": 12,
                        "eval_count": 2,
                    },
                ]
            ),
        )

    server_app.state.ask_api.provider.transport = httpx.MockTransport(model)
    server = uvicorn.Server(local_server.server_config(server_app))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]})
    thread.start()
    try:
        deadline = time.monotonic() + 8
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline
            time.sleep(0.02)
        record_property("scope", "Actual PTY/PG/HTTP with labeled MODEL_FIXTURE; not live inference or release proof")
        yield SimpleNamespace(
            config=path,
            settings=config,
            app=server_app,
            state=state,
            dsn=settings.database_url.get_secret_value(),
            token=token,
        )
    finally:
        server.should_exit = True
        thread.join(timeout=8)
        listener.close()
        assert not thread.is_alive()


@contextmanager
def terminal(path):
    master, slave = pty.openpty()
    before = termios.tcgetattr(slave)
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 26, 110, 0, 0))
    process = subprocess.Popen(
        [str(ROOT / ".venv/bin/python"), "-m", "panestria.cli.main", "tui", "--config", str(path)],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        cwd=ROOT,
        env={**os.environ, "TERM": "xterm-256color", "PYTHONUTF8": "1"},
    )
    transcript = bytearray()

    def until(value, timeout=6, *, after=None):
        deadline = time.monotonic() + timeout
        start = len(transcript) if after is None else after
        while value not in transcript[start:]:
            assert process.poll() is None and time.monotonic() < deadline, bytes(transcript[-3000:])
            if select.select([master], [], [], 0.05)[0]:
                transcript.extend(os.read(master, 65536))
        return bytes(transcript)

    try:
        yield SimpleNamespace(process=process, master=master, slave=slave, until=until, transcript=transcript)
        process.wait(timeout=4)
        assert process.returncode == 0
        after = termios.tcgetattr(slave)
        assert after == before, "Terminal attributes were not restored"
    finally:
        if process.poll() is None:
            process.terminate()  # Only this fixture's exact child; no server/model/owner service.
            process.wait(timeout=4)
        os.close(master)
        os.close(slave)


def test_actual_terminal_question_answer_resize_quit_and_terminal_restoration(terminal_server):
    f = terminal_server
    f.state.text += " \x1b]52;c;SYNTHETIC_CLIPBOARD\x07 \u202eread literally 中文"
    with terminal(f.config) as t:
        t.until(b"CONNECTED")
        os.write(t.master, "nPUBLIC question 中文".encode())
        baseline = f.state.status_reads
        curses.setupterm(term="xterm-256color")
        os.write(t.master, curses.tigetstr("kf5"))
        deadline = time.monotonic() + 1.5
        while f.state.status_reads == baseline:
            assert time.monotonic() < deadline, "F5 did not refresh while editing"
            time.sleep(0.01)
        assert f.state.calls == 0  # Refresh must not submit or discard the draft.
        response_start = len(t.transcript)
        os.write(t.master, b"\r")
        t.until(b"COMPLETED")
        # A PTY read can split a curses refresh between the status and answer.
        # Also accept answer bytes already read with the status from this response.
        t.until(b"SYNTHETIC TUI ANSWER", after=response_start)
        assert f.state.calls == 1
        assert b"\x1b]52" not in t.transcript and "\u202e".encode() not in t.transcript
        assert f.token.encode() not in t.transcript and f.dsn.encode() not in t.transcript
        fcntl.ioctl(t.slave, termios.TIOCSWINSZ, struct.pack("HHHH", 12, 50, 0, 0))
        t.process.send_signal(signal.SIGWINCH)
        t.until(b"Resize to at least")
        fcntl.ioctl(t.slave, termios.TIOCSWINSZ, struct.pack("HHHH", 26, 110, 0, 0))
        t.process.send_signal(signal.SIGWINCH)
        t.until(b"SYNTHETIC TUI ANSWER")
        os.write(t.master, b"q")
    assert f.state.requests[0]["stream"] is True
    with psycopg.connect(f.dsn) as c:
        assert c.execute(
            "SELECT state FROM panestria.ask_request WHERE project_id=%s", (f.settings.project_id,)
        ).fetchall() == [("COMPLETED",)]


def test_actual_terminal_cancellation_is_canonical_and_reuse_is_explicit(terminal_server):
    f = terminal_server
    f.state.delay = True
    with terminal(f.config) as t:
        t.until(b"CONNECTED")
        os.write(t.master, b"nPUBLIC delayed question\r")
        assert f.state.started.wait(5)
        os.write(t.master, b"c")
        t.until(b"CANCELLED")
        with psycopg.connect(f.dsn) as c:
            assert c.execute(
                "SELECT state FROM panestria.ask_request WHERE project_id=%s", (f.settings.project_id,)
            ).fetchall() == [("CANCELLED",)]
        f.state.delay = False
        os.write(t.master, b"nPUBLIC fresh question\r")
        t.until(b"COMPLETED")
        os.write(t.master, b"q")
    assert f.state.calls == 2


def test_actual_terminal_authentication_loss_clears_view(terminal_server):
    f = terminal_server
    with terminal(f.config) as t:
        t.until(b"CONNECTED")
        os.write(t.master, b"nPUBLIC initial question\r")
        t.until(b"COMPLETED")
        # Inject changed expected bearer token into this disposable fixture app.
        # The actual API authorization then returns401; no owner credential changes.
        object.__setattr__(f.app.state.goal_api, "token", "synthetic-replacement-local-token")
        os.write(t.master, b"r")
        t.until(b"authentication_lost")
        os.write(t.master, b"q")
    assert f.state.calls == 1


def test_unconfirmed_post_is_not_replayed_and_receipt_recovers_actual_commit(terminal_server, monkeypatch):
    f = terminal_server
    client = LocalAskClient(f.config)
    terminal_app = AskTerminal(client)
    terminal_app.view.connected, terminal_app.view.question = True, "PUBLIC lost acknowledgement"
    request = client._request

    def lost(method, route, body=None):
        result = request(method, route, body)
        if route == "/v1/ask":
            raise TerminalUnavailable("SYNTHETIC_COMMITTED_RESPONSE_LOST")
        return result

    monkeypatch.setattr(client, "_request", lost)
    terminal_app.submit()
    deadline = time.monotonic() + 5
    while "ask" in terminal_app.busy:
        assert time.monotonic() < deadline
        terminal_app.drain()
        time.sleep(0.02)
    identity = terminal_app.view.request_id
    terminal_app.submit()
    assert identity == terminal_app.view.request_id and f.state.calls == 1
    observed = client.receipt(identity)
    assert observed["state"] == "COMPLETED" and "text" not in observed
    terminal_app.events.put((terminal_app.generation, "receipt", observed))
    terminal_app.drain()
    assert terminal_app.view.state == "COMPLETED" and not terminal_app.view.answer
    assert client.cancel(identity)["state"] == "COMPLETED"  # Cannot undo completed inference.
    terminal_app.close()


def test_wrong_server_scope_refuses_question_before_disclosure(terminal_server):
    f = terminal_server
    client = LocalAskClient(f.config)
    client.config = client.config.model_copy(update={"project_id": uuid4()})
    with pytest.raises(TerminalUnavailable, match="server_scope_mismatch") as error:
        client.ask(str(uuid4()), "PUBLIC wrong project must not dispatch")
    assert error.value.clear and not error.value.uncertain and f.state.calls == 0


def test_total_control_deadline_includes_actual_http_body_read(terminal_server, monkeypatch):
    f = terminal_server
    f.state.slow_status = True
    monkeypatch.setattr(tui_client, "CONTROL_SECONDS", 0.1)
    started = time.monotonic()
    with pytest.raises(TerminalUnavailable, match="connection_unconfirmed_check_receipt"):
        LocalAskClient(f.config).status()
    assert time.monotonic() - started < 0.8 and f.state.calls == 0


def test_late_generation_and_auth_callbacks_cannot_restore_or_regress_terminal_view(tmp_path):
    from test_local_server import configuration

    config, _ = configuration(tmp_path)
    view = AskTerminal(LocalAskClient(config))
    view.view = TerminalView(
        connected=True,
        question="SYNTHETIC_PRIVATE_QUESTION",
        answer="SYNTHETIC_PRIVATE_ANSWER",
        request_id=str(uuid4()),
        state="COMPLETED",
    )
    assert "SYNTHETIC_PRIVATE" not in repr(view.view)
    view.events.put((view.generation, "receipt", {"state": "RUNNING"}))
    view.drain()
    assert view.view.state == "COMPLETED"
    generation = view.generation
    view.events.put((generation, "status", TerminalUnavailable("authentication_lost", clear=True)))
    view.events.put((generation, "ask", {"state": "COMPLETED", "text": "SYNTHETIC_LATE_ANSWER"}))
    view.drain()
    assert not view.view.answer and not view.view.question and not view.view.request_id
    assert not view.view.connected
    view.close()
    view.events.put((view.generation, "ask", {"state": "COMPLETED", "text": "SYNTHETIC_LATE_ANSWER"}))
    view.drain()
    assert not view.view.answer


def test_terminal_text_is_inert_and_headless_cli_does_not_start_or_disclose():
    text = "中文\x1b]52;c;clipboard\x07\r\u202e literal\nnext"
    assert "\x1b" not in literal(text) and "\u202e" not in literal(text) and "中文" in literal(text)
    assert "".join(wrapped("中文café", 4)) == "中文café"
    result = CliRunner().invoke(cli, ["tui", "--config", "/SYNTHETIC_PRIVATE_PATH"])
    assert result.exit_code == 1 and "interactive_terminal_required" in result.output
    assert "SYNTHETIC_PRIVATE_PATH" not in result.output
