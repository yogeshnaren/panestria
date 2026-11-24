"""Approval expiry persists, a closed approval can be re-requested, and cancel closes pending ones.

Production-readiness plan item 1.17, on the exact local Build merge flow.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from build_support import BuildFixture, _git, _publish
from build_support import build as build
from test_aos_027a import _target

from panestria.contracts.approval import ActionPreview
from panestria.execution.build_merge import prepare_merge
from panestria.execution.outbox import EffectExecutor
from panestria.kernel.approvals import ApprovalService, ApprovalView
from panestria.kernel.cancellation import CancellationService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.policy import PolicyService
from panestria.kernel.repositories.policy import active_policy_ref
from panestria.kernel.uow import UnitOfWork


def _request(build: BuildFixture, digest: str, *, ttl_seconds: int = 600) -> ApprovalView:
    with psycopg.connect(build.task["dsn"]) as c:
        return build.service.request_merge(
            UnitOfWork(c), build.actor, build.task["task"], digest, "refs/heads/main", ttl_seconds=ttl_seconds
        )


def _decide(build: BuildFixture, view: ApprovalView, decision: str, *, version: int | None = None) -> Any:
    # Like every caller, the connection context manager commits a receipt and rolls back a denial.
    with psycopg.connect(build.task["dsn"]) as c:
        return ApprovalService().decide(
            UnitOfWork(c),
            build.actor,
            view.approval_id,
            view.effect_digest,
            view.expected_version if version is None else version,
            decision,
            str(uuid4()),
        )


def _wait_expired(build: BuildFixture, approval_id: str) -> None:
    deadline = time.monotonic() + 5
    with psycopg.connect(build.task["dsn"], autocommit=True) as c:
        while c.execute(
            "SELECT expires_at > clock_timestamp() FROM panestria.approval_request WHERE id = %s", (approval_id,)
        ).fetchone() != (False,):
            assert time.monotonic() < deadline, "approval fixture did not expire"
            time.sleep(0.02)


def _approval(build: BuildFixture, approval_id: str) -> tuple[Any, ...]:
    with psycopg.connect(build.task["dsn"]) as c:
        row = c.execute(
            "SELECT state, decided_by::text, decided_at IS NOT NULL FROM panestria.approval_request WHERE id = %s",
            (approval_id,),
        ).fetchone()
    assert row is not None
    return tuple(row)


def _events(build: BuildFixture, kind: str, approval_id: str) -> int:
    with psycopg.connect(build.task["dsn"]) as c:
        row = c.execute(
            "SELECT count(*) FROM panestria.task_event WHERE kind = %s AND payload->>'approval_id' = %s",
            (kind, approval_id),
        ).fetchone()
    assert row is not None
    return int(row[0])


def _task(build: BuildFixture) -> tuple[str, int]:
    with psycopg.connect(build.task["dsn"]) as c:
        row = c.execute("SELECT state, row_version FROM panestria.task WHERE id = %s", (build.task["task"],)).fetchone()
    assert row is not None
    return str(row[0]), int(row[1])


def test_expired_decision_persists_although_the_caller_rolls_back(build: BuildFixture) -> None:
    view = _request(build, _publish(build), ttl_seconds=1)
    _wait_expired(build, view.approval_id)

    with pytest.raises(KernelDenied, match="expired"):
        _decide(build, view, "approve")

    assert _approval(build, view.approval_id) == ("EXPIRED", None, False)
    assert _events(build, "approval.expired", view.approval_id) == 1
    assert _task(build) == ("WAITING_APPROVAL", view.expected_version + 1)
    # A repeated decision reports the stored expiry without another write.
    with pytest.raises(KernelDenied, match="expired"):
        _decide(build, view, "deny", version=view.expected_version + 1)
    assert _events(build, "approval.expired", view.approval_id) == 1
    assert _task(build) == ("WAITING_APPROVAL", view.expected_version + 1)


def test_expired_approval_can_be_re_requested_and_merged(build: BuildFixture) -> None:
    digest = _publish(build)
    expired = _request(build, digest, ttl_seconds=1)
    _wait_expired(build, expired.approval_id)
    with pytest.raises(KernelDenied, match="expired"):
        _decide(build, expired, "approve")

    renewed = _request(build, digest)

    assert renewed.approval_id != expired.approval_id and renewed.state == "PENDING"
    assert _approval(build, expired.approval_id)[0] == "EXPIRED"
    assert _decide(build, renewed, "approve").state == "APPROVED"
    with psycopg.connect(build.task["dsn"]) as c:
        effect = prepare_merge(UnitOfWork(c), build.actor, renewed.approval_id)
    EffectExecutor(lambda: psycopg.connect(build.task["dsn"]), _target(build)).dispatch(build.actor, effect.effect_id)
    assert _git(build.bare, "rev-parse", "refs/heads/main") == build.candidate


def test_pending_request_past_expiry_is_closed_by_a_re_request(build: BuildFixture) -> None:
    digest = _publish(build)
    stale = _request(build, digest, ttl_seconds=1)
    _wait_expired(build, stale.approval_id)

    renewed = _request(build, digest)

    assert renewed.state == "PENDING"
    assert _approval(build, stale.approval_id) == ("EXPIRED", None, False)
    assert _events(build, "approval.expired", stale.approval_id) == 1


def test_denied_approval_can_be_re_requested(build: BuildFixture) -> None:
    digest = _publish(build)
    denied = _request(build, digest)
    assert _decide(build, denied, "deny").state == "DENIED"

    renewed = _request(build, digest)

    assert renewed.approval_id != denied.approval_id and renewed.state == "PENDING"
    assert _approval(build, denied.approval_id)[0] == "DENIED"


def test_revoked_approval_can_be_re_requested(build: BuildFixture) -> None:
    revoked = _request(build, _publish(build))
    policies = PolicyService(build.certificates)
    with psycopg.connect(build.task["dsn"]) as c:
        uow = UnitOfWork(c)
        # A new policy revision revokes every pending approval of the project.
        review = policies.propose(uow, build.actor, build.task["task"], build.policy.model_copy(update={"version": 2}))
        policies.decide(uow, build.actor, review.review_id, review.effect_digest, "approve")
        policies.apply(uow, build.actor, review.review_id, review.effect_digest)
        current = active_policy_ref(uow, build.actor.owner_id, build.actor.project_id)
    assert _approval(build, revoked.approval_id)[0] == "REVOKED"
    assert current is not None
    document = {**revoked.preview, "policy_version": current}

    with psycopg.connect(build.task["dsn"]) as c:
        renewed = ApprovalService().request(UnitOfWork(c), build.actor, document)

    assert renewed.approval_id != revoked.approval_id and renewed.state == "PENDING"


def test_a_live_request_or_another_wait_still_blocks_a_re_request(build: BuildFixture) -> None:
    digest = _publish(build)
    pending = _request(build, digest)
    with pytest.raises(KernelDenied, match="illegal_transition"):
        _request(build, digest)
    approved = _decide(build, pending, "approve")
    assert approved.state == "APPROVED"
    with pytest.raises(KernelDenied, match="illegal_transition"):
        _request(build, digest)
    # A re-request renews the same wait; it cannot turn a merge wait into another kind.
    consent = {**pending.preview, "action_kind": "contract_consent"}
    with pytest.raises(KernelDenied, match="illegal_transition"), psycopg.connect(build.task["dsn"]) as c:
        ApprovalService().request(UnitOfWork(c), build.actor, consent)
    assert _approval(build, pending.approval_id)[0] == "APPROVED"


def test_request_rejects_an_expiry_that_has_passed(build: BuildFixture) -> None:
    digest = _publish(build)
    bundle = build.service.store.read(digest)
    document = ActionPreview(
        action_kind="merge",
        owner_id=build.actor.owner_id,
        project_id=build.actor.project_id,
        task_id=build.task["task"],
        contract_sha256=bundle.contract_sha256,
        contract_version=bundle.contract_version,
        policy_version=bundle.policy_ref,
        destination=f"refs/heads/main@{bundle.candidate_commit}",
        expected_base=bundle.base_commit,
        candidate_sha256=digest,
        required_checks=[c.check_key for c in bundle.checks if c.required],
        minimum_actor_id=build.actor.owner_id,
        expires_at=(datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
    ).model_dump(mode="json")

    with pytest.raises(KernelDenied, match="invalid_preview_expiry"), psycopg.connect(build.task["dsn"]) as c:
        ApprovalService().request(UnitOfWork(c), build.actor, document)

    assert _task(build)[0] == "VERIFYING"
    # The same preview with a future expiry is accepted.
    document["expires_at"] = (datetime.now(UTC) + timedelta(minutes=10)).isoformat()
    with psycopg.connect(build.task["dsn"]) as c:
        assert ApprovalService().request(UnitOfWork(c), build.actor, document).state == "PENDING"


def test_decision_compares_expiry_with_the_statement_clock(build: BuildFixture) -> None:
    view = _request(build, _publish(build), ttl_seconds=2)
    with psycopg.connect(build.task["dsn"]) as c:
        # This transaction starts before the expiry; now() stays at its start.
        assert c.execute(
            "SELECT expires_at > now() FROM panestria.approval_request WHERE id = %s", (view.approval_id,)
        ).fetchone() == (True,)
        _wait_expired(build, view.approval_id)
        with pytest.raises(KernelDenied, match="expired"):
            ApprovalService().decide(
                UnitOfWork(c),
                build.actor,
                view.approval_id,
                view.effect_digest,
                view.expected_version,
                "approve",
                str(uuid4()),
            )
    assert _approval(build, view.approval_id)[0] == "EXPIRED"


def test_list_pending_compares_expiry_with_the_statement_clock(build: BuildFixture) -> None:
    view = _request(build, _publish(build), ttl_seconds=2)
    with psycopg.connect(build.task["dsn"]) as c:
        listed = ApprovalService().list_pending(UnitOfWork(c), build.actor, 10)
        assert [item["approval_id"] for item in listed] == [view.approval_id]
        _wait_expired(build, view.approval_id)
        assert ApprovalService().list_pending(UnitOfWork(c), build.actor, 10) == []


@pytest.mark.parametrize("status", ["COMPLETED", "FAILED", "CANCELLED"])
def test_list_pending_hides_approvals_of_terminal_goals(build: BuildFixture, status: str) -> None:
    view = _request(build, _publish(build))
    with psycopg.connect(build.task["dsn"]) as c:
        assert [i["approval_id"] for i in ApprovalService().list_pending(UnitOfWork(c), build.actor, 10)] == [
            view.approval_id
        ]
        # A goal can end without deciding its approval, for example through an earlier release.
        c.execute("UPDATE panestria.goal SET status = %s WHERE id = %s", (status, build.task["goal"]))
        assert ApprovalService().list_pending(UnitOfWork(c), build.actor, 10) == []
        c.rollback()


def test_goal_cancel_closes_pending_approvals(build: BuildFixture) -> None:
    view = _request(build, _publish(build))
    with psycopg.connect(build.task["dsn"]) as c:
        receipt = CancellationService().cancel(
            UnitOfWork(c),
            build.actor,
            build.task["goal"],
            view.expected_version,
            "owner_requested_cancel",
            correlation_id=str(uuid4()),
        )
    assert (receipt.goal_status, receipt.task_state) == ("CANCELLED", "CANCELLED")

    assert _approval(build, view.approval_id) == ("DENIED", build.actor.owner_id, True)
    assert _events(build, "approval.closed", view.approval_id) == 1
    with psycopg.connect(build.task["dsn"]) as c:
        assert ApprovalService().list_pending(UnitOfWork(c), build.actor, 10) == []
    with pytest.raises(KernelDenied, match="decision_conflict"):
        _decide(build, view, "approve", version=receipt.task_version)
