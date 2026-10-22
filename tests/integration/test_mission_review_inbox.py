"""Canonical read-only inbox and real browser selection -> separate acceptance."""

import json
import os
import subprocess
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
import uvicorn
from build_support import build as build  # noqa: F401
from fastapi.testclient import TestClient
from plan_support import PATHS
from plan_support import r1_task as r1_task  # noqa: F401
from test_mission_build_intake import bundle, fresh
from test_mission_plan_acceptance import review_application
from test_public_plan_submission import submission as submission  # noqa: F401

from panestria.api.local_protocol import LocalHttpProtocol
from panestria.contracts.goal import contract_sha256
from panestria.contracts.plan import PlanProposal, ProjectInventory
from panestria.execution.build_intake import BuildIntakeService
from panestria.kernel.approvals import ApprovalService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.plan_store import PlanStore
from panestria.kernel.plan_submission import PlanSubmissionService
from panestria.kernel.review_inbox import review_inbox
from panestria.kernel.uow import UnitOfWork

ROOT = Path(__file__).resolve().parents[2]


def stage(f, value):
    b = f[0]
    with psycopg.connect(b.task["dsn"]) as db:
        return PlanSubmissionService().stage(
            UnitOfWork(db),
            b.actor,
            value["contract_document"],
            PlanProposal.model_validate_json(json.dumps(value["proposal"])),
            ProjectInventory.model_validate_json(json.dumps(value["inventory"])),
            "inbox-fixture:" + value["proposal"]["plan_id"],
        )


