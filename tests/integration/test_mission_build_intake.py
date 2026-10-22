"""Actual canonical staging/HTTP/Chromium; no worker or inference launched by intake."""

import copy
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
from build_support import build as build  # noqa: F401
from fastapi.testclient import TestClient
from plan_support import PATHS
from plan_support import r1_task as r1_task  # noqa: F401
from test_mission_control_browser import ASSETS, configure
from test_public_plan_submission import submission as submission  # noqa: F401

from panestria.api.activity_server import build_activity_app
from panestria.api.local_protocol import LocalHttpProtocol
from panestria.api.mission_web import mount_mission_control
from panestria.api.routes import build_intake
from panestria.config import Settings
from panestria.config_local import LocalApplicationRejected
from panestria.contracts.goal import contract_sha256, load_contract
from panestria.execution.build_intake import BuildIntakeService
from panestria.kernel.plan_store import PlanStore
from panestria.kernel.uow import UnitOfWork

ROOT = Path(__file__).resolve().parents[2]


def bundle(f):
    _, document, proposal, inventory = f
    return {
        "contract_document": document,
        "proposal": proposal.model_dump(mode="json"),
        "inventory": inventory.model_dump(mode="json"),
    }


def fresh(value):
    value = copy.deepcopy(value)
    value["contract_document"]["goal_id"] = str(uuid4())
    value["proposal"].update(
        plan_id=str(uuid4()),
        goal_id=value["contract_document"]["goal_id"],
        contract_sha256=contract_sha256(load_contract(value["contract_document"])),
    )
    return value


def application(f, tmp_path, enabled=True):
    b = f[0]
    tmp_path.mkdir(parents=True, exist_ok=True)
    path, config, token = configure({"owner": b.actor.owner_id, "project": b.actor.project_id}, tmp_path)
    app = build_activity_app(config, Settings(database_url=b.task["dsn"]).validate_profile(), token)
    mount_mission_control(app, config, token, ASSETS, build_intake=enabled)
    return app, path, config, token


def counts(f):
    b = f[0]
    with psycopg.connect(b.task["dsn"]) as db:
        return db.execute(
            "SELECT (SELECT count(*) FROM panestria.goal WHERE project_id=%s),"
            "(SELECT count(*) FROM panestria.build_plan WHERE project_id=%s),"
            "(SELECT count(*) FROM panestria.task t JOIN panestria.goal g ON g.id=t.goal_id WHERE g.project_id=%s),"
            "(SELECT count(*) FROM panestria.task_attempt a JOIN panestria.task t ON t.id=a.task_id"
            " JOIN panestria.goal g ON g.id=t.goal_id WHERE g.project_id=%s),"
            "(SELECT count(*) FROM panestria.build_plan_acceptance WHERE project_id=%s)",
            (b.actor.project_id,) * 5,
        ).fetchone()


