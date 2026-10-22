"""Real local PUBLIC intake browser/HTTP/PG/CAS; no model, search or qualification."""

import json
import os
import subprocess
import threading
import time
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
import uvicorn
from fastapi.testclient import TestClient
from test_mission_control_browser import ASSETS, configure
from test_research_submission import QUESTION  # noqa: F401
from test_research_submission import staged as staged

from panestria.api.activity_server import build_activity_app
from panestria.api.local_protocol import LocalHttpProtocol
from panestria.api.mission_web import mount_mission_control
from panestria.api.routes import research_intake
from panestria.config import Settings
from panestria.config_local import LocalApplicationRejected
from panestria.contracts.research import ResearchLimits
from panestria.execution.research_intake import ResearchIntakeService

ROOT = Path(__file__).resolve().parents[2]


def application(staged, tmp_path, enabled=True):
    dsn, actor, root, document = staged
    path, config, token = configure({"owner": actor.owner_id, "project": actor.project_id}, tmp_path)
    intake = tmp_path / "research-intake.json"
    intake.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "root": str(root),
                "contract_template": document,
                "limits": ResearchLimits(max_sources=2).model_dump(mode="json"),
            }
        )
    )
    intake.chmod(0o600)
    app = build_activity_app(config, Settings(database_url=dsn).validate_profile(), token)
    mount_mission_control(app, config, token, ASSETS, research_intake=intake if enabled else None)
    return app, path, config, token, intake


def body(app, **changes):
    return {
        "goal_id": str(uuid4()),
        "template_sha256": app.state.research_intake.view.template_sha256,
        "question": QUESTION,
        "public_question": True,
        **changes,
    }


def totals(dsn, project):
    with psycopg.connect(dsn) as db:
        return tuple(
            db.execute(
                "SELECT (SELECT count(*) FROM panestria.goal WHERE project_id=%s),"
                " (SELECT count(*) FROM panestria.research_request WHERE project_id=%s),"
                " (SELECT count(*) FROM panestria.task_attempt a JOIN panestria.task t ON a.task_id=t.id"
                " JOIN panestria.goal g ON g.id=t.goal_id WHERE g.project_id=%s)",
                (project, project, project),
            ).fetchone()
        )


def test_public_staging_replay_scope_and_final_session_fence(staged, tmp_path, monkeypatch):
    app, _, config, token, intake = application(staged, tmp_path)
    route = "/v1/mission/research/questions"
    bearer = {"Authorization": "Bearer " + token}
    origin = {"Origin": config.origin}
    initial = totals(staged[0], staged[1].project_id)
    with TestClient(app, base_url=config.origin) as client:
        assert client.get("/v1/mission/research/intake").status_code == 401
        view = client.get("/v1/mission/research/intake", headers=bearer).json()
        assert view["contract_template"] == app.state.research_intake.view.contract_template
        assert str(staged[2]) not in json.dumps(view) and view["execution_authority"] == "NONE"
        code = client.post("/v1/session/code", headers=bearer, json={}).json()["code"]
        csrf = client.post("/v1/session/pair", headers=origin, json={"code": code}).json()["csrf_token"]
        headers = {**origin, "X-Panestria-CSRF": csrf}
        request = body(app)
        assert client.post(route, json=request, headers=origin).status_code == 403
        assert (
            client.post(route, json=request, headers={**headers, "Origin": "https://evil.invalid"}).status_code == 403
        )
        for changes in (
            {"public_question": False},
            {"public_question": 1},
            {"public_question": "true"},
            {"question": "é" * 2100},
        ):
            assert client.post(route, json={**request, **changes}, headers=headers).status_code == 422
        assert client.post(route, json={**request, "template_sha256": "ff" * 32}, headers=headers).status_code == 409
        assert totals(staged[0], staged[1].project_id) == initial
        response = client.post(route, json=request, headers=headers)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["question"] == QUESTION and result["goal_status"] == result["task_state"] == "CREATED"
        assert result["semantic_support"] == "NOT_ASSESSED" and result["operation"] == "STAGED_NO_EXECUTION"
        assert client.post(route, json=request, headers=headers).json() == result
        assert (
            client.post(route, json={**request, "question": "Different PUBLIC intent"}, headers=headers).status_code
            == 409
        )
        assert client.get(route + "/" + str(uuid4())).status_code == 404
        assert client.post("/v1/ask", json={}, headers=headers).status_code == 404
        assert client.post("/v1/goals", json={}, headers=headers).status_code == 404
        recorded = totals(staged[0], staged[1].project_id)
        assert recorded == (initial[0] + 1, initial[1] + 1, initial[2])
        actual = research_intake.reauthorize_mutation
        observations = []

        def revoke_before_commit(request, api, connection):
            observations.append(1)
            if len(observations) == 2:
                connection.execute(
                    "UPDATE panestria.browser_session SET revoked_at=clock_timestamp() WHERE project_id=%s",
                    (staged[1].project_id,),
                )
            return actual(request, api, connection)

        monkeypatch.setattr(research_intake, "reauthorize_mutation", revoke_before_commit)
        denied = client.post(route, json=body(app), headers=headers)
        assert denied.status_code == 401 and totals(staged[0], staged[1].project_id) == recorded
        monkeypatch.setattr(research_intake, "reauthorize_mutation", actual)
        with psycopg.connect(staged[0]) as db:
            db.execute(
                "UPDATE panestria.project SET policy_version=policy_version+1 WHERE id=%s", (staged[1].project_id,)
            )
        assert client.post(route, json=body(app), headers=headers).status_code == 409
        assert totals(staged[0], staged[1].project_id) == recorded
    no_intake = build_activity_app(config, Settings(database_url=staged[0]).validate_profile(), token)
    mount_mission_control(no_intake, config, token, ASSETS)
    with TestClient(no_intake, base_url=config.origin) as default:
        assert default.post(route, json={}, headers=bearer).status_code == 404
        assert default.get("/v1/mission/capabilities", headers=bearer).json()["research_intake_enabled"] is False
    with pytest.raises(LocalApplicationRejected, match="mission_research_select_one_mode"):
        mount_mission_control(no_intake, config, token, ASSETS, research_intake=intake, build_review_root=tmp_path)


