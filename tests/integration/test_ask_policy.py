"""Which project policy local Ask runs under, on real PostgreSQL (``local_setup.ask_policy``).

Single-mode Ask requires exactly its offline setup policy. The owner app also
accepts the broader policy that setting up Build applies to the same project,
but only an owner-applied revision that descends from the offline setup and
still lets ``read`` act.
"""

from __future__ import annotations

import psycopg
import pytest

from panestria.contracts.policy import AutonomyAxis, PolicyContext, PrivacyAxis, TrustAxis
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.local_setup import LocalSetupIntent, LocalSetupService, ask_policy, offline_policy
from panestria.kernel.policy import PolicyService
from panestria.kernel.repositories.policy import current_policy, insert_revision
from panestria.kernel.uow import UnitOfWork


class AnyCertificate:
    """Accepts every runtime certificate; certificate validation has its own tests."""

    def validate(self, trust: TrustAxis) -> None:
        del trust


def offline(task: dict[str, str]) -> Actor:
    actor = Actor(task["owner"], task["project"])
    intent = LocalSetupIntent(owner_id=actor.owner_id, project_id=actor.project_id, intent="OFFLINE_ASK")
    with psycopg.connect(task["dsn"]) as c:
        LocalSetupService().initialize(UnitOfWork(c), intent)
    return actor


def build_policy(old: PolicyContext, *, read: str = "act-and-report") -> PolicyContext:
    """The successor ``OwnerBuild.propose_policy`` proposes, optionally with another ``read``."""
    actions = {**old.autonomy.actions, "read": read, "edit": "act-and-report", "external-send": "act-and-report"}
    actions["merge"] = "approve-first"
    return old.model_copy(
        update={
            "version": old.version + 1,
            "trust": TrustAxis(
                version=old.trust.version + 1,
                profile="PERSONAL_SANDBOX",
                allowed_actions=["read", "edit", "external-send", "merge"],
                runtime_certificate_sha256="ab" * 32,
            ),
            "privacy": PrivacyAxis(version=old.privacy.version + 1, cloud_destinations=["claude-subscription"]),
            "autonomy": AutonomyAxis(version=old.autonomy.version + 1, actions=actions),
        }
    )


def apply(task: dict[str, str], actor: Actor, proposed: PolicyContext) -> PolicyContext:
    """Propose, approve and apply ``proposed`` through a policy review, as the owner does."""
    service = PolicyService(AnyCertificate())  # type: ignore[arg-type]
    with psycopg.connect(task["dsn"]) as c:
        review = service.propose(UnitOfWork(c), actor, task["task"], proposed)
        service.decide(UnitOfWork(c), actor, review.review_id, review.effect_digest, "approve")
        return service.apply(UnitOfWork(c), actor, review.review_id, review.effect_digest)


def current(task: dict[str, str], actor: Actor) -> PolicyContext:
    with psycopg.connect(task["dsn"]) as c:
        return current_policy(UnitOfWork(c), actor)


def policy_for_ask(task: dict[str, str], actor: Actor, *, accept_successor: bool) -> PolicyContext:
    with psycopg.connect(task["dsn"]) as c:
        return ask_policy(UnitOfWork(c), actor, accept_successor=accept_successor)


@pytest.mark.parametrize("accept_successor", [False, True])
def test_ask_runs_under_its_offline_setup_policy(r1_task: dict[str, str], accept_successor: bool) -> None:
    actor = offline(r1_task)
    assert policy_for_ask(r1_task, actor, accept_successor=accept_successor) == offline_policy(actor)


def test_only_the_owner_app_accepts_the_policy_build_setup_applies(r1_task: dict[str, str]) -> None:
    actor = offline(r1_task)
    applied = apply(r1_task, actor, build_policy(current(r1_task, actor)))
    with pytest.raises(KernelDenied, match="^local_setup_policy_conflict$"):
        policy_for_ask(r1_task, actor, accept_successor=False)
    policy = policy_for_ask(r1_task, actor, accept_successor=True)
    assert policy == applied and (policy.version, policy.trust.profile) == (2, "PERSONAL_SANDBOX")


def test_a_successor_where_read_no_longer_acts_is_refused(r1_task: dict[str, str]) -> None:
    actor = offline(r1_task)
    apply(r1_task, actor, build_policy(current(r1_task, actor), read="approve-first"))
    with pytest.raises(KernelDenied, match="^local_setup_policy_conflict$"):
        policy_for_ask(r1_task, actor, accept_successor=True)


def test_a_revision_not_applied_through_a_policy_review_is_refused(r1_task: dict[str, str]) -> None:
    actor = offline(r1_task)
    with psycopg.connect(r1_task["dsn"]) as c:
        insert_revision(UnitOfWork(c), build_policy(current_policy(UnitOfWork(c), actor)))
    assert current(r1_task, actor).version == 2
    with pytest.raises(KernelDenied, match="^local_setup_policy_conflict$"):
        policy_for_ask(r1_task, actor, accept_successor=True)


def test_a_project_never_set_up_for_offline_ask_is_refused(r1_task: dict[str, str]) -> None:
    actor = Actor(r1_task["owner"], r1_task["project"])
    with psycopg.connect(r1_task["dsn"]) as c:
        PolicyService(AnyCertificate()).initialize(UnitOfWork(c), actor, r1_task["task"])  # type: ignore[arg-type]
    apply(r1_task, actor, build_policy(current(r1_task, actor)))
    for accept_successor in (False, True):
        with pytest.raises(KernelDenied, match="^local_setup_policy_conflict$"):
            policy_for_ask(r1_task, actor, accept_successor=accept_successor)
