"""Canonical queue/observations/CLI, no worker or provider launch in this component."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from test_native_plan_execution import native_plan as native_plan  # noqa: F401
from test_native_plan_execution import prepared_plan as prepared_plan  # noqa: F401
from test_owner_build_cli import owner_cli as owner_cli  # noqa: F401
from typer.testing import CliRunner

from panestria.cli.main import app
from panestria.contracts.background import BackgroundEnqueue
from panestria.kernel.background import BackgroundWorkService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.quota import QuotaService
from panestria.kernel.uow import UnitOfWork
from quota_support import observation


def request_for(owner, plan, **policy_changes):
    now = datetime.now(UTC) - timedelta(seconds=1)
    account = str(uuid4())
    body = {
        "schema_version": 1,
        "item_id": str(uuid4()),
        "plan_id": plan.plan_id,
        "expected_plan_sha256": plan.sha256(),
        "policy": {
            "policy_id": str(uuid4()),
            "owner_id": owner.actor.owner_id,
            "project_id": owner.actor.project_id,
            "quota_windows": [
                {"provider": "claude-subscription", "account_ref": account, "window_ref": "session"},
                {"provider": "claude-subscription", "account_ref": account, "window_ref": "weekly"},
            ],
            "expires_at": (now + timedelta(hours=1)).isoformat(),
            **policy_changes,
        },
    }
    return BackgroundEnqueue.model_validate_json(json.dumps(body))


def cli(f, *args, expected=0):
    result = CliRunner().invoke(app, ["background", args[0], "--config", str(f.config), *args[1:]])
    assert result.exit_code == expected, (result.stdout, result.exception)
    return json.loads(result.stdout)


def record(owner, task, scope, **changes):
    data = observation(scope=scope.model_dump(mode="json"), **changes)
    with owner.connect() as c:
        QuotaService().record(UnitOfWork(c), owner.actor, task, data)
    return data


def test_actual_owner_queue_review_quota_reserve_unknown_billing_and_withdraw_are_not_dispatch(prepared_plan):
    f, owner, _, plan = prepared_plan
    path = f.config.parent / "background.json"
    drafted = cli(f, "draft", plan.plan_id, str(uuid4()), "--output", str(path))
    assert drafted["status"] == "DRAFTED" and drafted["billing"] == "UNKNOWN"
    request = BackgroundEnqueue.model_validate_json(path.read_bytes())
    assert request.policy.billing is None and request.policy.allow_unknown_quota is False
    review = cli(f, "prepare", "--request", str(path))
    assert review["status"] == "REVIEW_ONLY" and review["eligibility"]["scheduling_candidate"] is False
    assert "no_extra_spend_boundary_unconfirmed" in review["eligibility"]["waiting_reasons"]
    cli(f, "enqueue", "--request", str(path), "ff" * 32, "--accept-background-policy", expected=1)
    queued = cli(f, "enqueue", "--request", str(path), request.policy.sha256(), "--accept-background-policy")
    assert queued["status"] == "QUEUED" and queued["execution_authority"] == "NONE"
    replay = cli(f, "enqueue", "--request", str(path), request.policy.sha256(), "--accept-background-policy")
    assert replay["replayed"] and replay["event_seq"] == queued["event_seq"]
    for scope in request.policy.quota_windows:
        record(owner, plan.nodes[-1].task_id, scope, remaining="40")
    view = cli(f, "list")["items"][0]
    assert view["waiting_reasons"] == ["no_extra_spend_boundary_unconfirmed"]
    assert view["seconds_to_reported_reset"] > 0
    assert all(o["source"] == "OWNER_REPORTED" and o["effective_remaining"] == "40" for o in view["quota_observations"])
    withdrawn = cli(f, "withdraw", request.item_id, queued["binding_sha256"])
    assert cli(f, "withdraw", request.item_id, queued["binding_sha256"])["event_seq"] == withdrawn["event_seq"]
    assert cli(f, "list")["items"][0]["status"] == "WITHDRAWN"
    assert cli(f, "show", request.item_id)["status"] == "WITHDRAWN"
    # Renewal is a new exact owner review after explicit withdrawal, not mutation
    # of the original policy/observation freshness or an automatic worker retry.
    newer = BackgroundEnqueue.model_validate_json(
        json.dumps(
            {
                **request.model_dump(mode="json"),
                "item_id": str(uuid4()),
                "policy": {**request.policy.model_dump(mode="json"), "policy_id": str(uuid4())},
            }
        )
    )
    path.write_text(newer.model_dump_json())
    renewed = cli(f, "enqueue", "--request", str(path), newer.policy.sha256(), "--accept-background-policy")
    assert renewed["event_seq"] != queued["event_seq"] and not renewed["replayed"]
    assert cli(f, "show", request.item_id)["status"] == "WITHDRAWN"
    with owner.connect() as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.task_attempt a JOIN panestria.task t ON t.id=a.task_id WHERE t.goal_id=%s",
            (plan.goal_id,),
        ).fetchone() == (0,)
        assert c.execute("SELECT DISTINCT state FROM panestria.task WHERE goal_id=%s", (plan.goal_id,)).fetchall() == [
            ("CREATED",)
        ]
        assert c.execute(
            "SELECT count(*) FROM panestria.task_event WHERE goal_id=%s AND kind='background.queued'", (plan.goal_id,)
        ).fetchone() == (1,)
    assert f.transport.launches == 0


def test_actual_queue_atomic_race_and_scoped_candidate_reserve_foreground_guards(prepared_plan, native_plan):
    f, owner, _, plan = prepared_plan
    request = request_for(owner, plan)
    billing = {
        "reported_by": owner.actor.owner_id,
        "account_ref": request.policy.quota_windows[0].account_ref,
        "observed_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
        "usage_credits_enabled": False,
    }
    request = BackgroundEnqueue.model_validate_json(
        json.dumps(
            {
                **request.model_dump(mode="json"),
                "policy": {
                    **request.policy.model_dump(mode="json"),
                    "billing": billing,
                },
            }
        )
    )

    def enqueue():
        with owner.connect() as c:
            return BackgroundWorkService().enqueue(
                UnitOfWork(c), owner.actor, request, request.policy.sha256(), accept_background_policy=True
            )

    # Actual rollback has no queued fact; no row/counter manufactured as success.
    with owner.connect() as c:
        BackgroundWorkService().enqueue(
            UnitOfWork(c), owner.actor, request, request.policy.sha256(), accept_background_policy=True
        )
        c.rollback()
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = list(pool.map(lambda _: enqueue(), range(2)))
    assert sorted([a["replayed"], b["replayed"]]) == [False, True] and a["event_seq"] == b["event_seq"]
    service = BackgroundWorkService()
    with owner.connect() as c:
        binding = service.prepare(UnitOfWork(c), owner.actor, request)
        assert (
            "quota_unknown_requires_explicit_best_effort_policy"
            in service.inspect(UnitOfWork(c), owner.actor, binding)["waiting_reasons"]
        )
    unknown_request = BackgroundEnqueue.model_validate_json(
        json.dumps(
            {
                **request.model_dump(mode="json"),
                "policy": {
                    **request.policy.model_dump(mode="json"),
                    "allow_unknown_quota": True,
                },
            }
        )
    )
    with owner.connect() as c:
        proposed = service.prepare(UnitOfWork(c), owner.actor, unknown_request)
        best_effort = service.inspect(UnitOfWork(c), owner.actor, proposed)
        assert best_effort["scheduling_candidate"] and best_effort["seconds_to_reported_reset"] is None
        assert best_effort["no_extra_spend_runtime_qualification"] == "NOT_ASSESSED"
        # A prepared scheduling candidate is not queued policy consent/dispatch.
        assert best_effort["execution_authority"] == "NONE"
    for scope in request.policy.quota_windows:
        record(owner, plan.nodes[-1].task_id, scope, remaining="40")
    with owner.connect() as c:
        view = service.inspect(UnitOfWork(c), owner.actor, binding)
        assert view["scheduling_candidate"] and view["runtime_qualification"] == "NOT_ASSESSED"
        assert view["execution_authority"] == "NONE" and view["billing_source"] == "OWNER_REPORTED"
    # Independent weekly reserve blocks despite a positive session reading.
    record(owner, plan.nodes[-1].task_id, request.policy.quota_windows[1], remaining="20")
    with owner.connect() as c:
        assert "regular_use_reserve" in service.inspect(UnitOfWork(c), owner.actor, binding)["waiting_reasons"]
    record(owner, plan.nodes[-1].task_id, request.policy.quota_windows[1], remaining="40")
    record(owner, plan.nodes[-1].task_id, request.policy.quota_windows[0], remaining="0")
    record(owner, plan.nodes[-1].task_id, request.policy.quota_windows[0], remaining=None)
    with owner.connect() as c:
        prior_zero = service.inspect(UnitOfWork(c), owner.actor, proposed)
        assert "observed_exhaustion_wait_for_new_evidence_or_reset" in prior_zero["waiting_reasons"]
        assert prior_zero["retained_exhaustion_observations"]
        assert not prior_zero["scheduling_candidate"]  # even explicit best effort cannot erase exhaustion
    record(owner, plan.nodes[-1].task_id, request.policy.quota_windows[0], remaining="40")
    with owner.connect() as c:
        assert service.inspect(UnitOfWork(c), owner.actor, binding)["scheduling_candidate"]
    with owner.connect() as c:
        with pytest.raises(KernelDenied, match="not_found"):
            service.prepare(UnitOfWork(c), Actor(str(uuid4()), str(uuid4())), request)
    from panestria.kernel.build import BuildEvidenceService
    from panestria.kernel.scheduler import Scheduled, Scheduler
    from panestria.resources.hardware import HardwareProbe

    with owner.connect() as c:
        claimed = Scheduler().claim_ready(
            UnitOfWork(c),
            owner.actor,
            plan.plan_id,
            HardwareProbe(owner.settings.skills_archive).collect_cpu(),
            BuildEvidenceService(owner.reports),
        )
        assert isinstance(claimed, Scheduled)
    with owner.connect() as c:
        held = service.inspect(UnitOfWork(c), owner.actor, binding)
        assert "foreground_or_held_capacity_reserved" in held["waiting_reasons"]
        assert not held["scheduling_candidate"]
    # A lease is real but was not dispatched; no process/return proof is invented.
    assert native_plan[3]["launches"] == f.transport.launches == 0
