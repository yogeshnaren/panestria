"""Exact opt-in plan acceptance uses canonical PG guards, never a worker dispatcher."""

import json
import os
import subprocess
import threading
import time
from pathlib import Path

import psycopg
import pytest
import uvicorn
from build_support import build as build  # noqa: F401
from fastapi.testclient import TestClient
from plan_support import PATHS
from plan_support import r1_task as r1_task  # noqa: F401
from test_mission_build_intake import application, bundle, counts, fresh
from test_mission_control_browser import ASSETS
from test_public_plan_submission import submission as submission  # noqa: F401

from panestria.api.activity_server import build_activity_app
from panestria.api.local_protocol import LocalHttpProtocol
from panestria.api.mission_web import mount_mission_control
from panestria.api.routes import build_intake
from panestria.config import Settings
from panestria.execution.build_intake import BuildIntakeService
from panestria.kernel.uow import UnitOfWork

ROOT = Path(__file__).resolve().parents[2]


def review_application(f, tmp_path):
    intake, path, config, token = application(f, tmp_path)
    intake.state.health.shutdown()
    app = build_activity_app(config, Settings(database_url=f[0].task["dsn"]).validate_profile(), token)
    mount_mission_control(app, config, token, ASSETS, build_plan_review=True)
    return app, path, config, token


@pytest.mark.parametrize("build", [PATHS], indirect=True)
def test_exact_plan_acceptance_session_rollback_expiry_and_no_dispatch(submission, tmp_path, monkeypatch):
    b = submission[0]
    app, _, config, token = review_application(submission, tmp_path)
    root = "/v1/mission/build/plans"
    initial = counts(submission)
    with TestClient(app, base_url=config.origin) as client:
        bearer, origin = {"Authorization": "Bearer " + token}, {"Origin": config.origin}
        code = client.post("/v1/session/code", headers=bearer, json={}).json()["code"]
        csrf = client.post("/v1/session/pair", headers=origin, json={"code": code}).json()["csrf_token"]
        headers = {**origin, "X-Panestria-CSRF": csrf}
        staged = client.post(root, json={**bundle(submission), "public_plan": True}, headers=headers).json()
        identifier = staged["plan"]["proposal"]["plan_id"]
        route = root + "/" + identifier + "/accept"
        body = {"effect_digest": staged["plan"]["effect_digest"], "accept_plan": True}
        assert client.post(route, json=body, headers=origin).status_code == 403
        assert client.post(route, json=body, headers={**headers, "Origin": "https://evil.invalid"}).status_code == 403
        for value in (False, 1, "true"):
            assert client.post(route, json={**body, "accept_plan": value}, headers=headers).status_code == 422
        assert client.post(route, json={**body, "effect_digest": "ff" * 32}, headers=headers).status_code == 409
        recorded = counts(submission)
        assert recorded == tuple(n + extra for n, extra in zip(initial, (1, 1, 0, 0, 0), strict=True))
        actual, seen = build_intake.reauthorize_mutation, []

        def revoke(request, api, connection):
            seen.append(1)
            if len(seen) == 2:
                connection.execute(
                    "UPDATE panestria.browser_session SET revoked_at=clock_timestamp() WHERE project_id=%s",
                    (b.actor.project_id,),
                )
            return actual(request, api, connection)

        monkeypatch.setattr(build_intake, "reauthorize_mutation", revoke)
        assert client.post(route, json=body, headers=headers).status_code == 401
        assert counts(submission) == recorded
        monkeypatch.setattr(build_intake, "reauthorize_mutation", actual)
        response = client.post(route, json=body, headers=headers)
        assert response.status_code == 200, response.text
        accepted = response.json()
        assert accepted["plan"]["state"] == "ACCEPTED" and accepted["operation"] == "PLAN_ACCEPTED_NO_EXECUTION"
        assert accepted["goal_status"] == "CREATED" and accepted["execution_authority"] == "NONE"
        assert client.post(route, json=body, headers=headers).json() == accepted
        assert counts(submission) == tuple(n + extra for n, extra in zip(recorded, (0, 0, 2, 0, 1), strict=True))
        # Create an actual retained expired consent by changing only its fixture
        # clock SELECT during preparation. No production clock/guard is changed.
        original_execute = UnitOfWork.execute

        def expired_clock(self, query, *args, **kwargs):
            if query == "SELECT clock_timestamp()+interval '15 minutes'":
                query = "SELECT clock_timestamp()-interval '1 second'"
            return original_execute(self, query, *args, **kwargs)

        monkeypatch.setattr(UnitOfWork, "execute", expired_clock)
        expired_body = fresh(bundle(submission))
        # Use distinct node IDs: the already accepted plan owns its old IDs.
        from uuid import uuid4

        ids = {n["task_id"]: str(uuid4()) for n in expired_body["proposal"]["nodes"]}
        for node in expired_body["proposal"]["nodes"]:
            node["task_id"] = ids[node["task_id"]]
            node["depends_on"] = [ids[t] for t in node["depends_on"]]
        expired = client.post(root, json={**expired_body, "public_plan": True}, headers=headers).json()
        monkeypatch.setattr(UnitOfWork, "execute", original_execute)
        expired_id = expired["plan"]["proposal"]["plan_id"]
        assert (
            client.post(
                root + "/" + expired_id + "/accept",
                json={"effect_digest": expired["plan"]["effect_digest"], "accept_plan": True},
                headers=headers,
            ).status_code
            == 409
        )
        assert client.get(root + "/" + expired_id).json()["plan"]["state"] == "PROPOSED"
        with psycopg.connect(b.task["dsn"]) as db:
            assert db.execute("SELECT state FROM panestria.task WHERE goal_id=%s", (staged["goal_id"],)).fetchall() == [
                ("CREATED",),
                ("CREATED",),
            ]
            assert db.execute(
                "SELECT count(*) FROM panestria.task_event WHERE goal_id=%s AND kind='build.plan.accepted'",
                (staged["goal_id"],),
            ).fetchone() == (1,)
        intake = build_activity_app(config, Settings(database_url=b.task["dsn"]).validate_profile(), token)
        mount_mission_control(intake, config, token, ASSETS, build_intake=True)
        with TestClient(intake, base_url=config.origin) as plain:
            assert plain.post(route, json=body, headers=bearer).status_code == 404
            review_cookie = client.cookies.get(app.state.browser_access.cookie_name)
            assert (
                plain.get(
                    root + "/" + identifier,
                    headers={"Cookie": intake.state.browser_access.cookie_name + "=" + review_cookie},
                ).status_code
                == 401
            )


