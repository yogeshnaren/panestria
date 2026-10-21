"""Real scoped PG/HTTP metadata: no model, dispatch, private content or new task state."""

import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from test_native_plan_execution import prepared_plan as prepared_plan  # noqa: F401
from test_owner_build_cli import owner_cli as owner_cli  # noqa: F401

from panestria.api import create_app
from panestria.api.auth import GoalApi
from panestria.api.health import default_readiness_probe
from panestria.api.main import mount_goal_api
from panestria.config import Settings
from panestria.contracts.activity import ProjectActivity
from panestria.contracts.ask import AskSubmission
from panestria.kernel.activity import project_activity
from panestria.kernel.ask import AskService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor, GoalService
from panestria.kernel.uow import UnitOfWork


def test_scoped_activity_pages_are_read_only_content_free_and_independent_of_model(prepared_plan):
    f, owner, _, plan = prepared_plan
    with owner.connect() as c:
        expected_goals = {
            r[0]
            for r in c.execute(
                "SELECT id FROM panestria.goal WHERE owner_id=%s AND project_id=%s",
                (owner.actor.owner_id, owner.actor.project_id),
            ).fetchall()
        }
    fixture = json.loads(
        (Path(__file__).resolve().parents[2] / "docs/fixtures/synthetic-goal-contract.json").read_text()
    )
    fixture.update(
        goal_id=str(uuid4()),
        owner_id=owner.actor.owner_id,
        project_id=owner.actor.project_id,
        intent="PRIVATE_ACTIVITY_INTENT",
    )
    with owner.connect() as c:
        GoalService().submit(UnitOfWork(c), owner.actor, fixture, "private-activity-goal")
        c.execute("UPDATE panestria.task SET state='WAITING_APPROVAL' WHERE id=%s", (plan.nodes[-1].task_id,))
    expected_goals.add(UUID(fixture["goal_id"]))
    expected_asks = set()
    for _ in range(3):
        identity = str(uuid4())
        expected_asks.add(UUID(identity))
        with owner.connect() as c:
            AskService().prepare(
                UnitOfWork(c),
                owner.actor,
                AskSubmission(
                    request_id=identity,
                    project_id=owner.actor.project_id,
                    question="PRIVATE_ACTIVITY_QUESTION",
                    privacy_label="PUBLIC",
                ),
            )
    other_project = str(uuid4())
    with owner.connect() as c:
        c.execute("INSERT INTO panestria.project(id,owner_id) VALUES(%s,%s)", (other_project, owner.actor.owner_id))
        foreign = {**fixture, "goal_id": str(uuid4()), "project_id": other_project}
        GoalService().submit(UnitOfWork(c), Actor(owner.actor.owner_id, other_project), foreign, "foreign")
    application = create_app(Settings(database_url=owner.dsn), default_readiness_probe)
    token = "synthetic-activity-only-test-token"
    mount_goal_api(application, GoalApi(token, owner.actor.owner_id, owner.actor.project_id, owner.dsn))
    with owner.connect() as c:
        before = c.execute("SELECT count(*) FROM panestria.task_event").fetchone()
    with TestClient(application, base_url="http://127.0.0.1:8765") as client:
        headers = {"Authorization": "Bearer " + token}
        assert client.get("/v1/activity").status_code == 401
        assert client.get("/v1/activity", headers={**headers, "Origin": "https://untrusted.invalid"}).status_code == 403
        pages = []
        cursor = None
        for _ in range(8):
            response = client.get(
                "/v1/activity", headers=headers, params={"limit": 2, **({"before": cursor} if cursor else {})}
            )
            assert response.status_code == 200, response.text
            assert response.headers["cache-control"] == "no-store"
            assert "PRIVATE_ACTIVITY" not in response.text and foreign["goal_id"] not in response.text
            page = ProjectActivity.model_validate_json(response.content)
            pages.extend(page.entries)
            cursor = page.next_cursor
            if not cursor:
                break
        else:
            pytest.fail("Activity cursor did not finish the bounded fixture")
        assert {(p.source, p.id) for p in pages} == (
            {("GOAL", identity) for identity in expected_goals} | {("ASK", identity) for identity in expected_asks}
        )
        assert len(pages) == len(expected_goals) + len(expected_asks)
        assert sum(p.workflow == "ASK" for p in pages) == 3
        build = next(p for p in pages if p.id == UUID(plan.goal_id))
        assert build.workflow == "BUILD" and build.waiting_reviews == 1 and build.needs_attention
        assert next(p for p in pages if p.id == UUID(fixture["goal_id"])).workflow == "KERNEL"
        assert (
            client.get("/v1/activity", headers=headers, params={"before": "GOAL:" + foreign["goal_id"]}).status_code
            == 404
        )
        # A real task lock does not block this read-only metadata observation.
        with owner.connect() as lock:
            lock.execute("SELECT id FROM panestria.task WHERE id=%s FOR UPDATE", (plan.nodes[0].task_id,))
            assert client.get("/v1/activity", headers=headers).status_code == 200
        assert client.post("/v1/activity", headers=headers, json={}).status_code == 405
    with owner.connect() as c:
        assert c.execute("SELECT count(*) FROM panestria.task_event").fetchone() == before
        with pytest.raises(KernelDenied, match="read_only_observation_required"):
            project_activity(UnitOfWork(c), owner.actor)
