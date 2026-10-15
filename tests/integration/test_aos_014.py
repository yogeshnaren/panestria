"""Real PostgreSQL canonical replay ordering and integrity independent of process state."""

from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import psycopg
import pytest
from starlette.requests import Request
from test_aos_009 import _client

from panestria.api.event_stream import stream_events
from panestria.kernel.errors import KernelDenied
from panestria.kernel.event_replay import EventReplay, parse_cursor
from panestria.kernel.goals import Actor
from panestria.kernel.repositories.tasks import append_event
from panestria.kernel.uow import UnitOfWork


def test_cursor_commit_and_restart(r1_task: dict[str, str], record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-014-TC01")
    record_property("source_clauses", "AOS-014-F02,AOS-014-F03,AOS-014-AC01")
    actor, reader = Actor(r1_task["owner"], r1_task["project"]), EventReplay()
    with psycopg.connect(r1_task["dsn"]) as writer, psycopg.connect(r1_task["dsn"]) as observing:
        uow = UnitOfWork(writer)
        seq = append_event(
            uow,
            goal_id=r1_task["goal"],
            task_id=r1_task["task"],
            actor=actor.owner_id,
            kind="test.committed",
            payload={"schema_version": 1},
        )
        assert reader.read(UnitOfWork(observing), actor, r1_task["goal"], 0).events == ()
        observing.commit()
        writer.commit()
        events = reader.read(UnitOfWork(observing), actor, r1_task["goal"], 0).events
        assert len(events) == 1 and events[0]["seq"] == str(seq) and len(events[0]["sha256"]) == 64
        observing.commit()
        with pytest.raises(psycopg.Error, match="immutable"), writer.transaction():
            writer.execute("UPDATE panestria.task_event SET payload='{}' WHERE seq=%s", (seq,))
        append_event(
            uow,
            goal_id=r1_task["goal"],
            task_id=r1_task["task"],
            actor=actor.owner_id,
            kind="test.rollback",
            payload={},
        )
        writer.rollback()
    with psycopg.connect(r1_task["dsn"]) as restarted:
        assert len(EventReplay().read(UnitOfWork(restarted), actor, r1_task["goal"], 0).events) == 1
        with pytest.raises(KernelDenied, match="not_found"), restarted.transaction():
            reader.read(UnitOfWork(restarted), Actor(str(uuid4()), actor.project_id), r1_task["goal"], 0)


def test_sse_reconnect_decimal_cursor(r1_task: dict[str, str], record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-014-TC02")
    record_property("source_clauses", "AOS-014-F02,AOS-014-AC01")
    actor = Actor(r1_task["owner"], r1_task["project"])
    with psycopg.connect(r1_task["dsn"]) as c:
        c.execute("ALTER TABLE panestria.task_event ALTER COLUMN seq RESTART WITH 9007199254740993")
        c.commit()
        for _ in range(3):
            append_event(
                UnitOfWork(c),
                goal_id=r1_task["goal"],
                task_id=r1_task["task"],
                actor=actor.owner_id,
                kind="test.replay",
                payload={},
            )
            c.commit()
    client = _client(r1_task)
    api = client.app.state.goal_api

    def request(after: str | None = None) -> Request:
        headers = [(b"host", b"127.0.0.1:8766"), (b"authorization", b"Bearer test-only-cli-token-at-least-16")]
        if after:
            headers.append((b"last-event-id", after.encode()))

        async def receiving() -> dict[str, object]:
            return {"type": "http.request", "body": b"", "more_body": False}

        return Request(
            {
                "type": "http",
                "method": "GET",
                "path": f"/v1/goals/{r1_task['goal']}/events",
                "headers": headers,
                "app": client.app,
                "state": {},
                "query_string": b"",
            },
            receiving,
        )

    async def scenario() -> None:
        first = await stream_events(request(), api, r1_task["goal"], "0")
        frame = await anext(first.body_iterator)
        event = json.loads(frame.decode().split("data: ")[1])
        assert event["seq"] == "9007199254740993"
        await first.body_iterator.aclose()
        resumed = await stream_events(request(event["seq"]), api, r1_task["goal"], "0")
        second, third = await anext(resumed.body_iterator), await anext(resumed.body_iterator)
        assert b"9007199254740994" in second and b"9007199254740995" in third
        await resumed.body_iterator.aclose()

    asyncio.run(scenario())
    with psycopg.connect(r1_task["dsn"]) as c:
        reader = EventReplay()
        reader.retire_before(UnitOfWork(c), actor, r1_task["goal"], 9007199254740994, 0)
        c.commit()
        page = reader.read(UnitOfWork(c), actor, r1_task["goal"], 0)
        assert page.resync and page.events == () and page.snapshot["cursor"] == "9007199254740995"
    for value in ["01", "-1", "1.0", "9223372036854775808", "١"]:
        with pytest.raises(KernelDenied, match="invalid_cursor"):
            parse_cursor(value)


def test_sse_session_revocation_between_frames(r1_task: dict[str, str]) -> None:
    client = _client(r1_task)
    cli = {"Authorization": "Bearer test-only-cli-token-at-least-16"}
    origin = {"Origin": "http://127.0.0.1:8766"}
    code = client.post("/v1/session/code", json={}, headers=cli).json()["code"]
    paired = client.post("/v1/session/pair", json={"code": code}, headers=origin)
    assert paired.status_code == 200
    actor = Actor(r1_task["owner"], r1_task["project"])
    with psycopg.connect(r1_task["dsn"]) as c:
        for _ in range(2):
            append_event(
                UnitOfWork(c),
                goal_id=r1_task["goal"],
                task_id=r1_task["task"],
                actor=actor.owner_id,
                kind="test.private",
                payload={},
            )
            c.commit()

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    token = client.cookies.get("panestria_session")
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": f"/v1/goals/{r1_task['goal']}/events",
            "headers": [(b"host", b"127.0.0.1:8766"), (b"cookie", f"panestria_session={token}".encode())],
            "app": client.app,
            "state": {},
            "query_string": b"",
        },
        receive,
    )

    async def scenario() -> None:
        stream = await stream_events(request, client.app.state.goal_api, r1_task["goal"], "0")
        assert b"test.private" in await anext(stream.body_iterator)
        with psycopg.connect(r1_task["dsn"]) as c:
            access = client.app.state.browser_access
            access.service.revoke(UnitOfWork(c), actor, token, paired.json()["csrf_token"])
        denied = await anext(stream.body_iterator)
        assert b"event: error" in denied and b"unauthorized" in denied and b"test.private" not in denied
        with pytest.raises(StopAsyncIteration):
            await anext(stream.body_iterator)

    asyncio.run(scenario())