@pytest.mark.parametrize("build", [PATHS], indirect=True)
def test_browser_exact_plan_acceptance_and_lost_commit_reply(submission, tmp_path, monkeypatch, record_property):
    b = submission[0]
    app, path, config, token = review_application(submission, tmp_path)
    record_property(
        "mode",
        "ACTUAL_CHROMIUM_HTTP_PG_GIT_CLI_PAIRING__DECLARED_FIXTURE_INVENTORY__ACCEPTANCE_ONLY__LOST_ACK_INJECTION",
    )
    original, failed = BuildIntakeService.inspect, set()
    identifier = submission[2].plan_id

    def lose_reply(self, uow, actor, plan_id):
        value = original(self, uow, actor, plan_id)
        if value.plan.state == "ACCEPTED" and plan_id not in failed:
            failed.add(plan_id)
            raise OSError("synthetic acceptance reply lost after commit")
        return value

    monkeypatch.setattr(BuildIntakeService, "inspect", lose_reply)
    server = uvicorn.Server(
        uvicorn.Config(
            app, host="127.0.0.1", port=config.bind_port, log_config=None, access_log=False, http=LocalHttpProtocol
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 15
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline
            time.sleep(0.02)
        code = subprocess.run(
            [
                str(ROOT / ".venv/bin/python"),
                "-m",
                "panestria.cli.main",
                "mission-control",
                "pair-code",
                "--config",
                str(path),
            ],
            cwd=ROOT,
            env={**os.environ, "PANESTRIA_DATABASE_URL": b.task["dsn"]},
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert code.returncode == 0 and token not in code.stdout, code.stderr
        fixture, screenshot = tmp_path / "browser.json", tmp_path / "plan-review.png"
        fixture.write_text(
            json.dumps({"origin": config.origin, "code": json.loads(code.stdout)["code"], "bundle": bundle(submission)})
        )
        fixture.chmod(0o600)
        result = subprocess.run(
            [os.environ.get("PANESTRIA_TEST_NODE", "node"), "tests/plan-acceptance.mjs"],
            cwd=ROOT / "apps/mission-control",
            env={
                **os.environ,
                "PANESTRIA_BROWSER_FIXTURE": str(fixture),
                "PANESTRIA_BROWSER_SCREENSHOT": str(screenshot),
            },
            capture_output=True,
            text=True,
            timeout=45,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert failed == {identifier}
        with psycopg.connect(b.task["dsn"]) as db:
            goal = submission[2].goal_id
            assert db.execute("SELECT state FROM panestria.task WHERE goal_id=%s", (goal,)).fetchall() == [
                ("CREATED",),
                ("CREATED",),
            ]
            assert db.execute(
                "SELECT count(*) FROM panestria.build_plan_acceptance WHERE plan_id=%s", (identifier,)
            ).fetchone() == (1,)
            assert db.execute(
                "SELECT count(*) FROM panestria.task_attempt a JOIN panestria.task t ON t.id=a.task_id "
                "WHERE t.goal_id=%s",
                (goal,),
            ).fetchone() == (0,)
        target = os.environ.get("PANESTRIA_MISSION_SCREENSHOT")
        if target:
            import shutil

            shutil.copyfile(screenshot, target)
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive()
