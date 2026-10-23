"""Mobile Chromium/CLI/TLS/PG journey; simulated device and native provider only."""

import json
import os
import select
import shutil
import signal
import ssl
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx2 as httpx
from test_native_plan_execution import native_plan as native_plan  # noqa: F401
from test_native_plan_execution import owner_cli as owner_cli  # noqa: F401
from test_native_plan_execution import prepared_plan as prepared_plan  # noqa: F401
from test_private_phone import cli, configuration

from panestria.config_phone import load_phone_settings
from panestria.kernel.goals import GoalService
from panestria.kernel.uow import UnitOfWork

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "apps/mission-control/dist"


def test_mobile_observer_build_attention_stop_restart_offline_background_and_revocation(
    native_plan, tmp_path, monkeypatch, record_property
):
    owner, runner, plan, state = native_plan
    record_property(
        "candidate_commit", subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    )
    record_property(
        "worktree_state",
        "dirty" if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip() else "clean",
    )
    record_property("mode", "MOBILE_EMULATION_REAL_TLS_PG_GIT__FIXTURE_NATIVE_AUTH_CAPACITY_NOT_REAL_PHONE")
    monkeypatch.setenv("PANESTRIA_DATABASE_URL", owner.dsn)
    path, config, token = configuration({"owner": owner.actor.owner_id, "project": owner.actor.project_id}, tmp_path)
    doc = json.loads(path.read_text()) | {"build_evidence_store": str(owner.reports.root)}
    path.write_text(json.dumps(doc))
    config, _ = load_phone_settings(path)
    with owner.connect() as c:
        contract = c.execute(
            "SELECT body FROM panestria.goal_contract WHERE goal_id=%s ORDER BY version DESC LIMIT 1", (plan.goal_id,)
        ).fetchone()[0]
        private = json.loads(json.dumps(contract))
        private.update(goal_id=str(uuid4()), privacy_class="INTERNAL", intent="PHONE_PRIVATE_CONTENT_SENTINEL")
        GoalService().submit(UnitOfWork(c), owner.actor, private, "phone-private-test")
    code = cli(path, "pair-code")["code"]
    fixture = tmp_path / "browser.json"
    fixture.write_text(
        json.dumps(
            {
                "origin": config.origin,
                "goal": plan.goal_id,
                "privateGoal": private["goal_id"],
                "code": code,
                "store": str(owner.reports.root),
                "privateDescription": contract["acceptance"][0]["description"],
            }
        )
    )
    fixture.chmod(0o600)
    env = {**os.environ, "PANESTRIA_DATABASE_URL": owner.dsn}
    processes = []
    browser = None

    def start():
        process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "from panestria.cli.main import app;app()",
                "phone",
                "serve",
                "--config",
                str(path),
                "--assets",
                str(ASSETS),
            ],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        processes.append(process)
        # Verify TLS with this fixture's CA independently of the UX browser's
        # explicit self-signed-certificate bypass. No OS/phone trust is installed.
        with httpx.Client(
            verify=ssl.create_default_context(cafile=str(config.certificate_file)), trust_env=False, timeout=1
        ) as client:
            deadline = time.monotonic() + 20
            while True:
                assert process.poll() is None and time.monotonic() < deadline
                try:
                    if client.get(config.origin + "/").status_code == 200:
                        return process
                except httpx.HTTPError:
                    pass
                time.sleep(0.05)

    def stop(process):
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
        try:
            out, err = process.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            out, err = process.communicate(timeout=5)
        assert token.encode() not in out + err

    try:
        server = start()
        screenshot = tmp_path / "phone-observer.png"
        browser = subprocess.Popen(
            [os.environ.get("PANESTRIA_TEST_NODE", "node"), "tests/phone-observer.mjs"],
            cwd=ROOT / "apps/mission-control",
            env={**env, "PANESTRIA_BROWSER_FIXTURE": str(fixture), "PANESTRIA_BROWSER_SCREENSHOT": str(screenshot)},
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert browser.stdout and browser.stdin

        def wait(expected):
            ready, _, _ = select.select([browser.stdout], [], [], 55)
            assert ready, f"no browser {expected}"
            actual = browser.stdout.readline().strip()
            if actual != expected:
                browser.wait(timeout=5)
                raise AssertionError(actual + ": " + browser.stderr.read())

        def advance():
            browser.stdin.write("{}\n")
            browser.stdin.flush()

        wait("RUN")
        result = runner.run(plan.plan_id, public_subscription_run=True)
        record_property("run_result", json.dumps(result))
        assert result["status"] == "WAITING_APPROVAL", result
        assert state["launches"] == 2  # explicit fixture; no inference
        advance()
        wait("STOP")
        with owner.connect() as c:
            before = c.execute("SELECT count(*) FROM panestria.task_event").fetchone()
        stop(server)
        advance()
        wait("RESTART")
        start()  # same original canonical grant, no renewal or re-pairing
        advance()
        wait("REVOKE")
        device = cli(path, "devices")["devices"]
        assert len(device) == 1
        assert cli(path, "revoke", device[0]["session_id"], "--confirm-revocation")["state"] == "REVOKED"
        advance()
        wait("PASS")
        _, err = browser.communicate(timeout=10)
        assert browser.returncode == 0, err
        with owner.connect() as c:
            assert c.execute("SELECT count(*) FROM panestria.task_event").fetchone() == before
        assert screenshot.is_file()
        if os.environ.get("PANESTRIA_MISSION_SCREENSHOT"):
            shutil.copyfile(screenshot, os.environ["PANESTRIA_MISSION_SCREENSHOT"])
    finally:
        if browser is not None and browser.poll() is None:
            browser.terminate()
            browser.communicate(timeout=10)
        for process in processes:
            stop(process)
