"""Independent axes, label lineage and client authority rejection."""

from __future__ import annotations

from itertools import product
from uuid import uuid4

import pytest
from pydantic import ValidationError

from panestria.contracts.policy import AutonomyAxis, PolicyContext, PolicyRequest, PrivacyAxis, TrustAxis
from panestria.policy.engine import PolicyEngine
from panestria.policy.labels import LabelService

ACTIONS = ["read", "edit", "tool-install", "external-send", "spend", "merge", "delete", "policy-change"]


def _context() -> PolicyContext:
    return PolicyContext(
        owner_id=str(uuid4()),
        project_id=str(uuid4()),
        version=1,
        trust=TrustAxis(
            version=1, profile="PERSONAL_SANDBOX", allowed_actions=ACTIONS, runtime_certificate_sha256="ab" * 32
        ),
        privacy=PrivacyAxis(version=1, cloud_destinations=["openai-api"], allow_private_cloud=True),
        autonomy=AutonomyAxis(version=1, actions={action: "act-and-report" for action in ACTIONS}),
    )


def _request(context: PolicyContext, **changes: object) -> PolicyRequest:
    body = dict(
        owner_id=context.owner_id,
        project_id=context.project_id,
        action="edit",
        label="PRIVATE",
        destination="local",
        effect_digest="cd" * 32,
    )
    body.update(changes)
    return PolicyRequest.model_validate(body)


