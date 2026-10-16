"""Actual disposable PG owner-reviewed web-policy persistence, not egress certification."""

from uuid import uuid4

import psycopg
import pytest

from panestria.contracts.policy import PolicyRequest, PrivacyAxis
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.policy import PolicyService
from panestria.kernel.repositories.policy import active_policy_ref, require_current_policy
from panestria.kernel.uow import UnitOfWork
from panestria.policy.engine import PolicyEngine
from panestria.policy.profiles import CertificateStore


def test_web_destination_needs_owner_digest_review_persists_and_revokes_old_approvals(r1_task, tmp_path):
    actor = Actor(r1_task["owner"], r1_task["project"])
    service = PolicyService(CertificateStore(tmp_path, {}))
    with psycopg.connect(r1_task["dsn"]) as connection:
        uow = UnitOfWork(connection)
        first = service.initialize(uow, actor, r1_task["task"])
        connection.commit()
        old_ref = active_policy_ref(uow, actor.owner_id, actor.project_id)
        pending_id = str(uuid4())
        connection.execute(
            "INSERT INTO panestria.approval_request"
            " (id,goal_id,task_id,owner_id,project_id,minimum_actor_id,action_kind,effect_digest,policy_version,"
            " state,expires_at,preview) VALUES (%s,%s,%s,%s,%s,%s,'merge',%s,%s,'PENDING',"
            " clock_timestamp()+interval '1 hour','{}'::jsonb)",
            (
                pending_id,
                r1_task["goal"],
                r1_task["task"],
                actor.owner_id,
                actor.project_id,
                actor.owner_id,
                "ef" * 32,
                old_ref,
            ),
        )
        connection.commit()
        proposed = first.model_copy(
            update={"version": 2, "privacy": PrivacyAxis(version=2, cloud_destinations=["public-web"])}
        )
        review = service.propose(uow, actor, r1_task["task"], proposed)
        connection.commit()
        assert service.get(uow, actor).sha256() == first.sha256()
        with pytest.raises(KernelDenied, match="review_mismatch"), connection.transaction():
            service.apply(uow, actor, review.review_id, review.effect_digest)
        with pytest.raises(KernelDenied, match="not_found"), connection.transaction():
            service.decide(
                uow, Actor(str(uuid4()), actor.project_id), review.review_id, review.effect_digest, "approve"
            )
        with pytest.raises(KernelDenied, match="review_mismatch"), connection.transaction():
            service.decide(uow, actor, review.review_id, "00" * 32, "approve")
        connection.commit()
        service.decide(uow, actor, review.review_id, review.effect_digest, "approve")
        connection.commit()
        second = service.apply(uow, actor, review.review_id, review.effect_digest)
        connection.commit()
        assert second.privacy.cloud_destinations == ["public-web"]
        assert second.trust == first.trust and second.autonomy == first.autonomy
        assert service.get(uow, actor).sha256() == proposed.sha256()
        assert connection.execute(
            "SELECT state FROM panestria.approval_request WHERE id=%s", (pending_id,)
        ).fetchone() == ("REVOKED",)
        with pytest.raises(KernelDenied, match="policy_mismatch"), connection.transaction():
            require_current_policy(uow, actor, old_ref)
        request = PolicyRequest(
            owner_id=actor.owner_id,
            project_id=actor.project_id,
            action="external-send",
            label="PUBLIC",
            destination="public-web",
            effect_digest="cd" * 32,
        )
        # A privacy grant alone never certifies or expands the synthetic runtime.
        assert PolicyEngine().authorize(request, second).outcome == "DENY"
        connection.commit()
        revoked = second.model_copy(update={"version": 3, "privacy": PrivacyAxis(version=3)})
        change = service.propose(uow, actor, r1_task["task"], revoked)
        connection.commit()
        service.decide(uow, actor, change.review_id, change.effect_digest, "approve")
        connection.commit()
        third = service.apply(uow, actor, change.review_id, change.effect_digest)
        connection.commit()
        assert third.privacy.cloud_destinations == [] and third.sha256() == revoked.sha256()
        assert service.get(uow, actor).sha256() == third.sha256()
        assert connection.execute(
            "SELECT count(*) FROM panestria.project_policy_revision WHERE project_id=%s", (actor.project_id,)
        ).fetchone() == (3,)
