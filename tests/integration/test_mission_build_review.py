"""Physical browser consent -> existing exact merge; explicit nonlive worker fixtures."""

import json
import os
import select
import signal
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import httpx2 as httpx
from fastapi.testclient import TestClient
from test_mission_control_browser import configure
from test_native_plan_execution import native_plan as native_plan  # noqa: F401
from test_native_plan_execution import owner_cli as owner_cli  # noqa: F401
from test_native_plan_execution import prepared_plan as prepared_plan  # noqa: F401
from test_registered_check_authority import git

from panestria.api.activity_server import build_activity_app
from panestria.api.mission_web import mount_mission_control
from panestria.config import Settings
from panestria.kernel.goals import GoalService
from panestria.kernel.uow import UnitOfWork

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "apps/mission-control/dist"


def evidence_case(native_plan, tmp_path):
    owner, runner, plan, state = native_plan
    result = runner.run(plan.plan_id, public_subscription_run=True)
    assert result["status"] == "WAITING_APPROVAL", result
    assert state["launches"] == 2  # TEST_FIXTURE_NOT_LIVE; actual MCP/Git/verifier only.
    path, config, token = configure({"owner": owner.actor.owner_id, "project": owner.actor.project_id}, tmp_path)
    return owner, plan, path, config, token


def app_for(owner, config, token, review):
    app = build_activity_app(config, Settings(database_url=owner.dsn).validate_profile(), token)
    mount_mission_control(app, config, token, ASSETS, build_review_root=owner.settings.root if review else None)
    return app


def decision(view, choice="approve"):
    return {k: view[k] for k in ("approval_id", "effect_digest", "expected_version", "review_sha256")} | {
        "decision": choice,
        "idempotency_key": str(uuid4()),
    }


def test_scoped_exact_preview_fences_and_denial_have_no_dispatch(native_plan, tmp_path, record_property):
    owner, plan, _, config, token = evidence_case(native_plan, tmp_path)
    record_property("mode", "ACTUAL_HTTP_PG_GIT_VERIFIER__TEST_FIXTURE_NOT_LIVE_NATIVE_AUTH_CAPACITY")
    route = f"/v1/mission/goals/{plan.goal_id}/build-review"
    bearer = {"Authorization": "Bearer " + token}
    original = app_for(owner, config, token, False)
    with TestClient(original, base_url=config.origin) as old:
        assert old.get(route, headers=bearer).status_code == 404
        assert old.post(route + "/decision", headers=bearer, json={}).status_code == 404
        assert old.get("/v1/mission/capabilities", headers=bearer).json()["build_review_enabled"] is False
        code = old.post("/v1/session/code", headers=bearer, json={}).json()["code"]
        old.post("/v1/session/pair", headers={"Origin": config.origin}, json={"code": code}).raise_for_status()
        old_cookie = dict(old.cookies)
    app = app_for(owner, config, token, True)
    with TestClient(app, base_url=config.origin) as c:
        assert c.get(route).status_code == 401
        with TestClient(app, base_url=config.origin, cookies=old_cookie) as wrong:
            assert wrong.get(route).status_code == 401
        view = c.get(route, headers=bearer)
        assert view.status_code == 200, view.text
        view = view.json()
        assert "+value = 43" in view["diff"]
        assert view["preview"]["candidate_sha256"] == owner.status(plan.goal_id)["evidence_sha256"]
        assert all(json.loads(item["report"])["verdict"] == "PASS" for item in view["checks"])
        assert view["decision_available"] and view["dispatch_authority"] == "NONE"
        assert str(owner.settings.root) not in json.dumps(view)
        with owner.connect() as db:
            document = db.execute(
                "SELECT body FROM panestria.goal_contract WHERE goal_id=%s", (plan.goal_id,)
            ).fetchone()[0]
            document = {
                **document,
                "goal_id": str(uuid4()),
                "privacy_class": "INTERNAL",
                "intent": "PRIVATE_REVIEW_SENTINEL",
            }
            GoalService().submit(UnitOfWork(db), owner.actor, document, "private-review")
            before = db.execute(
                "SELECT count(*) FROM panestria.task_event WHERE goal_id=%s", (plan.goal_id,)
            ).fetchone()
        denied = c.get(f"/v1/mission/goals/{document['goal_id']}/build-review", headers=bearer)
        assert denied.status_code == 404 and "PRIVATE_REVIEW_SENTINEL" not in denied.text
        assert c.get(f"/v1/mission/goals/{uuid4()}/build-review", headers=bearer).status_code == 404
        for field, value in (
            ("effect_digest", "ff" * 32),
            ("review_sha256", "aa" * 32),
            ("expected_version", view["expected_version"] + 1),
        ):
            body = decision(view)
            body[field] = value
            assert c.post(route + "/decision", headers=bearer, json=body).status_code == 409
        code = c.post("/v1/session/code", headers=bearer, json={}).json()["code"]
        pair = c.post("/v1/session/pair", headers={"Origin": config.origin}, json={"code": code})
        csrf = pair.json()["csrf_token"]
        assert (
            c.post(
                route + "/decision",
                headers={"Origin": "https://evil.invalid", "X-Panestria-CSRF": csrf},
                json=decision(view),
            ).status_code
            == 403
        )
        assert c.post(route + "/decision", headers={"Origin": config.origin}, json=decision(view)).status_code == 403
        headers = {"Origin": config.origin, "X-Panestria-CSRF": csrf}
        digest = view["checks"][0]["check"]["report_sha256"]
        blob = owner.reports.root / digest
        raw = blob.read_bytes()
        blob.chmod(0o600)
        blob.write_bytes(b"corrupt synthetic report")
        assert c.post(route + "/decision", headers=headers, json=decision(view)).status_code != 200
        blob.write_bytes(raw)
        blob.chmod(0o400)
        with owner.connect() as db:
            assert (
                db.execute("SELECT count(*) FROM panestria.task_event WHERE goal_id=%s", (plan.goal_id,)).fetchone()
                == before
            )
            assert db.execute(
                "SELECT state FROM panestria.approval_request WHERE id=%s", (view["approval_id"],)
            ).fetchone() == ("PENDING",)
        assert git(owner.settings.repository, "rev-parse", "HEAD") == view["base_commit"]
        body = decision(view, "deny")
        response = c.post(route + "/decision", headers=headers, json=body)
        assert response.status_code == 200, response.text
        assert response.json()["state"] == "DENIED" and response.json()["dispatch_authority"] == "NONE"
        replay = c.post(route + "/decision", headers=headers, json=body)
        assert replay.status_code == 200 and replay.json()["replayed"]
        assert git(owner.settings.repository, "rev-parse", "HEAD") == view["base_commit"]
        with owner.connect() as db:
            assert db.execute("SELECT status FROM panestria.goal WHERE id=%s", (plan.goal_id,)).fetchone() == (
                "ACTIVE",
            )
            assert db.execute(
                "SELECT count(*) FROM panestria.task_event WHERE goal_id=%s AND kind='approval.decided'",
                (plan.goal_id,),
            ).fetchone() == (1,)
            assert db.execute(
                "SELECT count(*) FROM panestria.side_effect WHERE task_id=%s", (view["preview"]["task_id"],)
            ).fetchone() == (0,)


