"""Review binds the project, policy, original revision and every proposed field."""

from __future__ import annotations

import hashlib
import json
from uuid import uuid4

from psycopg.types.json import Jsonb

from panestria.contracts.classification import classification_rank
from panestria.contracts.memory import MemorySubmission
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.repositories.policy import active_policy_ref, require_current_policy
from panestria.kernel.uow import UnitOfWork


def fingerprint(
    actor: Actor, item_id: str, expected_version: int, old_sha256: str, policy_ref: str, document: MemorySubmission
) -> str:
    body = {
        "owner_id": actor.owner_id,
        "project_id": actor.project_id,
        "item_id": item_id,
        "expected_version": expected_version,
        "old_sha256": old_sha256,
        "policy_ref": policy_ref,
        "document": document.model_dump(mode="json"),
    }
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def guard_review_policy(uow: UnitOfWork, actor: Actor, review_id: str) -> None:
    row = uow.execute(
        "SELECT policy_ref FROM panestria.memory_review WHERE id=%s AND owner_id=%s AND project_id=%s",
        (review_id, actor.owner_id, actor.project_id),
    ).fetchone()
    if row is None:
        raise KernelDenied("not_found")
    require_current_policy(uow, actor, str(row[0]))  # Before any memory/review row lock.


def consume_review(
    uow: UnitOfWork,
    actor: Actor,
    review_id: str,
    item_id: str,
    expected_version: int,
    old_sha256: str,
    document: MemorySubmission,
) -> None:
    row = uow.execute(
        "SELECT item_id::text,expected_version,old_sha256,policy_ref,effect_digest,state,"
        " expires_at>clock_timestamp(),proposed FROM panestria.memory_review"
        " WHERE id=%s AND owner_id=%s AND project_id=%s FOR UPDATE",
        (review_id, actor.owner_id, actor.project_id),
    ).fetchone()
    if row is None:
        raise KernelDenied("not_found")
    if row[0] != item_id or row[1] != expected_version or row[2] != old_sha256 or row[5] != "APPROVED" or not row[6]:
        raise KernelDenied("memory_review_mismatch")
    digest = fingerprint(actor, item_id, expected_version, old_sha256, str(row[3]), document)
    if row[4] != digest or row[7] != document.model_dump(mode="json"):
        raise KernelDenied("memory_review_mismatch")
    uow.execute("UPDATE panestria.memory_review SET state='CONSUMED' WHERE id=%s", (review_id,))


class ReclassificationService:
    def propose(
        self, uow: UnitOfWork, actor: Actor, item_id: str, expected_version: int, document: MemorySubmission
    ) -> dict[str, object]:
        ref = active_policy_ref(uow, actor.owner_id, actor.project_id)
        if ref is None:
            raise KernelDenied("policy_unconfigured")
        require_current_policy(uow, actor, ref)
        row = uow.execute(
            "SELECT i.row_version,r.sha256,s.privacy_label FROM panestria.memory_item i"
            " JOIN panestria.memory_revision r ON r.item_id=i.id AND r.version=i.current_revision"
            " JOIN panestria.memory_source s ON s.id=r.source_id"
            " WHERE i.id=%s AND i.owner_id=%s AND i.project_id=%s FOR SHARE OF i",
            (item_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        if row[0] != expected_version:
            raise KernelDenied("version_conflict")
        if classification_rank(document.label) >= classification_rank(row[2]):
            raise KernelDenied("privacy_review_not_required")
        identity = str(uuid4())
        digest = fingerprint(actor, item_id, expected_version, str(row[1]), ref, document)
        uow.execute(
            "INSERT INTO panestria.memory_review"
            " (id,owner_id,project_id,item_id,expected_version,old_sha256,old_label,policy_ref,proposed,effect_digest)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                identity,
                actor.owner_id,
                actor.project_id,
                item_id,
                expected_version,
                row[1],
                row[2],
                ref,
                Jsonb(document.model_dump(mode="json")),
                digest,
            ),
        )
        return {
            "review_id": identity,
            "effect_digest": digest,
            "state": "PENDING",
            "old_label": row[2],
            "new_label": document.label,
        }

    def decide(self, uow: UnitOfWork, actor: Actor, review_id: str, digest: str, decision: str) -> str:
        if decision not in {"approve", "deny"}:
            raise KernelDenied("invalid_decision")
        guard_review_policy(uow, actor, review_id)
        row = uow.execute(
            "SELECT state,effect_digest,expires_at>clock_timestamp() FROM panestria.memory_review"
            " WHERE id=%s AND owner_id=%s AND project_id=%s FOR UPDATE",
            (review_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        if row[1] != digest or not row[2]:
            raise KernelDenied("memory_review_mismatch")
        target = "APPROVED" if decision == "approve" else "DENIED"
        if row[0] == target:
            return target
        if row[0] != "PENDING":
            raise KernelDenied("decision_conflict")
        uow.execute(
            "UPDATE panestria.memory_review SET state=%s,decided_by=%s,decided_at=clock_timestamp() WHERE id=%s",
            (target, actor.owner_id, review_id),
        )
        return target
