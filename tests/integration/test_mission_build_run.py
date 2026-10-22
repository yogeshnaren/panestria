"""Real PG/Git/HTTP/Chromium/MCP/Docker; native/cert/capacity remain explicit fixtures."""

import json
import os
import shutil
import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
import uvicorn
from fastapi.testclient import TestClient
from test_mission_control_browser import ASSETS, configure
from test_native_plan_execution import native_plan as native_plan  # noqa: F401
from test_native_plan_execution import prepared_plan as prepared_plan  # noqa: F401
from test_owner_build_cli import owner_cli as owner_cli  # noqa: F401

from panestria.api.activity_server import build_activity_app
from panestria.api.local_protocol import LocalHttpProtocol
from panestria.api.mission_web import mount_mission_control
from panestria.api.routes import mission_run
from panestria.config import Settings
from panestria.config_local import LocalApplicationRejected
from panestria.kernel.errors import KernelDenied
from panestria.kernel.uow import UnitOfWork
from panestria.verification.git_snapshot import protected_git

ROOT = Path(__file__).resolve().parents[2]


def application(native_plan, owner_cli, tmp_path):
    owner = native_plan[0]
    path, config, token = configure({"owner": owner.actor.owner_id, "project": owner.actor.project_id}, tmp_path)
    app = build_activity_app(config, Settings(database_url=owner.dsn).validate_profile(), token)
    mount_mission_control(app, config, token, ASSETS, build_run=owner_cli.config)
    return app, path, config, token


def pair(client, token, origin):
    code = client.post("/v1/session/code", headers={"Authorization": "Bearer " + token}, json={}).json()["code"]
    csrf = client.post("/v1/session/pair", headers={"Origin": origin}, json={"code": code}).json()["csrf_token"]
    return {"Origin": origin, "X-Panestria-CSRF": csrf}


def intent(plan):
    return {"request_id": str(uuid4()), "plan_sha256": plan.sha256(), "public_subscription_run": True}


def wait_return(client, route):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        reply = client.get(route)
        assert reply.status_code == 200, reply.text
        view = reply.json()
        if view["state"] == "RETURN_RECORDED" and not view["controller_active"]:
            return view
        time.sleep(0.025)
    raise AssertionError(view)


def test_run_session_rollback_cancellation_after_revocation_and_held_capacity(
    native_plan, owner_cli, tmp_path, monkeypatch
):
    owner, _, plan, state = native_plan
    state["block"] = True
    app, _, config, token = application(native_plan, owner_cli, tmp_path)
    route = f"/v1/mission/build/plans/{plan.plan_id}/run"
    body = intent(plan)
    with TestClient(app, base_url=config.origin) as client:
        assert client.get(route).status_code == 401
        headers = pair(client, token, config.origin)
        capabilities = client.get("/v1/mission/capabilities").json()
        assert capabilities["build_run_enabled"] and capabilities["build_review_enabled"]
        assert capabilities["dispatch_authority"] == "EXPLICIT_FOREGROUND_BUILD"
        assert client.get(route).json()["state"] == "NOT_REQUESTED" and state["launches"] == 0
        assert client.post(route, json=body, headers={"Origin": config.origin}).status_code == 403
        for value in (False, 1, "true"):
            assert (
                client.post(route, json={**body, "public_subscription_run": value}, headers=headers).status_code == 422
            )
        assert client.post(route, json={**body, "plan_sha256": "ff" * 32}, headers=headers).status_code == 409
        original, calls = mission_run.reauthorize_mutation, []

        def revoke(request, api, connection):
            calls.append(1)
            if len(calls) == 2:
                connection.execute(
                    "UPDATE panestria.browser_session SET revoked_at=clock_timestamp() WHERE project_id=%s",
                    (owner.actor.project_id,),
                )
            return original(request, api, connection)

        monkeypatch.setattr(mission_run, "reauthorize_mutation", revoke)
        assert client.post(route, json=body, headers=headers).status_code == 401
        monkeypatch.setattr(mission_run, "reauthorize_mutation", original)
        assert client.get(route).json()["state"] == "NOT_REQUESTED" and state["launches"] == 0
        assert client.post(route, json=body, headers=headers).status_code == 200
        assert state["started"].wait(12)
        assert client.post(route, json=body, headers=headers).status_code == 200
        assert client.post(route, json=intent(plan), headers=headers).status_code == 409
        with owner.connect() as c:
            c.execute(
                "UPDATE panestria.project SET policy_version=policy_version+1 WHERE id=%s", (owner.actor.project_id,)
            )
        cancellation = {"request_id": body["request_id"], "plan_sha256": plan.sha256(), "cancel_plan": True}
        assert client.post(route + "/cancel", json=cancellation, headers=headers).status_code == 200
        view = wait_return(client, route)
        assert view["state"] == "RETURN_RECORDED" and view["claim_release_authority"] == "NONE"
        assert state["launches"] == 2
        with owner.connect() as c:
            assert c.execute(
                "SELECT count(*) FROM panestria.build_active_worker_claim WHERE plan_id=%s", (plan.plan_id,)
            ).fetchone() == (2,)
            assert c.execute(
                "SELECT count(*) FROM panestria.approval_request WHERE goal_id=%s", (plan.goal_id,)
            ).fetchone() == (0,)
        assert (
            protected_git(owner.settings.repository, ("rev-parse", "refs/heads/main")).decode().strip()
            == owner_cli.base
        )
        plain = build_activity_app(config, Settings(database_url=owner.dsn).validate_profile(), token)
        mount_mission_control(plain, config, token, ASSETS, build_plan_review=True)
        with TestClient(plain, base_url=config.origin) as other:
            assert other.post(route, json=body, headers={"Authorization": "Bearer " + token}).status_code == 404
            cookie = client.cookies.get(app.state.browser_access.cookie_name)
            assert (
                other.get(
                    "/v1/activity", headers={"Cookie": plain.state.browser_access.cookie_name + "=" + cookie}
                ).status_code
                == 401
            )
        with pytest.raises(LocalApplicationRejected):
            mount_mission_control(plain, config, token, ASSETS, build_run=owner_cli.config, build_intake=True)


