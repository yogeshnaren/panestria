"""Confirmed rollback is correctable; actual committed lost acknowledgment stays unknown."""

import copy
import json
import os
import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import psycopg
import pytest
import uvicorn
from build_support import build as build  # noqa: F401
from fastapi.testclient import TestClient
from plan_support import PATHS
from plan_support import r1_task as r1_task  # noqa: F401
from test_mission_build_intake import application, bundle, counts
from test_public_plan_submission import submission as submission  # noqa: F401

from panestria.api.local_protocol import LocalHttpProtocol
from panestria.api.routes import build_intake

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("build", [PATHS], indirect=True)
def test_precommit_denials_have_marker_but_lost_commit_acknowledgment_never_does(submission, tmp_path, monkeypatch):
    app, _, config, token = application(submission, tmp_path)
    before = counts(submission)
    route = "/v1/mission/build/plans"
    with TestClient(app, base_url=config.origin) as client:
        headers = {"Authorization": "Bearer " + token}
        request = {**bundle(submission), "public_plan": True}
        bad = copy.deepcopy(request)
        bad["proposal"]["inventory_sha256"] = "ff" * 32
        denied = client.post(route, json=bad, headers=headers)
        assert denied.status_code == 409 and denied.headers["X-Panestria-Mutation"] == "NOT_COMMITTED"
        bad = copy.deepcopy(request)
        bad["contract_document"]["unknown_field"] = "PUBLIC_SYNTHETIC_DO_NOT_ECHO"
        invalid = client.post(route, json=bad, headers=headers)
        assert invalid.status_code == 422 and invalid.headers["X-Panestria-Mutation"] == "NOT_COMMITTED"
        assert "PUBLIC_SYNTHETIC_DO_NOT_ECHO" not in invalid.text
        assert counts(submission) == before
        actual = build_intake.open_database

        @contextmanager
        def lost_commit_reply(dsn):
            with actual(dsn) as db:
                yield db
            # Actual canonical COMMIT completed. Only the acknowledgment is lost.
            raise psycopg.OperationalError("synthetic commit acknowledgment lost")

        monkeypatch.setattr(build_intake, "open_database", lost_commit_reply)
        unknown = client.post(route, json=request, headers=headers)
        assert unknown.status_code == 503 and "X-Panestria-Mutation" not in unknown.headers
        monkeypatch.setattr(build_intake, "open_database", actual)
        view = client.get(route + "/" + request["proposal"]["plan_id"], headers=headers)
        assert view.status_code == 200 and view.json()["plan"]["state"] == "PROPOSED"
        assert counts(submission) == tuple(n + delta for n, delta in zip(before, (1, 1, 0, 0, 0), strict=True))
        assert client.post(route, json=request, headers=headers).json() == view.json()


@pytest.mark.parametrize("build", [PATHS], indirect=True)
def test_browser_corrects_rejected_bundle_with_same_plan_id_without_unknown_retry(
    submission, tmp_path, record_property
):
    app, path, config, token = application(submission, tmp_path)
    record_property(
        "mode", "ACTUAL_CHROMIUM_HTTP_PG_GIT_CLI_PAIRING__DECLARED_INVENTORY__REAL_HASH_DENIAL__NO_EXECUTION"
    )
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
            env={**os.environ, "PANESTRIA_DATABASE_URL": submission[0].task["dsn"]},
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert code.returncode == 0 and token not in code.stdout, code.stderr
        fixture, screenshot = tmp_path / "browser.json", tmp_path / "rejection.png"
        fixture.write_text(
            json.dumps(dict(origin=config.origin, code=json.loads(code.stdout)["code"], bundle=bundle(submission)))
        )
        fixture.chmod(0o600)
        result = subprocess.run(
            [os.environ.get("PANESTRIA_TEST_NODE", "node"), "tests/intake-rejections.mjs"],
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
        with psycopg.connect(submission[0].task["dsn"]) as db:
            goal = submission[2].goal_id
            assert db.execute("SELECT count(*) FROM panestria.build_plan WHERE goal_id=%s", (goal,)).fetchone() == (1,)
            assert db.execute(
                "SELECT count(*) FROM panestria.task_event WHERE goal_id=%s AND kind='build.plan.proposed'", (goal,)
            ).fetchone() == (1,)
            assert db.execute("SELECT count(*) FROM panestria.task WHERE goal_id=%s", (goal,)).fetchone() == (0,)
        target = os.environ.get("PANESTRIA_MISSION_SCREENSHOT")
        if target:
            import shutil

            shutil.copyfile(screenshot, target)
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive()
