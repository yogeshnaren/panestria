"""AI-P2e / ADR 0014: real queue eligibility paces toward a reported reset."""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from test_background_queue import record, request_for
from test_native_plan_execution import native_plan as native_plan  # noqa: F401
from test_native_plan_execution import prepared_plan as prepared_plan  # noqa: F401
from test_owner_build_cli import owner_cli as owner_cli  # noqa: F401

from panestria.contracts.background import BackgroundEnqueue
from panestria.kernel.background import BackgroundWorkService
from panestria.kernel.uow import UnitOfWork


def candidate(owner, plan):
    request = request_for(owner, plan)
    billing = {
        "reported_by": owner.actor.owner_id,
        "account_ref": request.policy.quota_windows[0].account_ref,
        "observed_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
        "usage_credits_enabled": False,
    }
    policy = {**request.policy.model_dump(mode="json"), "billing": billing}
    return BackgroundEnqueue.model_validate_json(json.dumps({**request.model_dump(mode="json"), "policy": policy}))


def reasons(owner, request):
    service = BackgroundWorkService()
    with owner.connect() as c:
        binding = service.prepare(UnitOfWork(c), owner.actor, request)
        return service.inspect(UnitOfWork(c), owner.actor, binding)["waiting_reasons"]


def test_ai_p2e_projected_use_holds_work_until_the_urgency_window(prepared_plan, native_plan):
    f, owner, _, plan = prepared_plan
    task = plan.nodes[-1].task_id
    now = datetime.now(UTC) - timedelta(seconds=1)
    far, near = (now + timedelta(hours=30)).isoformat(), (now + timedelta(minutes=45)).isoformat()
    request = candidate(owner, plan)
    session, weekly = request.policy.quota_windows
    record(owner, task, weekly, remaining="90", resets_at=far)
    # Owner example: 40% left, falling 1%/hour, 30 h to reset; the 20% reserve
    # plus 30% projected regular use exceeds what remains.
    record(owner, task, session, remaining="41", observed_at=(now - timedelta(hours=1)).isoformat(), resets_at=far)
    record(owner, task, session, remaining="40", resets_at=far)
    assert reasons(owner, request) == ["pacing_projected_regular_use_before_reset"]
    # A report seconds later is not rate evidence on its own.
    record(owner, task, session, remaining="39", resets_at=far)
    assert reasons(owner, request) == []
    # Inside the urgency window the projection no longer holds work back.
    near_request = candidate(owner, plan)
    session, weekly = near_request.policy.quota_windows
    record(owner, task, weekly, remaining="90", resets_at=near)
    record(owner, task, session, remaining="41", observed_at=(now - timedelta(hours=1)).isoformat(), resets_at=near)
    record(owner, task, session, remaining="40", resets_at=near)
    assert reasons(owner, near_request) == []


def test_ai_p2e_old_reports_and_unknown_never_count_as_headroom(prepared_plan, native_plan):
    f, owner, _, plan = prepared_plan
    task = plan.nodes[-1].task_id
    now = datetime.now(UTC) - timedelta(seconds=1)
    request = candidate(owner, plan)
    for scope in request.policy.quota_windows:
        record(
            owner,
            task,
            scope,
            remaining="90",
            observed_at=(now - timedelta(hours=7)).isoformat(),
            fresh_for_seconds=86400,
        )
    waiting = reasons(owner, request)
    assert "quota_observation_older_than_background_limit" in waiting
    assert "quota_unknown_requires_explicit_best_effort_policy" in waiting
    for scope in request.policy.quota_windows:
        record(owner, task, scope, source="UNKNOWN", remaining=None, unit=None, observation_id=str(uuid4()))
    assert "quota_unknown_requires_explicit_best_effort_policy" in reasons(owner, request)
