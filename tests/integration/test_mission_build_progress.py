"""Actual browser/PG/Git/verifier; native/auth/capacity remain explicit nonlive fixtures."""

import json
import os
import select
import signal
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from test_mission_control_browser import configure
from test_native_plan_execution import native_plan as native_plan  # noqa: F401
from test_native_plan_execution import owner_cli as owner_cli  # noqa: F401
from test_native_plan_execution import prepared_plan as prepared_plan  # noqa: F401

from panestria.api.activity_server import build_activity_app
from panestria.api.mission_web import mount_mission_control
from panestria.config import Settings
from panestria.kernel.build import BuildEvidenceStore
from panestria.kernel.errors import KernelDenied

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "apps/mission-control/dist"


def test_actual_browser_checks_require_current_protected_bytes_and_never_grant_acceptance(
    native_plan, tmp_path, record_property
):
    owner, runner, plan, state = native_plan
    record_property(
        "candidate_commit", subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    )
    record_property(
        "worktree_state",
        "dirty" if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip() else "clean",
    )
    record_property("mode", "ACTUAL_CHROMIUM_PG_GIT_VERIFIER__TEST_FIXTURE_NOT_LIVE_NATIVE_AUTH_CAPACITY")
    path, config, token = configure({"owner": owner.actor.owner_id, "project": owner.actor.project_id}, tmp_path)
    with owner.connect() as c:
        document = c.execute(
            "SELECT body FROM panestria.goal_contract WHERE goal_id=%s ORDER BY version DESC LIMIT 1", (plan.goal_id,)
        ).fetchone()[0]
    omitted_description = document["acceptance"][0]["description"]
    store = owner.reports.root
    # Explicit read-only opening creates no store and cannot publish a report.
    with pytest.raises(KernelDenied, match="existing_private_evidence_store_required"):
        BuildEvidenceStore(tmp_path / "missing", read_only=True)
    assert not (tmp_path / "missing").exists()
    reader = BuildEvidenceStore(store, read_only=True)
    originals = {p.name: p.read_bytes() for p in store.iterdir()}
    with pytest.raises(KernelDenied, match="evidence_store_read_only"):
        reader.write_report(b"never published")
    assert {p.name: p.read_bytes() for p in store.iterdir()} == originals
    app = build_activity_app(config, Settings(database_url=owner.dsn).validate_profile(), token)
    route = f"/v1/activity/goals/{plan.goal_id}/build-progress"
    bearer = {"Authorization": "Bearer " + token}
    with TestClient(app, base_url=config.origin) as client:
        assert client.get(route).status_code == 401
        assert client.get(route, headers=bearer).status_code == 409
    # Different factory: TestClient closed its health service; no session or work grant changed.
    app = build_activity_app(config, Settings(database_url=owner.dsn).validate_profile(), token)
    mount_mission_control(app, config, token, ASSETS, build_evidence_store=store)
    with TestClient(app, base_url=config.origin) as client:
        initial = client.get(route, headers=bearer)
        assert initial.status_code == 200, initial.text
        initial = initial.json()
        assert initial["required_checks_passed"] == 0 and initial["required_checks_total"] > 0
        assert initial["dispatch_authority"] == "NONE" and initial["release_acceptance"] == "NOT_ASSESSED"
        assert client.get(f"/v1/activity/goals/{uuid4()}/build-progress", headers=bearer).status_code == 404
        assert all(
            x not in json.dumps(initial) for x in ("description", "preview", "intent", str(store), "native_config")
        )
    env = {**os.environ, "PANESTRIA_DATABASE_URL": owner.dsn}
    server = subprocess.Popen(
        [
            str(ROOT / ".venv/bin/python"),
            "-m",
            "panestria.cli.main",
            "mission-control",
            "serve",
            "--config",
            str(path),
            "--assets",
            str(ASSETS),
            "--build-evidence-store",
            str(store),
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    browser = None
    try:
        with httpx.Client(trust_env=False, timeout=1) as client:
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
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert paired.returncode == 0, paired.stderr
            fixture = tmp_path / "browser.json"
            fixture.write_text(
                json.dumps(
                    {
                        "origin": config.origin,
                        "goal": plan.goal_id,
                        "code": json.loads(paired.stdout)["code"],
                        "total": initial["required_checks_total"],
                        "store": str(store),
                        "privateDescription": omitted_description,
                    }
                )
            )
            fixture.chmod(0o600)
            screenshot = tmp_path / "build-progress.png"
            browser = subprocess.Popen(
                [os.environ.get("PANESTRIA_TEST_NODE", "node"), "tests/build-progress.mjs"],
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

            def wait(expected):
                ready, _, _ = select.select([browser.stdout], [], [], 65)
                assert ready, f"no browser {expected}"
                actual = browser.stdout.readline().strip()
                if actual != expected:
                    browser.wait(timeout=5)
                    raise AssertionError(actual + ": " + browser.stderr.read())

            def advance():
                browser.stdin.write("{}\n")
                browser.stdin.flush()

            wait("RUN")
            with owner.connect() as c:
                before = c.execute(
                    "SELECT count(*) FROM panestria.task_event WHERE goal_id=%s", (plan.goal_id,)
                ).fetchone()
            result = runner.run(plan.plan_id, public_subscription_run=True)
            record_property("run_result", json.dumps(result))
            assert result["status"] == "WAITING_APPROVAL", json.dumps(result)
            assert state["launches"] == 2  # explicit fixture, never a real provider call
            advance()
            wait("CORRUPT")
            before_corrupt = client.get(config.origin + route, headers=bearer).json()
            digest = before_corrupt["final_evidence_sha256"]
            assert digest
            with owner.connect() as c:
                after = c.execute(
                    "SELECT count(*) FROM panestria.task_event WHERE goal_id=%s", (plan.goal_id,)
                ).fetchone()
                assert after[0] > before[0]
            changed = store / digest
            changed.chmod(0o600)
            changed.write_bytes(b"corrupt synthetic evidence")
            advance()
            wait("PASS")
            browser.communicate(timeout=10)
            assert browser.returncode == 0
            with owner.connect() as c:
                assert (
                    c.execute("SELECT count(*) FROM panestria.task_event WHERE goal_id=%s", (plan.goal_id,)).fetchone()
                    == after
                )
            final = client.get(config.origin + route, headers=bearer).json()
            assert final["required_checks_passed"] == 0 and final["final_evidence_sha256"] is None
            assert final["goal_status"] == "ACTIVE" and final["release_acceptance"] == "NOT_ASSESSED"
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
