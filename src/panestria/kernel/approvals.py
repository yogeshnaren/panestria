"""Locked approval decisions. A decision does not execute an effect."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import uuid4

from psycopg.errors import UniqueViolation

from panestria.contracts.approval import (
    ActionPreview,
    PreviewRejected,
    effect_digest,
    load_preview,
    require_request_bounds,
)
from panestria.contracts.task import ALLOWED_TRANSITIONS
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.plan_scope import require_final_task
from panestria.kernel.repositories.approvals import (
    bump_version,
    consumption,
    effect_count,
    insert_consumption,
    insert_effect,
    insert_idempotency,
    insert_request,
    lock_idempotency,
    lock_request,
    lock_task_row,
    mark_decision,
    mark_expired,
    mark_wait,
    peek_request_task,
    preview_json,
    request_expired,
    required_verdicts,
)
from panestria.kernel.repositories.policy import require_current_policy
from panestria.kernel.repositories.tasks import append_event
from panestria.kernel.uow import UnitOfWork

_WAIT = {
    "contract_consent": ("DISPATCH", "contract"),
    "merge": ("MERGE", "merge"),
    "finalize": ("FINALIZE", "finalize"),
}
_EFFECT_WAIT = frozenset({"MERGE", "FINALIZE"})


class ApprovalView:
    def __init__(
        self,
        approval_id: str,
        effect_digest: str,
        expected_version: int,
        state: str,
        continuation_kind: str,
        preview: dict[str, Any],
    ) -> None:
        self.approval_id = approval_id
        self.effect_digest = effect_digest
        self.expected_version = expected_version
        self.state = state
        self.continuation_kind = continuation_kind
        self.preview = preview


class DecisionReceipt:
    def __init__(
        self,
        approval_id: str,
        state: str,
        effect_digest: str,
        row_version: int,
        replayed: bool,
    ) -> None:
        self.approval_id = approval_id
        self.state = state
        self.effect_digest = effect_digest
        self.row_version = row_version
        self.replayed = replayed


class ContinuationReceipt:
    def __init__(self, approval_id: str, task_state: str, effect_id: str | None, replayed: bool) -> None:
        self.approval_id = approval_id
        self.task_state = task_state
        self.effect_id = effect_id
        self.replayed = replayed


class ApprovalService:
    def request(self, uow: UnitOfWork, actor: Actor, document: dict[str, Any]) -> ApprovalView:
        try:
            preview = load_preview(document)
            now = uow.execute("SELECT clock_timestamp()").fetchone()
            assert now is not None
            require_request_bounds(preview, now[0])
        except PreviewRejected as exc:
            raise KernelDenied(exc.code) from None
        if preview.owner_id != actor.owner_id or preview.project_id != actor.project_id:
            raise KernelDenied("not_found")
        require_current_policy(uow, actor, preview.policy_version)
        locked = lock_task_row(uow, actor.owner_id, actor.project_id, preview.task_id)
        if locked is None:
            raise KernelDenied("not_found")
        goal_id, state, row_version, contract_id = locked
        if preview.action_kind in {"merge", "finalize"}:
            require_final_task(uow, actor, preview.task_id)
        self._bound_contract(uow, contract_id, preview)
        continuation, phase = _WAIT[preview.action_kind]
        if (state, "WAITING_APPROVAL") not in ALLOWED_TRANSITIONS:
            raise KernelDenied("illegal_transition")
        digest = effect_digest(preview)
        updated = mark_wait(uow, preview.task_id, row_version, "WAITING_APPROVAL", continuation, phase)
        if updated is None:
            raise KernelDenied("version_conflict")
        request_id = str(uuid4())
        body = json.loads(preview.model_dump_json())
        insert_request(
            uow,
            request_id,
            goal_id,
            preview.task_id,
            actor.owner_id,
            actor.project_id,
            preview.minimum_actor_id,
            preview.action_kind,
            digest,
            preview.policy_version,
            preview.expires_at,
            preview_json(body),
        )
        append_event(
            uow,
            goal_id=goal_id,
            task_id=preview.task_id,
            kind="approval.requested",
            actor=actor.owner_id,
            payload={"approval_id": request_id, "effect_digest": digest, "continuation_kind": continuation},
        )
        return ApprovalView(request_id, digest, updated, "PENDING", continuation, body)

    def preview(self, uow: UnitOfWork, actor: Actor, request_id: str) -> ApprovalView:
        task_id = peek_request_task(uow, actor.owner_id, actor.project_id, request_id)
        if task_id is None:
            raise KernelDenied("not_found")
        locked = lock_task_row(uow, actor.owner_id, actor.project_id, task_id)
        row = lock_request(uow, actor.owner_id, actor.project_id, request_id)
        if locked is None or row is None:
            raise KernelDenied("not_found")
        _goal_id, _state, row_version, _contract_id = locked
        _goal, _task, _actor, action_kind, digest, state, body = row
        parsed = self._stored_preview(body, str(digest))
        continuation, _phase = _WAIT[action_kind]
        return ApprovalView(request_id, str(digest), row_version, str(state), continuation, parsed)

    def list_pending(self, uow: UnitOfWork, actor: Actor, limit: int) -> list[dict[str, object]]:
        rows = uow.execute(
            "SELECT approval_request.id::text, approval_request.goal_id::text,"
            " approval_request.effect_digest, approval_request.action_kind,"
            " approval_request.expires_at, task.row_version"
            " FROM panestria.approval_request AS approval_request"
            " JOIN panestria.task AS task ON task.id = approval_request.task_id"
            " WHERE approval_request.owner_id = %s AND approval_request.project_id = %s"
            " AND approval_request.state = 'PENDING' AND approval_request.expires_at > now()"
            " ORDER BY approval_request.expires_at LIMIT %s",
            (actor.owner_id, actor.project_id, limit),
        ).fetchall()
        listed: list[dict[str, object]] = []
        for approval_id, goal_id, digest, action_kind, expires_at, row_version in rows:
            listed.append(
                {
                    "approval_id": str(approval_id),
                    "goal_id": str(goal_id),
                    "effect_digest": str(digest).strip(),
                    "action_kind": str(action_kind),
                    "expected_version": int(row_version),
                    "expires_at": expires_at.isoformat(),
                }
            )
        return listed

    def decide(
        self,
        uow: UnitOfWork,
        actor: Actor,
        request_id: str,
        supplied_digest: str,
        expected_version: int,
        decision: str,
        idempotency_key: str,
    ) -> DecisionReceipt:
        if decision not in {"approve", "deny"}:
            raise KernelDenied("invalid_decision")
        task_id = peek_request_task(uow, actor.owner_id, actor.project_id, request_id)
        if task_id is None:
            raise KernelDenied("not_found")
        project_ref = uow.execute(
            "SELECT contract.body->>'autonomy_profile_ref' FROM panestria.task task"
            " JOIN panestria.goal_contract contract ON contract.id=task.contract_id WHERE task.id=%s",
            (task_id,),
        ).fetchone()
        if project_ref is not None:
            require_current_policy(uow, actor, str(project_ref[0]))
        locked = lock_task_row(uow, actor.owner_id, actor.project_id, task_id)
        row = lock_request(uow, actor.owner_id, actor.project_id, request_id)
        if locked is None or row is None:
            raise KernelDenied("not_found")
        goal_id, _state, row_version, _contract_id = locked
        _goal, _task, minimum_actor, _kind, digest, state, body = row
        self._stored_preview(body, str(digest))
        request_hash = _decision_hash(request_id, supplied_digest, expected_version, decision)
        existing = lock_idempotency(uow, actor.owner_id, actor.project_id, idempotency_key)
        if existing is not None:
            return _replay(existing, request_hash)
        if str(minimum_actor) != actor.owner_id:
            raise KernelDenied("actor_mismatch")
        if supplied_digest != str(digest):
            raise KernelDenied("digest_mismatch")
        target = "APPROVED" if decision == "approve" else "DENIED"
        if str(state) == target:
            return DecisionReceipt(request_id, target, str(digest), row_version, True)
        if str(state) != "PENDING":
            raise KernelDenied("expired" if str(state) == "EXPIRED" else "decision_conflict")
        if row_version != expected_version:
            raise KernelDenied("version_conflict")
        if request_expired(uow, request_id):
            if mark_expired(uow, request_id) != 1:
                raise KernelDenied("decision_conflict")
            bumped = bump_version(uow, task_id, row_version)
            if bumped is None:
                raise KernelDenied("version_conflict")
            append_event(
                uow,
                goal_id=goal_id,
                task_id=task_id,
                kind="approval.expired",
                actor=actor.owner_id,
                payload={"approval_id": request_id, "effect_digest": str(digest)},
            )
            raise KernelDenied("expired")
        if mark_decision(uow, request_id, target, actor.owner_id) != 1:
            raise KernelDenied("decision_conflict")
        bumped = bump_version(uow, task_id, row_version)
        if bumped is None:
            raise KernelDenied("version_conflict")
        receipt = DecisionReceipt(request_id, target, str(digest), bumped, False)
        try:
            insert_idempotency(
                uow,
                actor.owner_id,
                actor.project_id,
                idempotency_key,
                request_hash,
                json.dumps(_receipt_body(receipt), separators=(",", ":"), sort_keys=True),
            )
        except UniqueViolation:
            raise KernelDenied("idempotency_conflict") from None
        append_event(
            uow,
            goal_id=goal_id,
            task_id=task_id,
            kind="approval.decided",
            actor=actor.owner_id,
            payload={"approval_id": request_id, "effect_digest": str(digest), "state": target},
        )
        return receipt

    def continue_after_approval(
        self,
        uow: UnitOfWork,
        actor: Actor,
        request_id: str,
        supplied_digest: str,
        expected_version: int,
    ) -> ContinuationReceipt:
        """Move a wait forward. MERGE and FINALIZE prepare one effect; neither launches a worker."""
        task_id = peek_request_task(uow, actor.owner_id, actor.project_id, request_id)
        if task_id is None:
            raise KernelDenied("not_found")
        project_ref = uow.execute(
            "SELECT contract.body->>'autonomy_profile_ref' FROM panestria.task task"
            " JOIN panestria.goal_contract contract ON contract.id=task.contract_id WHERE task.id=%s",
            (task_id,),
        ).fetchone()
        if project_ref is not None:
            require_current_policy(uow, actor, str(project_ref[0]))
        locked = lock_task_row(uow, actor.owner_id, actor.project_id, task_id)
        row = lock_request(uow, actor.owner_id, actor.project_id, request_id)
        if locked is None or row is None:
            raise KernelDenied("not_found")
        goal_id, task_state, row_version, _contract_id = locked
        _goal, _task, minimum_actor, action_kind, digest, state, body = row
        parsed = self._stored_preview(body, str(digest))
        if str(minimum_actor) != actor.owner_id or supplied_digest != str(digest):
            raise KernelDenied("actor_mismatch" if str(minimum_actor) != actor.owner_id else "digest_mismatch")
        found, effect_id = consumption(uow, request_id)
        continuation, _phase = _WAIT[str(action_kind)]
        if found:
            return ContinuationReceipt(request_id, task_state, effect_id, True)
        if str(state) == "EXPIRED" or request_expired(uow, request_id):
            raise KernelDenied("expired")
        if str(state) != "APPROVED":
            raise KernelDenied("not_approved")
        if row_version != expected_version:
            raise KernelDenied("version_conflict")
        if continuation in _EFFECT_WAIT:
            self._require_pass(uow, task_id, parsed)
            effect_id = str(uuid4())
            insert_effect(
                uow,
                effect_id,
                task_id,
                f"approval:{request_id}",
                str(parsed["destination"]),
                str(digest),
                request_id,
            )
            insert_consumption(uow, request_id, effect_id, actor.owner_id, str(digest))
            target = "VERIFYING"
        elif continuation == "DISPATCH":
            effect_id = None
            insert_consumption(uow, request_id, None, actor.owner_id, str(digest))
            target = "READY"
        else:
            raise KernelDenied("illegal_transition")
        if (task_state, target) not in ALLOWED_TRANSITIONS:
            raise KernelDenied("illegal_transition")
        updated = mark_wait(uow, task_id, row_version, target, continuation, _WAIT[str(action_kind)][1])
        if updated is None:
            raise KernelDenied("version_conflict")
        append_event(
            uow,
            goal_id=goal_id,
            task_id=task_id,
            kind="approval.continued",
            actor=actor.owner_id,
            payload={"approval_id": request_id, "effect_digest": str(digest), "to": target, "effect_id": effect_id},
        )
        return ContinuationReceipt(request_id, target, effect_id, False)

    def effects(self, uow: UnitOfWork, task_id: str) -> int:
        return effect_count(uow, task_id)

    def _bound_contract(self, uow: UnitOfWork, contract_id: str, preview: ActionPreview) -> None:
        stored = uow.execute(
            "SELECT sha256, version FROM panestria.goal_contract WHERE id = %s",
            (contract_id,),
        ).fetchone()
        if stored is None or str(stored[0]) != preview.contract_sha256 or int(stored[1]) != preview.contract_version:
            raise KernelDenied("invalid_preview")
        rows = uow.execute(
            "SELECT check_key FROM panestria.acceptance_check WHERE contract_id = %s AND required",
            (contract_id,),
        ).fetchall()
        if sorted(str(item[0]) for item in rows) != preview.required_checks:
            raise KernelDenied("invalid_preview")

    def _stored_preview(self, body: object, digest: str) -> dict[str, Any]:
        if isinstance(body, str):
            body = json.loads(body)
        try:
            parsed = load_preview(body)
        except PreviewRejected as exc:
            raise KernelDenied(exc.code) from None
        if effect_digest(parsed) != digest:
            raise KernelDenied("digest_mismatch")
        loaded = json.loads(parsed.model_dump_json())
        if not isinstance(loaded, dict):
            raise KernelDenied("invalid_preview")
        return loaded

    def _require_pass(self, uow: UnitOfWork, task_id: str, preview: dict[str, Any]) -> None:
        verdicts = required_verdicts(uow, task_id, str(preview["candidate_sha256"]))
        keys = [key for key, _verdict in verdicts]
        if keys != preview["required_checks"] or any(verdict != "PASS" for _key, verdict in verdicts):
            raise KernelDenied("unknown_check")


def _decision_hash(request_id: str, digest: str, expected_version: int, decision: str) -> str:
    payload = {
        "approval_id": request_id,
        "decision": decision,
        "effect_digest": digest,
        "expected_version": expected_version,
    }
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def _receipt_body(receipt: DecisionReceipt) -> dict[str, object]:
    return {
        "approval_id": receipt.approval_id,
        "effect_digest": receipt.effect_digest,
        "replayed": receipt.replayed,
        "row_version": receipt.row_version,
        "state": receipt.state,
    }


def _replay(existing: tuple[str, object], request_hash: str) -> DecisionReceipt:
    stored_hash, response = existing
    if stored_hash != request_hash:
        raise KernelDenied("idempotency_conflict")
    loaded = json.loads(response) if isinstance(response, str) else response
    if not isinstance(loaded, dict):
        raise KernelDenied("invalid_decision")
    return DecisionReceipt(
        str(loaded["approval_id"]),
        str(loaded["state"]),
        str(loaded["effect_digest"]),
        int(loaded["row_version"]),
        True,
    )