def seed(submission):
    b = submission[0]
    first, second = bundle(submission), fresh(bundle(submission))
    receipts = [stage(submission, value) for value in (first, second)]
    with psycopg.connect(b.task["dsn"]) as db:
        # Explicit fixture state, no worker or verification run is being claimed.
        db.execute("UPDATE panestria.task SET state='VERIFYING' WHERE id=%s", (b.task["task"],))
        preview = dict(
            action_kind="contract_consent",
            owner_id=b.actor.owner_id,
            project_id=b.actor.project_id,
            task_id=b.task["task"],
            contract_sha256=contract_sha256(b.contract),
            contract_version=b.contract.contract_version,
            policy_version=b.contract.autonomy_profile_ref,
            destination="PRIVATE_PREVIEW_DESTINATION_SENTINEL",
            expected_base=b.base,
            candidate_sha256="ff" * 32,
            required_checks=sorted(c.id for c in b.contract.acceptance if c.required),
            minimum_actor_id=b.actor.owner_id,
            expires_at=(datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
        )
        approval = ApprovalService().request(UnitOfWork(db), b.actor, preview)
    return receipts, approval.approval_id


@pytest.mark.parametrize("build", [PATHS], indirect=True)
def test_inbox_scope_paging_resolution_read_only_and_task_lock(submission, tmp_path):
    b = submission[0]
    plans, approval = seed(submission)
    app, _, config, token = review_application(submission, tmp_path)
    route = "/v1/activity/reviews"
    with psycopg.connect(b.task["dsn"]) as db:
        before = db.execute("SELECT count(*) FROM panestria.task_event").fetchone()
    with TestClient(app, base_url=config.origin) as client:
        bearer = {"Authorization": "Bearer " + token}
        assert client.get(route).status_code == 401
        assert client.get(route, headers={**bearer, "Origin": "https://evil.invalid"}).status_code == 403
        assert client.get(route, params={"limit": 0}, headers=bearer).status_code == 422
        expected = {("PLAN", p.plan_id) for p in plans} | {("APPROVAL", approval)}
        page = client.get(route, params={"limit": 1}, headers=bearer)
        assert page.status_code == 200, page.text
        assert (
            "PRIVATE_PREVIEW" not in page.text
            and "contract_document" not in page.text
            and "effect_digest" not in page.text
        )
        one = page.json()
        assert one["decision_authority"] == "NONE" and one["next_cursor"] and one["entries"][0]["kind"] == "APPROVAL"
        # Resolution does not invalidate a retained pagination anchor.
        with psycopg.connect(b.task["dsn"]) as db:
            preview = ApprovalService().preview(UnitOfWork(db), b.actor, approval)
            ApprovalService().decide(
                UnitOfWork(db),
                b.actor,
                approval,
                preview.effect_digest,
                preview.expected_version,
                "deny",
                "inbox-fixture-denial",
            )
        found = {(one["entries"][0]["kind"], one["entries"][0]["id"])}
        cursor = one["next_cursor"]
        for _ in range(4):
            page = client.get(route, params={"limit": 1, "after": cursor}, headers=bearer)
            assert page.status_code == 200, page.text
            value = page.json()
            found.update((e["kind"], e["id"]) for e in value["entries"])
            cursor = value["next_cursor"]
            if not cursor:
                break
        assert found == expected
        with psycopg.connect(b.task["dsn"]) as db:
            PlanStore().accept(UnitOfWork(db), b.actor, plans[0].plan_id, plans[0].effect_digest, accept_plan=True)
        current = client.get(route, headers=bearer).json()
        assert [(e["kind"], e["id"]) for e in current["entries"]] == [("PLAN", plans[1].plan_id)]
        with psycopg.connect(b.task["dsn"]) as lock:
            lock.execute("SELECT id FROM panestria.task WHERE id=%s FOR UPDATE", (b.task["task"],))
            assert client.get(route, headers=bearer).status_code == 200
        assert client.post(route, json={}, headers=bearer).status_code == 405
    with psycopg.connect(b.task["dsn"]) as db:
        # Only explicit fixture denial and acceptance wrote events; reads did not.
        assert db.execute("SELECT count(*) FROM panestria.task_event").fetchone()[0] == before[0] + 2
        with pytest.raises(KernelDenied, match="read_only_observation_required"):
            review_inbox(UnitOfWork(db), b.actor)
        other_project = str(uuid4())
        db.execute("INSERT INTO panestria.project(id,owner_id) VALUES(%s,%s)", (other_project, b.actor.owner_id))
    with psycopg.connect(b.task["dsn"]) as db:
        db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        foreign = Actor(b.actor.owner_id, other_project)
        assert review_inbox(UnitOfWork(db), foreign).entries == ()
        with pytest.raises(KernelDenied, match="not_found"):
            review_inbox(UnitOfWork(db), foreign, after="PLAN:" + plans[0].plan_id)


@pytest.mark.parametrize("build", [PATHS], indirect=True)
def test_actual_browser_discovers_plan_accepts_separately_and_refreshes_canonical_inbox(
    submission, tmp_path, monkeypatch, record_property
):
    b = submission[0]
    plans, approval = seed(submission)
    app, path, config, token = review_application(submission, tmp_path)
    original, failed = BuildIntakeService.inspect, set()

    def lose_reply(self, uow, actor, identifier):
        value = original(self, uow, actor, identifier)
        if value.plan.state == "ACCEPTED" and identifier not in failed:
            failed.add(identifier)
            raise OSError("synthetic committed acceptance reply lost")
        return value

    monkeypatch.setattr(BuildIntakeService, "inspect", lose_reply)
    record_property(
        "mode",
        "ACTUAL_CHROMIUM_HTTP_PG_GIT_CLI_PAIRING__SEEDED_VERIFYING_TASK_AND_DECLARED_INVENTORY__EXPLICIT_LOST_ACK__NO_WORKER",
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
            env={**os.environ, "PANESTRIA_DATABASE_URL": b.task["dsn"]},
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert code.returncode == 0 and token not in code.stdout, code.stderr
        fixture, screenshot = tmp_path / "browser.json", tmp_path / "inbox.png"
        fixture.write_text(
            json.dumps(
                dict(
                    origin=config.origin,
                    code=json.loads(code.stdout)["code"],
                    plan=plans[0].plan_id,
                    other=plans[1].plan_id,
                    approval=approval,
                )
            )
        )
        fixture.chmod(0o600)
        result = subprocess.run(
            [os.environ.get("PANESTRIA_TEST_NODE", "node"), "tests/review-inbox.mjs"],
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
        assert failed == {plans[0].plan_id}
        with psycopg.connect(b.task["dsn"]) as db:
            assert db.execute(
                "SELECT count(*) FROM panestria.build_plan_acceptance WHERE plan_id=%s", (plans[0].plan_id,)
            ).fetchone() == (1,)
            assert db.execute("SELECT state FROM panestria.task WHERE goal_id=%s", (plans[0].goal_id,)).fetchall() == [
                ("CREATED",),
                ("CREATED",),
            ]
            assert db.execute(
                "SELECT count(*) FROM panestria.task_attempt a JOIN panestria.task t ON t.id=a.task_id "
                "WHERE t.goal_id=%s",
                (plans[0].goal_id,),
            ).fetchone() == (0,)
        target = os.environ.get("PANESTRIA_MISSION_SCREENSHOT")
        if target:
            import shutil

            shutil.copyfile(screenshot, target)
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive()