@pytest.mark.parametrize("fault", ["request_commit", "claim_commit"])
def test_lost_commit_ack_never_dispatches_or_adopts_a_claim(native_plan, owner_cli, tmp_path, monkeypatch, fault):
    owner, _, plan, state = native_plan
    app, _, config, token = application(native_plan, owner_cli, tmp_path)
    service = app.state.mission_run
    route = f"/v1/mission/build/plans/{plan.plan_id}/run"
    body = intent(plan)
    original_api, original_worker = mission_run.open_database, service.connect
    actual_execute = UnitOfWork.execute

    def expired_preparation(self, query, *args, **kwargs):
        if query == "SELECT clock_timestamp()+interval '90 seconds'":
            query = "SELECT clock_timestamp()-interval '1 second'"
        return actual_execute(self, query, *args, **kwargs)

    @contextmanager
    def request_ack_lost(dsn):
        with original_api(dsn) as c:
            yield c
        raise psycopg.OperationalError("SYNTHETIC_COMMIT_ACK_LOSS_NOT_LIVE")

    @contextmanager
    def claim_ack_lost():
        with original_worker() as c:
            yield c
        raise psycopg.OperationalError("SYNTHETIC_CLAIM_ACK_LOSS_NOT_LIVE")

    with TestClient(app, base_url=config.origin) as client:
        headers = pair(client, token, config.origin)
        if fault == "request_commit":
            # Preparation-only clock fixture, not a claim of elapsed real time.
            monkeypatch.setattr(UnitOfWork, "execute", expired_preparation)
            monkeypatch.setattr(mission_run, "open_database", request_ack_lost)
            assert client.post(route, json=body, headers=headers).status_code == 503
            monkeypatch.setattr(mission_run, "open_database", original_api)
            monkeypatch.setattr(UnitOfWork, "execute", actual_execute)
            expected = "REQUESTED"
        else:
            monkeypatch.setattr(service, "connect", claim_ack_lost)
            assert client.post(route, json=body, headers=headers).status_code == 200
            service.active[1].join(5)
            monkeypatch.setattr(service, "connect", original_worker)
            expected = "CLAIMED_UNCONFIRMED"
        observed = client.get(route).json()
        assert observed["state"] == expected and not observed["controller_active"] and state["launches"] == 0
        # Server recreation/GET does not adopt any request or claim. Fresh
        # idempotency keys cannot bypass the immutable per-plan invocation.
        recovered, _, recovered_config, recovered_token = application(native_plan, owner_cli, tmp_path / "restart")
        with TestClient(recovered, base_url=recovered_config.origin) as restarted:
            again = pair(restarted, recovered_token, recovered_config.origin)
            assert restarted.get(route).json()["record"] == observed["record"]
            assert state["launches"] == 0
            assert restarted.post(route, json=intent(plan), headers=again).status_code == 409
            if expected == "CLAIMED_UNCONFIRMED":
                assert restarted.post(route, json=body, headers=again).json()["state"] == expected
            else:
                assert restarted.post(route, json=body, headers=again).json()["record"] == observed["record"]
                recovered.state.mission_run.active[1].join(5)
                assert restarted.get(route).json()["state"] == "REQUESTED"
                with owner.connect() as c, pytest.raises(KernelDenied, match="run_not_claimable"):
                    service.store.claim(
                        UnitOfWork(c), owner.actor, plan.plan_id, body["request_id"], service.configuration
                    )
        with owner.connect() as c:
            assert c.execute(
                "SELECT count(*) FROM panestria.task_attempt a JOIN panestria.task t ON t.id=a.task_id"
                " WHERE t.goal_id=%s",
                (plan.goal_id,),
            ).fetchone() == (0,)