def test_browser_public_question_and_committed_response_recovery(staged, tmp_path, monkeypatch, record_property):
    app, path, config, token, _ = application(staged, tmp_path)
    record_property("mode", "ACTUAL_CHROMIUM_HTTP_PG_CAS_CLI_PAIRING__NO_MODEL_OR_SEARCH__EXPLICIT_LOST_ACK_INJECTION")
    original = ResearchIntakeService.inspect
    failed = set()

    def lose_one_reply(self, dsn, actor, goal):
        value = original(self, dsn, actor, goal)
        if "LOST_ACK" in value.question and goal not in failed:
            failed.add(goal)
            raise OSError("synthetic committed response lost")
        return value

    monkeypatch.setattr(ResearchIntakeService, "inspect", lose_one_reply)
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
            env={**os.environ, "PANESTRIA_DATABASE_URL": staged[0]},
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert code.returncode == 0 and token not in code.stdout, code.stderr
        fixture = tmp_path / "browser.json"
        fixture.write_text(
            json.dumps({"origin": config.origin, "code": json.loads(code.stdout)["code"], "question": QUESTION})
        )
        fixture.chmod(0o600)
        screenshot = tmp_path / "research-intake.png"
        browser = subprocess.run(
            [os.environ.get("PANESTRIA_TEST_NODE", "node"), "tests/research-intake.mjs"],
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
        assert browser.returncode == 0, browser.stdout + browser.stderr
        goals = json.loads(browser.stdout)
        with psycopg.connect(staged[0]) as db:
            for goal in goals:
                assert db.execute("SELECT status FROM panestria.goal WHERE id=%s", (goal,)).fetchone() == ("CREATED",)
                assert db.execute("SELECT state FROM panestria.task WHERE goal_id=%s", (goal,)).fetchall() == [
                    ("CREATED",)
                ]
                assert db.execute(
                    "SELECT count(*) FROM panestria.research_request WHERE goal_id=%s", (goal,)
                ).fetchone() == (1,)
                assert db.execute(
                    "SELECT count(*) FROM panestria.task_event WHERE goal_id=%s AND kind='research.question.staged'",
                    (goal,),
                ).fetchone() == (1,)
                assert db.execute(
                    "SELECT count(*) FROM panestria.task_attempt a JOIN panestria.task t ON a.task_id=t.id"
                    " WHERE t.goal_id=%s",
                    (goal,),
                ).fetchone() == (0,)
        assert len(failed) == 1
        target = os.environ.get("PANESTRIA_MISSION_SCREENSHOT")
        if target:
            import shutil

            shutil.copyfile(screenshot, target)
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive()
