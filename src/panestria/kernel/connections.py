"""Scoped owner-review ledger. Declarations are never execution or conformance permits."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import uuid4

from psycopg.pq import TransactionStatus
from pydantic import TypeAdapter, ValidationError

from panestria.contracts.connections import ConnectionId, ConnectionManifest, ConnectionReviewRequest
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.repositories.policy import current_policy, lock_project
from panestria.kernel.repositories.tasks import append_event, lock_task
from panestria.kernel.uow import UnitOfWork

_ID = TypeAdapter(ConnectionId)


def _identifier(value: str) -> str:
    try:
        return _ID.validate_python(value)
    except ValidationError:
        raise KernelDenied("invalid_connection_identifier") from None


def _sha(body: object) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class ConnectionReview:
    proposal_id: str
    grant_id: str
    expected_version: int
    effect_digest: str
    operation: Literal["REPLACE", "REVOKE"]
    policy_ref: str
    expires_at: datetime
    manifest: ConnectionManifest = field(repr=False)
    state: Literal["PENDING", "EXPIRED", "APPROVED", "DENIED"] = "PENDING"
    replayed: bool = False


@dataclass(frozen=True)
class ConnectionDecision:
    proposal_id: str
    grant_id: str
    decision: Literal["APPROVED", "DENIED"]
    granted_version: int | None
    effect_digest: str
    replayed: bool = False
    authority: Literal["DECLARATION_ONLY"] = "DECLARATION_ONLY"


@dataclass(frozen=True)
class ConnectionDeclaration:
    grant_id: str
    version: int
    state: Literal["DECLARED_ACTIVE", "DECLARED_REVOKED", "EXPIRED"]
    policy_ref: str
    manifest: ConnectionManifest = field(repr=False)
    conformance_status: Literal["UNVERIFIED"] = "UNVERIFIED"
    authority: Literal["DECLARATION_ONLY"] = "DECLARATION_ONLY"


def _fingerprint(
    proposal_id: str,
    grant_id: str,
    actor: Actor,
    task_id: str,
    goal_id: str,
    expected_version: int,
    operation: str,
    policy_ref: str,
    manifest_sha: str,
    expiry: datetime,
) -> str:
    return _sha(
        {
            "proposal_id": proposal_id,
            "grant_id": grant_id,
            "owner_id": actor.owner_id,
            "project_id": actor.project_id,
            "task_id": task_id,
            "goal_id": goal_id,
            "expected_version": expected_version,
            "operation": operation,
            "policy_ref": policy_ref,
            "manifest_sha256": manifest_sha,
            "review_expires_at": expiry.astimezone(UTC).isoformat(),
        }
    )


class ConnectionReviewService:
    def __init__(self, *, review_seconds: int = 900) -> None:
        if type(review_seconds) is not int or not 1 <= review_seconds <= 900:
            raise ValueError("invalid_connection_review_deadline")
        self.review_seconds = review_seconds

    @staticmethod
    def _transaction(uow: UnitOfWork) -> None:
        if uow.connection.autocommit and uow.connection.info.transaction_status != TransactionStatus.INTRANS:
            raise KernelDenied("connection_caller_transaction_required")

    @staticmethod
    def _policy(uow: UnitOfWork, actor: Actor, supplied: str) -> None:
        policy = current_policy(uow, actor)
        if supplied != f"project-policy:{policy.version}:{policy.sha256()}":
            raise KernelDenied("policy_mismatch")

    @staticmethod
    def _root(uow: UnitOfWork, actor: Actor, grant_id: str, *, lock: bool = False) -> int:
        row = uow.execute(
            "SELECT current_version FROM panestria.connection_grant WHERE id=%s AND owner_id=%s AND project_id=%s"
            + (" FOR UPDATE" if lock else ""),
            (_identifier(grant_id), actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        return int(row[0])

    def _review(self, uow: UnitOfWork, actor: Actor, identifier: str) -> tuple[ConnectionReview, str, str, str]:
        row = uow.execute(
            "SELECT grant_id::text,expected_version,effect_digest,operation,policy_ref,expires_at,"
            "manifest_body,manifest_sha256,task_id::text,goal_id::text,request_sha256 "
            "FROM panestria.connection_grant_review WHERE id=%s AND owner_id=%s AND project_id=%s",
            (_identifier(identifier), actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        try:
            manifest = ConnectionManifest.model_validate_json(json.dumps(row[6]))
            if (manifest.owner_id, manifest.project_id) != (actor.owner_id, actor.project_id):
                raise ValueError
            digest = _fingerprint(
                identifier,
                str(row[0]),
                actor,
                str(row[8]),
                str(row[9]),
                int(row[1]),
                str(row[3]),
                str(row[4]),
                manifest.sha256(),
                row[5],
            )
            if manifest.sha256() != str(row[7]).strip() or digest != str(row[2]).strip():
                raise ValueError
            if row[3] not in {"REPLACE", "REVOKE"}:
                raise ValueError
            review = ConnectionReview(
                identifier, str(row[0]), int(row[1]), digest, row[3], str(row[4]), row[5], manifest
            )
        except (ValueError, TypeError, ValidationError):
            raise KernelDenied("connection_review_corrupt") from None
        return review, str(row[8]), str(row[9]), str(row[10]).strip()

    def preview(self, uow: UnitOfWork, actor: Actor, proposal_id: str) -> ConnectionReview:
        from dataclasses import replace

        review, _task, _goal, _request = self._review(uow, actor, proposal_id)
        decision = uow.execute(
            "SELECT decision FROM panestria.connection_grant_decision WHERE review_id=%s", (proposal_id,)
        ).fetchone()
        if decision is not None:
            return replace(review, state=decision[0])
        now = uow.execute("SELECT clock_timestamp()").fetchone()
        assert now is not None
        return replace(review, state="EXPIRED" if review.expires_at <= now[0] else "PENDING")

    def current(self, uow: UnitOfWork, actor: Actor, grant_id: str) -> ConnectionDeclaration:
        version = self._root(uow, actor, grant_id)
        row = uow.execute(
            "SELECT review_id::text,manifest_sha256,operation,policy_ref FROM panestria.connection_grant_revision "
            "WHERE grant_id=%s AND version=%s",
            (grant_id, version),
        ).fetchone()
        if row is None:
            raise KernelDenied("connection_not_declared")
        review, _task, _goal, _request = self._review(uow, actor, str(row[0]))
        if (review.manifest.sha256(), review.operation, review.policy_ref) != (
            str(row[1]).strip(),
            row[2],
            row[3],
        ) or review.expected_version + 1 != version:
            raise KernelDenied("connection_revision_corrupt")
        now = uow.execute("SELECT clock_timestamp()").fetchone()
        assert now is not None
        status: Literal["DECLARED_ACTIVE", "DECLARED_REVOKED", "EXPIRED"] = (
            "DECLARED_REVOKED"
            if review.operation == "REVOKE"
            else "EXPIRED"
            if review.manifest.expires_at <= now[0]
            else "DECLARED_ACTIVE"
        )
        return ConnectionDeclaration(grant_id, version, status, review.policy_ref, review.manifest)

    def propose(
        self,
        uow: UnitOfWork,
        actor: Actor,
        task_id: str,
        change: ConnectionReviewRequest,
    ) -> ConnectionReview:
        from dataclasses import replace

        self._transaction(uow)
        try:
            change = ConnectionReviewRequest.model_validate(change)
        except ValidationError:
            raise KernelDenied("invalid_connection_change") from None
        _identifier(task_id)
        lock_project(uow, actor)
        request_sha = _sha(
            {
                "task_id": task_id,
                "owner_id": actor.owner_id,
                "project_id": actor.project_id,
                "request": change.model_dump(mode="json"),
            }
        )
        old = uow.execute(
            "SELECT 1 FROM panestria.connection_grant_review WHERE id=%s", (change.proposal_id,)
        ).fetchone()
        if old is not None:
            review, old_task, _goal, old_sha = self._review(uow, actor, change.proposal_id)
            if request_sha != old_sha or old_task != task_id:
                raise KernelDenied("connection_proposal_conflict")
            return replace(self.preview(uow, actor, change.proposal_id), replayed=True)
        self._policy(uow, actor, change.policy_ref)
        grant_id = change.grant_id or str(uuid4())
        if change.grant_id is not None:
            version = self._root(uow, actor, grant_id, lock=True)
        else:
            version = 0
        if version != change.expected_version:
            raise KernelDenied("connection_version_conflict")
        locked = lock_task(uow, actor.owner_id, actor.project_id, task_id)
        if locked is None:
            raise KernelDenied("not_found")
        if change.operation == "REVOKE":
            prior = self.current(uow, actor, grant_id)
            if prior.state == "DECLARED_REVOKED":
                raise KernelDenied("connection_already_revoked")
            manifest = prior.manifest
        else:
            assert change.manifest is not None
            manifest = change.manifest
        if (manifest.owner_id, manifest.project_id) != (actor.owner_id, actor.project_id):
            raise KernelDenied("not_found")
        clock = uow.execute("SELECT clock_timestamp()").fetchone()
        assert clock is not None
        if change.operation == "REPLACE" and not clock[0] < manifest.expires_at <= clock[0] + timedelta(days=30):
            raise KernelDenied("connection_expiry_invalid")
        expiry = clock[0] + timedelta(seconds=self.review_seconds)
        digest = _fingerprint(
            change.proposal_id,
            grant_id,
            actor,
            task_id,
            locked[0],
            version,
            change.operation,
            change.policy_ref,
            manifest.sha256(),
            expiry,
        )
        if change.grant_id is None:
            uow.execute(
                "INSERT INTO panestria.connection_grant(id,owner_id,project_id) VALUES (%s,%s,%s)",
                (grant_id, actor.owner_id, actor.project_id),
            )
        uow.execute(
            "INSERT INTO panestria.connection_grant_review(id,grant_id,owner_id,project_id,goal_id,task_id,"
            "expected_version,operation,request_sha256,manifest_sha256,manifest_body,"
            "policy_ref,effect_digest,expires_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)",
            (
                change.proposal_id,
                grant_id,
                actor.owner_id,
                actor.project_id,
                locked[0],
                task_id,
                version,
                change.operation,
                request_sha,
                manifest.sha256(),
                manifest.model_dump_json(),
                change.policy_ref,
                digest,
                expiry,
            ),
        )
        append_event(
            uow,
            goal_id=locked[0],
            task_id=task_id,
            kind="connection.review_requested",
            actor=actor.owner_id,
            payload={"proposal_id": change.proposal_id, "grant_id": grant_id, "effect_digest": digest},
        )
        return ConnectionReview(
            change.proposal_id, grant_id, version, digest, change.operation, change.policy_ref, expiry, manifest
        )

    def decide(
        self,
        uow: UnitOfWork,
        actor: Actor,
        proposal_id: str,
        digest: str,
        decision: Literal["approve", "deny"],
    ) -> ConnectionDecision:
        self._transaction(uow)
        if decision not in {"approve", "deny"}:
            raise KernelDenied("invalid_decision")
        lock_project(uow, actor)
        review, task_id, goal_id, _request = self._review(uow, actor, proposal_id)
        version = self._root(uow, actor, review.grant_id, lock=True)
        locked = lock_task(uow, actor.owner_id, actor.project_id, task_id)
        if locked is None:
            raise KernelDenied("not_found")
        if digest != review.effect_digest:
            raise KernelDenied("digest_mismatch")
        target: Literal["APPROVED", "DENIED"] = "APPROVED" if decision == "approve" else "DENIED"
        old = uow.execute(
            "SELECT decision,granted_version FROM panestria.connection_grant_decision WHERE review_id=%s",
            (proposal_id,),
        ).fetchone()
        if old is not None:
            if old[0] != target:
                raise KernelDenied("decision_conflict")
            return ConnectionDecision(proposal_id, review.grant_id, target, old[1], digest, True)
        self._policy(uow, actor, review.policy_ref)
        if version != review.expected_version:
            raise KernelDenied("connection_version_conflict")
        now = uow.execute("SELECT clock_timestamp()").fetchone()
        assert now is not None
        if review.expires_at <= now[0] or (review.operation == "REPLACE" and review.manifest.expires_at <= now[0]):
            raise KernelDenied("connection_review_expired")
        next_version = version + 1 if target == "APPROVED" else None
        uow.execute(
            "INSERT INTO panestria.connection_grant_decision(review_id,grant_id,owner_id,project_id,expected_version,"
            "effect_digest,decision,granted_version,decided_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                proposal_id,
                review.grant_id,
                actor.owner_id,
                actor.project_id,
                version,
                digest,
                target,
                next_version,
                actor.owner_id,
            ),
        )
        if target == "APPROVED":
            uow.execute(
                "INSERT INTO panestria.connection_grant_revision(grant_id,version,owner_id,project_id,review_id,"
                "manifest_sha256,operation,policy_ref) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    review.grant_id,
                    next_version,
                    actor.owner_id,
                    actor.project_id,
                    proposal_id,
                    review.manifest.sha256(),
                    review.operation,
                    review.policy_ref,
                ),
            )
            uow.execute(
                "UPDATE panestria.connection_grant SET current_version=%s WHERE id=%s AND current_version=%s",
                (next_version, review.grant_id, version),
            )
        append_event(
            uow,
            goal_id=goal_id,
            task_id=task_id,
            kind="connection.review_decided",
            actor=actor.owner_id,
            payload={
                "proposal_id": proposal_id,
                "grant_id": review.grant_id,
                "decision": target,
                "granted_version": next_version,
                "effect_digest": digest,
            },
        )
        return ConnectionDecision(proposal_id, review.grant_id, target, next_version, digest)
