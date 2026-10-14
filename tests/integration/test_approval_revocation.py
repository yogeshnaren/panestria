"""Policy revocation preserves the original decision and fences a claimed merge."""

from __future__ import annotations

import psycopg
import pytest
from build_support import BuildFixture, _git, _publish
from build_support import build as build
from test_aos_027a import _approve, _target

from panestria.kernel.effects import SideEffectService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.uow import UnitOfWork


def test_current_policy_is_rechecked_after_dispatch_claim(build: BuildFixture) -> None:
    from panestria.kernel.policy import PolicyService

    digest = _publish(build)
    effect = _approve(build, digest)
    with psycopg.connect(build.task["dsn"]) as c:
        uow = UnitOfWork(c)
        claim = SideEffectService().claim(uow, build.actor, effect)
        c.commit()
        original = c.execute(
            "SELECT decided_at,decided_by FROM panestria.approval_request"
            " WHERE id=(SELECT approval_request_id FROM panestria.side_effect WHERE id=%s)",
            (effect,),
        ).fetchone()
        c.commit()
        policies = PolicyService(build.certificates)
        proposed = build.policy.model_copy(
            update={
                "version": 2,
                "trust": build.policy.trust.model_copy(
                    update={
                        "version": 2,
                        "allowed_actions": [a for a in build.policy.trust.allowed_actions if a != "merge"],
                    }
                ),
            }
        )
        review = policies.propose(uow, build.actor, build.task["task"], proposed)
        c.commit()
        policies.decide(uow, build.actor, review.review_id, review.effect_digest, "approve")
        c.commit()
        policies.apply(uow, build.actor, review.review_id, review.effect_digest)
        c.commit()
        after = c.execute(
            "SELECT state,decided_at,decided_by,revoked_by::text,revocation_policy_version"
            " FROM panestria.approval_request WHERE id=(SELECT approval_request_id"
            " FROM panestria.side_effect WHERE id=%s)",
            (effect,),
        ).fetchone()
        assert after == ("REVOKED", *original, build.actor.owner_id, 2)
        with pytest.raises(psycopg.Error, match="immutable"), c.transaction():
            c.execute(
                "UPDATE panestria.approval_request SET decided_at=clock_timestamp()"
                " WHERE id=(SELECT approval_request_id FROM panestria.side_effect WHERE id=%s)",
                (effect,),
            )
    with pytest.raises(KernelDenied, match="policy_mismatch"):
        _target(build).dispatch(claim)
    assert _git(build.bare, "rev-parse", "refs/heads/main") == build.base
