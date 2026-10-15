"""Only authenticated owner review applies a policy revision; models cannot promote themselves."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from uuid import uuid4

from panestria.contracts.policy import Action, Autonomy, AutonomyAxis, PolicyContext, PrivacyAxis, TrustAxis
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.repositories.policy import current_policy, insert_revision, lock_project
from panestria.kernel.repositories.tasks import append_event, lock_task
from panestria.kernel.uow import UnitOfWork
from panestria.policy.profiles import CertificateRejected, CertificateStore


@dataclass(frozen=True)
class PolicyReview:
    review_id: str
    effect_digest: str
    state: str


class PolicyService:
    def __init__(self, certificates: CertificateStore) -> None:
        self.certificates = certificates

    def get(self, uow: UnitOfWork, actor: Actor) -> PolicyContext:
        policy = current_policy(uow, actor)
        self._certificate(policy)
        return policy

    def _certificate(self, policy: PolicyContext) -> None:
        try:
            self.certificates.validate(policy.trust)
        except CertificateRejected as exc:
            raise KernelDenied(str(exc)) from None

    def _task(self, uow: UnitOfWork, actor: Actor, task_id: str) -> str:
        task = lock_task(uow, actor.owner_id, actor.project_id, task_id)
        if task is None:
            raise KernelDenied("not_found")
        return task[0]

    def initialize(self, uow: UnitOfWork, actor: Actor, task_id: str) -> PolicyContext:
        goal = self._task(uow, actor, task_id)
        if lock_project(uow, actor) != 0:
            raise KernelDenied("policy_already_configured")
        actions: dict[Action, Autonomy] = {
            action: "approve-first"
            for action in ("read", "edit", "tool-install", "external-send", "spend", "merge", "delete", "policy-change")
        }
        actions["read"] = "act-and-report"
        policy = PolicyContext(
            owner_id=actor.owner_id,
            project_id=actor.project_id,
            version=1,
            trust=TrustAxis(version=1, profile="SYNTHETIC_DEV", allowed_actions=["read", "edit", "merge"]),
            privacy=PrivacyAxis(version=1),
            autonomy=AutonomyAxis(version=1, actions=actions),
        )
        insert_revision(uow, policy)
        append_event(
            uow,
            goal_id=goal,
            task_id=task_id,
            kind="policy.initialized",
            actor=actor.owner_id,
            payload={"version": 1, "sha256": policy.sha256()},
        )
        return policy

    def propose(self, uow: UnitOfWork, actor: Actor, task_id: str, proposed: PolicyContext) -> PolicyReview:
        goal = self._task(uow, actor, task_id)
        version = lock_project(uow, actor)
        old = current_policy(uow, actor)
        if (proposed.owner_id, proposed.project_id) != (actor.owner_id, actor.project_id):
            raise KernelDenied("not_found")
        if proposed.version != version + 1:
            raise KernelDenied("version_conflict")
        for axis in ("trust", "privacy", "autonomy"):
            before, after = getattr(old, axis), getattr(proposed, axis)
            changed = before.model_dump(exclude={"version"}) != after.model_dump(exclude={"version"})
            if after.version != before.version + int(changed):
                raise KernelDenied("axis_version_conflict")
        self._certificate(proposed)
        digest = hashlib.sha256(
            json.dumps(
                {"task_id": task_id, "expected_version": version, "proposed_sha256": proposed.sha256()},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        review = PolicyReview(str(uuid4()), digest, "PENDING")
        uow.execute(
            "INSERT INTO panestria.policy_review"
            " (id,project_id,owner_id,task_id,expected_version,effect_digest,proposed_body,state,expires_at)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,'PENDING',clock_timestamp()+interval '15 minutes')",
            (review.review_id, actor.project_id, actor.owner_id, task_id, version, digest, proposed.model_dump_json()),
        )
        append_event(
            uow,
            goal_id=goal,
            task_id=task_id,
            kind="policy.review_requested",
            actor=actor.owner_id,
            payload={"review_id": review.review_id, "effect_digest": digest},
        )
        return review

    def _review(self, uow: UnitOfWork, actor: Actor, review_id: str) -> tuple[str, str, tuple[object, ...]]:
        hint = uow.execute(
            "SELECT task_id::text FROM panestria.policy_review WHERE id=%s AND owner_id=%s AND project_id=%s",
            (review_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if hint is None:
            raise KernelDenied("not_found")
        task_id = str(hint[0])
        goal_id = self._task(uow, actor, task_id)
        lock_project(uow, actor)
        row = uow.execute(
            "SELECT state,effect_digest,expected_version,proposed_body,expires_at>clock_timestamp()"
            " FROM panestria.policy_review WHERE id=%s FOR UPDATE",
            (review_id,),
        ).fetchone()
        assert row is not None
        return goal_id, task_id, row

    def decide(self, uow: UnitOfWork, actor: Actor, review_id: str, digest: str, decision: str) -> PolicyReview:
        if decision not in {"approve", "deny"}:
            raise KernelDenied("invalid_decision")
        goal, task, row = self._review(uow, actor, review_id)
        if str(row[1]).strip() != digest or row[4] is not True:
            raise KernelDenied("review_mismatch")
        target = "APPROVED" if decision == "approve" else "DENIED"
        if row[0] == target:
            return PolicyReview(review_id, digest, target)
        if row[0] != "PENDING":
            raise KernelDenied("decision_conflict")
        uow.execute(
            "UPDATE panestria.policy_review SET state=%s,decided_at=clock_timestamp(),decided_by=%s WHERE id=%s",
            (target, actor.owner_id, review_id),
        )
        append_event(
            uow,
            goal_id=goal,
            task_id=task,
            kind="policy.review_decided",
            actor=actor.owner_id,
            payload={"review_id": review_id, "state": target},
        )
        return PolicyReview(review_id, digest, target)

    def apply(self, uow: UnitOfWork, actor: Actor, review_id: str, digest: str) -> PolicyContext:
        goal, task, row = self._review(uow, actor, review_id)
        if str(row[1]).strip() != digest or row[4] is not True or row[0] not in {"APPROVED", "APPLIED"}:
            raise KernelDenied("review_mismatch")
        if row[0] == "APPLIED":
            return self.get(uow, actor)
        if lock_project(uow, actor) != row[2]:
            raise KernelDenied("version_conflict")
        proposed = PolicyContext.model_validate(row[3])
        expected_digest = hashlib.sha256(
            json.dumps(
                {"task_id": task, "expected_version": row[2], "proposed_sha256": proposed.sha256()},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        if expected_digest != digest:
            raise KernelDenied("review_mismatch")
        self._certificate(proposed)
        insert_revision(uow, proposed)
        uow.execute("UPDATE panestria.policy_review SET state='APPLIED' WHERE id=%s", (review_id,))
        uow.execute(
            "UPDATE panestria.approval_request SET state='REVOKED',decided_at=clock_timestamp(),decided_by=%s"
            " WHERE owner_id=%s AND project_id=%s AND state IN ('PENDING','APPROVED')",
            (actor.owner_id, actor.owner_id, actor.project_id),
        )
        append_event(
            uow,
            goal_id=goal,
            task_id=task,
            kind="policy.changed",
            actor=actor.owner_id,
            payload={"version": proposed.version, "sha256": proposed.sha256(), "review_id": review_id},
        )
        return proposed