@pytest.mark.parametrize("build", [PATHS], indirect=True)
def test_plan_intake_atomic_scope_replay_and_separate_acceptance(submission, tmp_path, monkeypatch):
    b = submission[0]
    app, _, config, token = application(submission, tmp_path)
    route = "/v1/mission/build/plans"
    initial = counts(submission)
    bearer, origin = {"Authorization": "Bearer " + token}, {"Origin": config.origin}
    with TestClient(app, base_url=config.origin) as client:
        assert client.get(route + "/" + str(uuid4())).status_code == 401
        code = client.post("/v1/session/code", headers=bearer, json={}).json()["code"]
        csrf = client.post("/v1/session/pair", headers=origin, json={"code": code}).json()["csrf_token"]
        headers = {**origin, "X-Panestria-CSRF": csrf}
        document = {**bundle(submission), "public_plan": True}
        assert client.post(route, json=document, headers=origin).status_code == 403
        assert (
            client.post(route, json=document, headers={**headers, "Origin": "https://evil.invalid"}).status_code == 403
        )
        assert (
            client.post(
                route, content=b" " * 65537, headers={**headers, "Content-Type": "application/json"}
            ).status_code
            == 413
        )
        for value in (False, 1, "true"):
            assert client.post(route, json={**document, "public_plan": value}, headers=headers).status_code == 422
        invalid = copy.deepcopy(document)
        invalid["proposal"]["inventory_sha256"] = "ff" * 32
        assert client.post(route, json=invalid, headers=headers).status_code == 409
        for key, value in (("privacy_class", "RESTRICTED"), ("project_id", str(uuid4()))):
            invalid = copy.deepcopy(document)
            invalid["contract_document"][key] = value
            assert client.post(route, json=invalid, headers=headers).status_code == 409
        assert counts(submission) == initial
        response = client.post(route, json=document, headers=headers)
        assert response.status_code == 200, response.text
        view = response.json()
        assert view["goal_status"] == "CREATED" and view["plan"]["state"] == "PROPOSED"
        assert view["contract_document"] == document["contract_document"]
        assert view["plan"]["proposal"] == document["proposal"] and view["plan"]["inventory"] == document["inventory"]
        assert view["execution_authority"] == "NONE" and view["runtime_qualification"] == "NOT_ASSESSED"
        assert client.post(route, json=document, headers=headers).json() == view
        assert counts(submission) == tuple(n + extra for n, extra in zip(initial, (1, 1, 0, 0, 0), strict=True))
        identifier = document["proposal"]["plan_id"]
        assert client.get(route + "/" + identifier).json() == view
        assert client.get(route + "/" + str(uuid4())).status_code == 404
        assert client.post("/v1/goals", json={}, headers=headers).status_code == 404
        assert client.post("/v1/ask", json={}, headers=headers).status_code == 404
        assert client.post(route + "/" + identifier + "/accept", json={}, headers=headers).status_code == 404
        actual = build_intake.reauthorize_mutation
        seen = []

        def revoke(request, api, connection):
            seen.append(1)
            if len(seen) == 2:
                connection.execute(
                    "UPDATE panestria.browser_session SET revoked_at=clock_timestamp() WHERE project_id=%s",
                    (b.actor.project_id,),
                )
            return actual(request, api, connection)

        recorded = counts(submission)
        monkeypatch.setattr(build_intake, "reauthorize_mutation", revoke)
        assert client.post(route, json=fresh(document), headers=headers).status_code == 401
        assert counts(submission) == recorded
        monkeypatch.setattr(build_intake, "reauthorize_mutation", actual)
        with psycopg.connect(b.task["dsn"]) as db:
            PlanStore().accept(UnitOfWork(db), b.actor, identifier, view["plan"]["effect_digest"], accept_plan=True)
        assert client.get(route + "/" + identifier).json()["plan"]["state"] == "ACCEPTED"
        assert counts(submission) == tuple(n + extra for n, extra in zip(recorded, (0, 0, 2, 0, 1), strict=True))
        with psycopg.connect(b.task["dsn"]) as db:
            db.execute(
                "UPDATE panestria.project SET policy_version=policy_version+1 WHERE id=%s", (b.actor.project_id,)
            )
        assert client.post(route, json=fresh(document), headers=headers).status_code == 409
        assert client.get(route + "/" + identifier).status_code == 409
    default, _, _, _ = application(submission, tmp_path / "default", enabled=False)
    with TestClient(default, base_url=config.origin) as client:
        assert client.post(route, json=document, headers=bearer).status_code == 404
        assert client.get("/v1/mission/capabilities", headers=bearer).json()["build_intake_enabled"] is False
    with pytest.raises(LocalApplicationRejected, match="mission_build_select_one_mode"):
        mount_mission_control(default, config, token, ASSETS, build_intake=True, build_review_root=tmp_path)


@pytest.mark.parametrize("build", [PATHS], indirect=True)
def test_browser_plan_intake_lost_reply_and_reload_recovery(submission, tmp_path, monkeypatch, record_property):
    b = submission[0]
    app, path, config, token = application(submission, tmp_path)
    record_property(
        "mode",
        "ACTUAL_CHROMIUM_HTTP_PG_GIT_CLI_PAIRING__DECLARED_FIXTURE_INVENTORY__NO_INTAKE_EXECUTION__LOST_ACK_INJECTION",
    )
    first, second = bundle(submission), fresh(bundle(submission))
    original, failed = BuildIntakeService.inspect, set()

    def lose_reply(self, uow, actor, identifier):
        value = original(self, uow, actor, identifier)
        if identifier == second["proposal"]["plan_id"] and identifier not in failed:
            failed.add(identifier)
            raise OSError("synthetic committed reply lost")
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
        fixture, screenshot = tmp_path / "browser.json", tmp_path / "build-intake.png"
        fixture.write_text(
            json.dumps(
                {"origin": config.origin, "code": json.loads(code.stdout)["code"], "first": first, "second": second}
            )
        )
        fixture.chmod(0o600)
        result = subprocess.run(
            [os.environ.get("PANESTRIA_TEST_NODE", "node"), "tests/build-intake.mjs"],
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
        assert failed == {second["proposal"]["plan_id"]}
        with psycopg.connect(b.task["dsn"]) as db:
            for value in (first, second):
                goal, plan = value["proposal"]["goal_id"], value["proposal"]["plan_id"]
                assert db.execute("SELECT status FROM panestria.goal WHERE id=%s", (goal,)).fetchone() == ("CREATED",)
                assert db.execute("SELECT count(*) FROM panestria.task WHERE goal_id=%s", (goal,)).fetchone() == (0,)
                assert db.execute(
                    "SELECT count(*) FROM panestria.build_plan_acceptance WHERE plan_id=%s", (plan,)
                ).fetchone() == (0,)
                assert db.execute(
                    "SELECT count(*) FROM panestria.task_event WHERE goal_id=%s AND kind='build.plan.proposed'", (goal,)
                ).fetchone() == (1,)
        target = os.environ.get("PANESTRIA_MISSION_SCREENSHOT")
        if target:
            import shutil

            shutil.copyfile(screenshot, target)
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive()
