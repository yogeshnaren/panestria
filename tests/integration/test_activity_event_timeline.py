"""Actual PG/read-only HTTP/SSE; no model, payload, grant or mutation interface."""

import asyncio
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request
from test_aos_009 import _client

from panestria.api.activity_server import build_activity_app
from panestria.api.event_stream import stream_events
from panestria.config import Settings
from panestria.config_activity import ActivitySettings
from panestria.contracts.activity import ActivityTimeline
from panestria.kernel.errors import KernelDenied
from panestria.kernel.event_replay import EventReplay
from panestria.kernel.goals import Actor
from panestria.kernel.repositories.tasks import append_event
from panestria.kernel.uow import UnitOfWork

TOKEN = "synthetic-timeline-test-token-long-enough"


def seed(task, count=3):
    with psycopg.connect(task["dsn"]) as c:
        result = []
        for _ in range(count):
            result.append(
                append_event(
                    UnitOfWork(c),
                    goal_id=task["goal"],
                    task_id=task["task"],
                    actor=task["owner"],
                    kind="timeline.observed",
                    payload={"private": "PRIVATE_TIMELINE_SENTINEL"},
                )
            )
            c.commit()
        return result


def test_metadata_json_scope_cursor_resync_and_no_write_locks_or_mutations(r1_task):
    f = r1_task
    seq = seed(f)
    config = ActivitySettings(
        schema_version=1,
        owner_id=UUID(f["owner"]),
        project_id=UUID(f["project"]),
        bind_port=8769,
        token_file=Path("/unused-synthetic-token"),
    )
    app = build_activity_app(config, Settings(database_url=f["dsn"]).validate_profile(), TOKEN)
    headers = {"Authorization": "Bearer " + TOKEN}
    route = f"/v1/activity/goals/{f['goal']}/events"
    with TestClient(app, base_url=config.origin) as client, psycopg.connect(f["dsn"]) as c:
        assert client.get(route).status_code == 401
        assert client.get(route, headers={**headers, "Origin": "https://foreign.invalid"}).status_code == 403
        foreign_project, foreign_goal = str(uuid4()), str(uuid4())
        c.execute("INSERT INTO panestria.project(id,owner_id) VALUES(%s,%s)", (foreign_project, f["owner"]))
        c.execute(
            "INSERT INTO panestria.goal(id,owner_id,project_id,intent,status) "
            "VALUES(%s,%s,%s,'PRIVATE_FOREIGN','ACTIVE')",
            (foreign_goal, f["owner"], foreign_project),
        )
        c.commit()
        assert client.get(f"/v1/activity/goals/{foreign_goal}/events", headers=headers).status_code == 404
        before = c.execute("SELECT count(*) FROM panestria.task_event").fetchone()
        # Goal/task writes do not serialize a read-only metadata observation.
        c.execute("SELECT id FROM panestria.goal WHERE id=%s FOR UPDATE", (f["goal"],))
        response = client.get(route, headers=headers)
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        page = ActivityTimeline.model_validate_json(response.content)
        assert [int(e.seq) for e in page.events] == seq and page.next_cursor == str(seq[-1])
        assert page.snapshot.goal_id == UUID(f["goal"]) and page.snapshot.status == "ACTIVE"
        assert not any(value in response.text for value in ("PRIVATE_TIMELINE", "payload", "sha256", "trace_id"))
        assert client.get(route, params={"after": page.next_cursor}, headers=headers).json()["events"] == []
        future = client.get(route, params={"after": str(2**63 - 1)}, headers=headers).json()
        assert future["resync"] and future["events"] == [] and future["snapshot"]["status"] == "ACTIVE"
        assert client.get(f"/v1/activity/goals/{uuid4()}/events", headers=headers).status_code == 404
        assert client.get(route, params={"after": "01"}, headers=headers).status_code == 422
        for target in ("/v1/goals", "/v1/ask", "/v1/approvals", "/v2/profiles", "/v1/session/code"):
            assert client.post(target, json={}, headers=headers).status_code == 404
        assert c.execute("SELECT count(*) FROM panestria.task_event").fetchone() == before
        c.rollback()
        EventReplay().retire_before(UnitOfWork(c), Actor(f["owner"], f["project"]), f["goal"], seq[-1], 0)
        c.commit()
        reset = client.get(route, headers=headers).json()
        assert reset["resync"] and reset["events"] == [] and reset["next_cursor"] == str(seq[-1])
        with pytest.raises(KernelDenied, match="read_only_observation_required"):
            EventReplay().read(UnitOfWork(c), Actor(f["owner"], f["project"]), f["goal"], 0, metadata_only=True)


def test_metadata_sse_reconnect_and_revocation_deny_cached_delivery(r1_task):
    f = r1_task
    seq = seed(f)
    client = _client(f)
    cli = {"Authorization": "Bearer test-only-cli-token-at-least-16"}
    origin = {"Origin": "http://127.0.0.1:8766"}
    code = client.post("/v1/session/code", headers=cli, json={}).json()["code"]
    paired = client.post("/v1/session/pair", headers=origin, json={"code": code})
    token = client.cookies.get("panestria_session")

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    def request(after=None):
        headers = [(b"host", b"127.0.0.1:8766"), (b"cookie", f"panestria_session={token}".encode())]
        if after:
            headers.append((b"last-event-id", after.encode()))
        return Request(
            {
                "type": "http",
                "method": "GET",
                "path": f"/v1/activity/goals/{f['goal']}/events",
                "headers": headers,
                "app": client.app,
                "state": {},
                "query_string": b"",
            },
            receive,
        )

    async def scenario():
        first = await stream_events(request(), client.app.state.goal_api, f["goal"], "0", metadata_only=True)
        event = await anext(first.body_iterator)
        assert f"id: {seq[0]}".encode() in event and b"PRIVATE_TIMELINE" not in event and b"sha256" not in event
        await first.body_iterator.aclose()
        stream = await stream_events(
            request(str(seq[0])), client.app.state.goal_api, f["goal"], "0", metadata_only=True
        )
        assert f"id: {seq[1]}".encode() in await anext(stream.body_iterator)
        with psycopg.connect(f["dsn"]) as c:
            client.app.state.browser_access.service.revoke(
                UnitOfWork(c), Actor(f["owner"], f["project"]), token, paired.json()["csrf_token"]
            )
        denied = await anext(stream.body_iterator)
        assert b"unauthorized" in denied and b"timeline.observed" not in denied and f["goal"].encode() not in denied
        with pytest.raises(StopAsyncIteration):
            await anext(stream.body_iterator)

    try:
        asyncio.run(scenario())
    finally:
        client.app.state.health.shutdown()