def test_physical_browser_review_offline_consent_and_existing_exact_merge(native_plan, tmp_path, record_property):
    owner, plan, path, config, token = evidence_case(native_plan, tmp_path)
    record_property(
        "candidate_commit", subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    )
    record_property(
        "worktree_state",
        "dirty" if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip() else "clean",
    )
    record_property("mode", "ACTUAL_CHROMIUM_PG_GIT_VERIFIER__TEST_FIXTURE_NOT_LIVE_NATIVE_AUTH_CAPACITY")
    server = subprocess.Popen(
        [
            str(ROOT / ".venv/bin/panestria"),
            "mission-control",
            "serve",
            "--config",
            str(path),
            "--assets",
            str(ASSETS),
            "--build-review-root",
            str(owner.settings.root),
        ],
        cwd=ROOT,
        env={**os.environ, "PANESTRIA_DATABASE_URL": owner.dsn},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    browser = None
    try:
        with httpx.Client(trust_env=False, timeout=2) as client:
            deadline = time.monotonic() + 10
            while True:
                assert server.poll() is None and time.monotonic() < deadline
                try:
                    if client.get(config.origin + "/").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.05)
            paired = subprocess.run(
                [str(ROOT / ".venv/bin/panestria"), "mission-control", "pair-code", "--config", str(path)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=True,
            )
            fixture = tmp_path / "browser.json"
            fixture.write_text(
                json.dumps({"origin": config.origin, "goal": plan.goal_id, "code": json.loads(paired.stdout)["code"]})
            )
            fixture.chmod(0o600)
            screenshot = tmp_path / "exact-review.png"
            browser = subprocess.Popen(
                [os.environ.get("PANESTRIA_TEST_NODE", "node"), "tests/build-review.mjs"],
                cwd=ROOT / "apps/mission-control",
                env={
                    **os.environ,
                    "PANESTRIA_BROWSER_FIXTURE": str(fixture),
                    "PANESTRIA_BROWSER_SCREENSHOT": str(screenshot),
                },
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            assert browser.stdout and browser.stdin
            ready, _, _ = select.select([browser.stdout], [], [], 45)
            assert ready, "No browser result"
            actual = browser.stdout.readline().strip()
            if actual != "APPROVED":
                browser.wait(timeout=5)
                raise AssertionError(actual + ": " + browser.stderr.read())
            review = owner.status(plan.goal_id, diff=True)
            assert review["approval"]["state"] == "APPROVED"
            assert review["task_state"] == "WAITING_APPROVAL"
            assert git(owner.settings.repository, "rev-parse", "HEAD") == review["base_commit"]
            with owner.connect() as db:
                assert db.execute("SELECT status FROM panestria.goal WHERE id=%s", (plan.goal_id,)).fetchone() == (
                    "ACTIVE",
                )
                assert db.execute(
                    "SELECT count(*) FROM panestria.task_event WHERE goal_id=%s AND kind='approval.decided'",
                    (plan.goal_id,),
                ).fetchone() == (1,)
                assert db.execute(
                    "SELECT count(*) FROM panestria.side_effect WHERE task_id=%s", (review["task_id"],)
                ).fetchone() == (0,)
            approved = review["approval"]
            merged = owner.approve(
                approved["approval_id"], approved["effect_digest"], approved["expected_version"], str(uuid4())
            )
            assert merged["task_state"] == "COMPLETED"
            assert git(owner.settings.repository, "rev-parse", "HEAD") == review["candidate_commit"]
            browser.stdin.write("{}\n")
            browser.stdin.flush()
            out, err = browser.communicate(timeout=35)
            assert browser.returncode == 0 and out.strip() == "PASS", err
            assert screenshot.is_file()
            if os.environ.get("PANESTRIA_MISSION_SCREENSHOT"):
                import shutil

                shutil.copyfile(screenshot, os.environ["PANESTRIA_MISSION_SCREENSHOT"])
    finally:
        if browser is not None and browser.poll() is None:
            browser.terminate()
            browser.communicate(timeout=10)
        if server.poll() is None:
            server.send_signal(signal.SIGINT)
        out, err = server.communicate(timeout=10)
        assert server.returncode in {0, 130}, err.decode()
        assert token.encode() not in out + err
