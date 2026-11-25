"""Goal events stream over a real socket under the product server, past the request deadline.

The hand-rolled R0 server buffered every response and reported a disconnect
right after the body, so an event stream could not work through it. These
tests open an actual HTTP connection to the goal API under uvicorn.
"""

from __future__ import annotations

import socket
import time

import psycopg

from panestria.api.auth import GoalApi
from panestria.api.main import create_app, mount_goal_api
from panestria.api.serving import TransportLimits
from panestria.config import Settings
from panestria.kernel.repositories.tasks import append_event
from panestria.kernel.uow import UnitOfWork
from serving_support import served

TOKEN = "synthetic-stream-token-0123456789"


def _app(task: dict[str, str]):  # type: ignore[no-untyped-def]
    application = create_app(Settings(database_url=task["dsn"]), lambda _deadline: None)  # type: ignore[arg-type]
    mount_goal_api(application, GoalApi(TOKEN, task["owner"], task["project"], task["dsn"]))
    # A short body deadline: the stream must outlive it, because it is not a body wait.
    application.add_middleware(TransportLimits, deadline_seconds=0.3)
    return application


def _append(task: dict[str, str], kind: str) -> int:
    with psycopg.connect(task["dsn"]) as connection:
        seq = append_event(
            UnitOfWork(connection),
            goal_id=task["goal"],
            task_id=task["task"],
            actor=task["owner"],
            kind=kind,
            payload={"schema_version": 1},
        )
        connection.commit()
    return int(seq)


def _read_until(sock: socket.socket, needle: bytes, seconds: float) -> bytes:
    received = b""
    deadline = time.monotonic() + seconds
    while needle not in received and time.monotonic() < deadline:
        try:
            chunk = sock.recv(65536)
        except TimeoutError:
            continue
        if not chunk:
            break
        received += chunk
    return received


def test_events_stream_incrementally_and_outlive_the_body_deadline(r1_task: dict[str, str]) -> None:
    first = _append(r1_task, "test.stream.first")
    with served(_app(r1_task)) as port, socket.create_connection(("127.0.0.1", port), timeout=0.5) as sock:
        sock.sendall(
            f"GET /v1/goals/{r1_task['goal']}/events HTTP/1.1\r\nHost: 127.0.0.1\r\n"
            f"Authorization: Bearer {TOKEN}\r\nAccept: text/event-stream\r\n\r\n".encode()
        )
        opened = _read_until(sock, b"test.stream.first", 5)
        assert opened.startswith(b"HTTP/1.1 200 ")
        assert b"content-type: text/event-stream" in opened.lower()
        assert f"id: {first}".encode() in opened
        # Well past the 0.3 s body deadline, on the same open connection.
        time.sleep(1.0)
        second = _append(r1_task, "test.stream.second")
        later = _read_until(sock, b"test.stream.second", 5)
        assert f"id: {second}".encode() in later and b"test.stream.second" in later


def test_an_unauthenticated_stream_is_refused(r1_task: dict[str, str]) -> None:
    with served(_app(r1_task)) as port, socket.create_connection(("127.0.0.1", port), timeout=2) as sock:
        sock.sendall(
            f"GET /v1/goals/{r1_task['goal']}/events HTTP/1.1\r\nHost: 127.0.0.1\r\n"
            "Accept: text/event-stream\r\nConnection: close\r\n\r\n".encode()
        )
        reply = _read_until(sock, b"unauthorized", 5)
    assert reply.startswith(b"HTTP/1.1 401 ") and b"text/event-stream" not in reply.lower()