def test_browser_finite_two_worker_run_recovers_lost_reply_and_reaches_review(
    native_plan, owner_cli, tmp_path, monkeypatch, record_property
):
    owner, _, plan, state = native_plan
    app, path, config, token = application(native_plan, owner_cli, tmp_path)
    record_property("mode", "ACTUAL_CHROMIUM_HTTP_PG_GIT_MCP_DOCKER__NATIVE_AUTH_CERT_CAPACITY_FIXTURES__NO_PROVIDER")
    original, lost = mission_run.authorize, []

    def lose_final_response(request, api):
        actor = original(request, api)
        if request.method == "POST" and request.url.path.endswith("/run") and app.state.mission_run.active and not lost:
            lost.append(1)
            raise OSError("SYNTHETIC_POST_COMMIT_REPLY_LOSS_NOT_LIVE")
        return actor

    monkeypatch.setattr(mission_run, "authorize", lose_final_response)
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
            capture_output=True,
            text=True,
            env={**os.environ, "PANESTRIA_DATABASE_URL": owner.dsn},
            timeout=10,
        )
        assert code.returncode == 0 and token not in code.stdout, code.stderr
        fixture, screenshot = tmp_path / "browser.json", tmp_path / "finite-run.png"
        fixture.write_text(
            json.dumps(
                {
                    "origin": config.origin,
                    "code": json.loads(code.stdout)["code"],
                    "plan": plan.plan_id,
                    "goal": plan.goal_id,
                }
            )
        )
        fixture.chmod(0o600)
        result = subprocess.run(
            [os.environ.get("PANESTRIA_TEST_NODE", "node"), "tests/build-run.mjs"],
            cwd=ROOT / "apps/mission-control",
            capture_output=True,
            text=True,
            timeout=60,
            env={
                **os.environ,
                "PANESTRIA_BROWSER_FIXTURE": str(fixture),
                "PANESTRIA_BROWSER_SCREENSHOT": str(screenshot),
            },
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert len(lost) == 1 and state["launches"] == 2 and state["peak"] == 2
        assert (
            protected_git(owner.settings.repository, ("rev-parse", "refs/heads/main")).decode().strip()
            == owner_cli.base
        )
        with owner.connect() as c:
            assert c.execute(
                "SELECT count(*) FROM panestria.build_handoff WHERE plan_id=%s", (plan.plan_id,)
            ).fetchone() == (2,)
            assert c.execute(
                "SELECT count(*) FROM panestria.task_event WHERE goal_id=%s AND kind LIKE 'mission.build_run.%'",
                (plan.goal_id,),
            ).fetchone() == (3,)
            assert c.execute(
                "SELECT count(*) FROM panestria.side_effect WHERE task_id=%s", (plan.nodes[-1].task_id,)
            ).fetchone() == (0,)
        target = os.environ.get("PANESTRIA_MISSION_SCREENSHOT")
        if target:
            shutil.copyfile(screenshot, target)
    finally:
        server.should_exit = True
        thread.join(12)
        assert not thread.is_alive()


def test_configured_real_storage_reserve_defers_before_native_claim(native_plan, owner_cli, tmp_path):
    owner, _, plan, state = native_plan
    policy = tmp_path / "storage.json"
    policy.write_text(
        json.dumps({"notifications_enabled": True, "filesystem": str(tmp_path), "minimum_free_bytes": 10**18})
    )
    policy.chmod(0o600)
    settings = json.loads(owner_cli.config.read_text())
    settings["storage_policy"] = str(policy)
    owner_cli.config.write_text(json.dumps(settings))
    app, _, config, token = application(native_plan, owner_cli, tmp_path)
    route = f"/v1/mission/build/plans/{plan.plan_id}/run"
    with TestClient(app, base_url=config.origin) as client:
        headers = pair(client, token, config.origin)
        assert client.post(route, json=intent(plan), headers=headers).status_code == 200
        view = wait_return(client, route)
        assert view["result"]["runner_status"] == "WAIT"
        assert view["storage"]["decision"] == "DEFER" and view["storage"]["cleanup_authority"] == "NONE"
        assert "free_reserve_at_risk" in view["storage"]["warnings"]
        assert view["storage"]["available_bytes"] > 0
        assert str(tmp_path) not in json.dumps(view)
        assert state["launches"] == 0
        with owner.connect() as c:
            assert c.execute(
                "SELECT count(*) FROM panestria.build_worker_claim WHERE plan_id=%s", (plan.plan_id,)
            ).fetchone() == (0,)