def test_independent_axes_matrix(record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-007-TC01")
    record_property("source_clauses", "AOS-007-F01,AOS-007-F03,AOS-007-F04,AOS-007-AC01")
    context, engine = _context(), PolicyEngine()
    request = _request(context)
    # Each independent denial must survive all changes to the other two axes.
    for trust_allows, label, mode in product(
        [True, False],
        ["PUBLIC", "PRIVATE", "RESTRICTED", "UNKNOWN"],
        ["observe", "suggest", "approve-first", "act-and-report", "act-silently"],
    ):
        changed = context.model_copy(
            update={
                "trust": context.trust.model_copy(update={"allowed_actions": ACTIONS if trust_allows else []}),
                "autonomy": context.autonomy.model_copy(update={"actions": {action: mode for action in ACTIONS}}),
            }
        )
        outcome = engine.authorize(_request(context, label=label), changed).outcome
        if not trust_allows or label == "UNKNOWN" or mode in {"observe", "suggest"}:
            assert outcome == "DENY"
        elif mode == "approve-first":
            assert outcome == "APPROVAL_NEEDED"
        else:
            assert outcome == "PERMIT"
    restricted = _request(context, label="RESTRICTED", destination="openai-api")
    for profile in ["PERSONAL_SANDBOX", "TRUSTED_PROJECT", "HARDENED_WORKSPACE"]:
        raised = context.model_copy(update={"trust": context.trust.model_copy(update={"profile": profile})})
        assert engine.authorize(restricted, raised).outcome == "DENY"
        assert engine.authorize(request, raised).outcome == "PERMIT"
    observe = context.model_copy(update={"autonomy": AutonomyAxis(version=2, actions={a: "observe" for a in ACTIONS})})
    for label in ["PUBLIC", "PRIVATE", "RESTRICTED"]:
        assert engine.authorize(_request(context, label=label), observe).outcome == "DENY"
    before = context.sha256()
    for action in ACTIONS:
        selective = dict(context.autonomy.actions)
        selective[action] = "approve-first"
        changed = context.model_copy(update={"autonomy": AutonomyAxis(version=2, actions=selective)})
        for other in ACTIONS:
            assert engine.authorize(_request(context, action=other), changed).outcome == (
                "APPROVAL_NEEDED" if other == action else "PERMIT"
            )
    assert context.sha256() == before


def test_restricted_cloud_and_labels(record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-007-TC02")
    record_property("source_clauses", "AOS-007-F02,AOS-007-AC02,AOS-007-AC03")
    context, engine, labels = _context(), PolicyEngine(), LabelService()
    for label in ["RESTRICTED", "UNKNOWN"]:
        decision = engine.authorize(_request(context, label=label, destination="openai-api"), context)
        assert decision.outcome == "DENY"
    assert labels.derive(["PUBLIC", "PRIVATE"]) == "PRIVATE"
    assert labels.derive(["PUBLIC", "PRIVATE", "RESTRICTED"]) == "RESTRICTED"
    assert labels.derive([]) == labels.derive([None]) == labels.derive(["RESTRICTED", "UNKNOWN"]) == "UNKNOWN"
    private_cloud = engine.authorize(_request(context, destination="openai-api"), context)
    assert private_cloud.outcome == "DENY" and "legacy_private_cloud_denied" in private_cloud.reasons
    assert engine.authorize(_request(context, destination="unconfigured-provider"), context).outcome == "DENY"


def test_model_cannot_self_promote(record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-007-TC04")
    record_property("source_clauses", "AOS-007-F01,AOS-007-F04")
    context = _context()
    for authority in ["approved", "approval_granted", "policy_granted", "owner_approved", "action_permit"]:
        with pytest.raises(ValidationError):
            PolicyRequest.model_validate({**_request(context).model_dump(), authority: True})
    missing = context.model_copy(
        update={"trust": context.trust.model_copy(update={"runtime_certificate_sha256": None})}
    )
    assert PolicyEngine().authorize(_request(context), missing).outcome == "DENY"
    other = _request(context, project_id=str(uuid4()))
    assert PolicyEngine().authorize(other, context).reasons == ("scope_mismatch",)
    with pytest.raises(ValidationError):
        AutonomyAxis(version=1, actions={"edit": "act-silently"})


def test_project_versions_and_revocation(
    r1_task: dict[str, str], tmp_path: object, record_property: pytest.RecordProperty
) -> None:
    from pathlib import Path

    import psycopg

    from panestria.kernel.errors import KernelDenied
    from panestria.kernel.goals import Actor
    from panestria.kernel.policy import PolicyService
    from panestria.kernel.repositories.policy import active_policy_ref, require_current_policy
    from panestria.kernel.uow import UnitOfWork
    from panestria.policy.profiles import CertificateStore

    record_property("gate_case_id", "AOS-007-TC03")
    record_property("source_clauses", "AOS-007-F01,AOS-007-F03,AOS-007-AC02")
    actor = Actor(r1_task["owner"], r1_task["project"])
    service = PolicyService(CertificateStore(Path(str(tmp_path)), {"claude": "test-only"}))
    with psycopg.connect(r1_task["dsn"]) as c:
        first = service.initialize(UnitOfWork(c), actor, r1_task["task"])
        c.commit()
        ref = active_policy_ref(UnitOfWork(c), actor.owner_id, actor.project_id)
        assert ref is not None and first.sha256() in ref
        require_current_policy(UnitOfWork(c), actor, ref)
        c.commit()
        with pytest.raises(KernelDenied, match="policy_mismatch"), c.transaction():
            require_current_policy(UnitOfWork(c), actor, "test-policy-v1")
        with pytest.raises(KernelDenied, match="policy_unconfigured"), c.transaction():
            service.get(UnitOfWork(c), Actor(actor.owner_id, str(uuid4())))
        proposed_actions = dict(first.autonomy.actions)
        proposed_actions["edit"] = "observe"
        proposed = first.model_copy(
            update={"version": 2, "autonomy": AutonomyAxis(version=2, actions=proposed_actions)}
        )
        with pytest.raises(KernelDenied, match="axis_version_conflict"), c.transaction():
            service.propose(
                UnitOfWork(c),
                actor,
                r1_task["task"],
                proposed.model_copy(update={"privacy": first.privacy.model_copy(update={"version": 2})}),
            )
        with pytest.raises(KernelDenied, match="runtime_uncertified"), c.transaction():
            service.propose(
                UnitOfWork(c),
                actor,
                r1_task["task"],
                first.model_copy(
                    update={
                        "version": 2,
                        "trust": first.trust.model_copy(update={"version": 2, "profile": "PERSONAL_SANDBOX"}),
                    }
                ),
            )
        review = service.propose(UnitOfWork(c), actor, r1_task["task"], proposed)
        c.commit()
        with pytest.raises(psycopg.Error, match="immutable"), c.transaction():
            c.execute("UPDATE panestria.policy_review SET proposed_body='{}'::jsonb WHERE id=%s", (review.review_id,))
        with pytest.raises(KernelDenied, match="review_mismatch"), c.transaction():
            service.apply(UnitOfWork(c), actor, review.review_id, review.effect_digest)
        with pytest.raises(KernelDenied, match="review_mismatch"), c.transaction():
            service.decide(UnitOfWork(c), actor, review.review_id, "00" * 32, "approve")
        with pytest.raises(KernelDenied, match="not_found"), c.transaction():
            service.decide(
                UnitOfWork(c), Actor(str(uuid4()), actor.project_id), review.review_id, review.effect_digest, "approve"
            )
        approval_id = str(uuid4())
        c.execute(
            "INSERT INTO panestria.approval_request"
            " (id,goal_id,task_id,owner_id,project_id,minimum_actor_id,action_kind,effect_digest,policy_version,"
            " state,expires_at,preview) VALUES (%s,%s,%s,%s,%s,%s,'merge',%s,%s,'PENDING',"
            " clock_timestamp()+interval '1 hour','{}'::jsonb)",
            (
                approval_id,
                r1_task["goal"],
                r1_task["task"],
                actor.owner_id,
                actor.project_id,
                actor.owner_id,
                "ef" * 32,
                ref,
            ),
        )
        c.commit()
        service.decide(UnitOfWork(c), actor, review.review_id, review.effect_digest, "approve")
        c.commit()
        applied = service.apply(UnitOfWork(c), actor, review.review_id, review.effect_digest)
        c.commit()
        assert applied.version == 2 and applied.trust.version == applied.privacy.version == 1
        assert applied.autonomy.version == 2
        assert service.get(UnitOfWork(c), actor).sha256() == applied.sha256()
        assert c.execute("SELECT state FROM panestria.approval_request WHERE id=%s", (approval_id,)).fetchone() == (
            "REVOKED",
        )
        with pytest.raises(KernelDenied, match="policy_mismatch"), c.transaction():
            require_current_policy(UnitOfWork(c), actor, ref)
        with pytest.raises(psycopg.Error, match="immutable"), c.transaction():
            c.execute(
                "UPDATE panestria.project_policy_revision SET sha256=%s WHERE project_id=%s AND version=1",
                ("00" * 32, actor.project_id),
            )


def test_policy_wait_does_not_hold_task_before_project(r1_task: dict[str, str], tmp_path: object) -> None:
    import time
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path
    from threading import Event

    import psycopg

    from panestria.kernel.goals import Actor
    from panestria.kernel.policy import PolicyService
    from panestria.kernel.uow import UnitOfWork
    from panestria.policy.profiles import CertificateStore

    actor = Actor(r1_task["owner"], r1_task["project"])
    service = PolicyService(CertificateStore(Path(str(tmp_path)), {}))
    with psycopg.connect(r1_task["dsn"]) as c:
        first = service.initialize(UnitOfWork(c), actor, r1_task["task"])
    actions = dict(first.autonomy.actions)
    actions["edit"] = "observe"
    proposed = first.model_copy(update={"version": 2, "autonomy": AutonomyAxis(version=2, actions=actions)})
    entered, backend = Event(), []

    def propose() -> object:
        with psycopg.connect(r1_task["dsn"], options="-c lock_timeout=2500 -c statement_timeout=3000") as c:
            backend.append(c.execute("SELECT pg_backend_pid()").fetchone()[0])
            c.commit()
            entered.set()
            return service.propose(UnitOfWork(c), actor, r1_task["task"], proposed)

    with ThreadPoolExecutor(max_workers=1) as pool, psycopg.connect(r1_task["dsn"]) as dispatcher:
        dispatcher.execute("SET LOCAL lock_timeout='1500ms'")
        dispatcher.execute("SELECT id FROM panestria.project WHERE id=%s FOR SHARE", (actor.project_id,))
        reviewing = pool.submit(propose)
        assert entered.wait(2)
        deadline = time.monotonic() + 2
        while True:
            waiting = dispatcher.execute(
                "SELECT wait_event_type FROM pg_stat_activity WHERE pid=%s", (backend[0],)
            ).fetchone()
            if waiting and waiting[0] == "Lock":
                break
            assert time.monotonic() < deadline
            time.sleep(0.02)
        # This must succeed while the policy writer is waiting for the project.
        # Taking task then project would create a real lock cycle with dispatch.
        dispatcher.execute("SELECT id FROM panestria.task WHERE id=%s FOR UPDATE", (r1_task["task"],))
        dispatcher.commit()
        assert reviewing.result(timeout=3).state == "PENDING"
