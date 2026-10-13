"""Effect intent and dispatch receipts in caller-owned transactions."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from panestria.contracts.approval import PreviewRejected, effect_digest, load_preview
from panestria.contracts.effects import EffectIntent
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.repositories.approvals import required_verdicts
from panestria.kernel.repositories.tasks import append_event, lock_task
from panestria.kernel.uow import UnitOfWork


@dataclass(frozen=True)
class EffectRef:
    effect_id: str
    task_id: str
    state: str
    replayed: bool = False


@dataclass(frozen=True)
class DispatchClaim:
    effect_id: str
    task_id: str
    epoch: int
    target: str
    request_ref: str
    fingerprint: str
    classification: str


class SideEffectService:
    def prepare(self, uow: UnitOfWork, actor: Actor, intent: EffectIntent, approval_id: str | None) -> EffectRef:
        locked = lock_task(uow, actor.owner_id, actor.project_id, intent.task_id)
        if locked is None:
            raise KernelDenied("not_found")
        goal_id, task_state, _version, _epoch = locked
        existing = uow.execute(
            "SELECT id::text,state,request_hash FROM panestria.side_effect"
            " WHERE task_id=%s AND effect_key=%s FOR UPDATE",
            (intent.task_id, intent.effect_key),
        ).fetchone()
        if existing is not None:
            if str(existing[2]).strip() != intent.fingerprint():
                raise KernelDenied("idempotency_conflict")
            return EffectRef(str(existing[0]), intent.task_id, str(existing[1]), True)
        if task_state in {"CANCELLING", "CANCELLED", "COMPLETED", "FAILED", "REJECTED"}:
            raise KernelDenied("illegal_transition")
        policy = uow.execute(
            "SELECT c.body->>'autonomy_profile_ref' FROM panestria.task t"
            " JOIN panestria.goal_contract c ON c.id=t.contract_id WHERE t.id=%s",
            (intent.task_id,),
        ).fetchone()
        if policy is None or policy[0] != intent.policy_version:
            raise KernelDenied("policy_mismatch")
        if intent.classification != "read-only" and approval_id is None:
            raise KernelDenied("approval_required")
        if approval_id is not None:
            approval = uow.execute(
                "SELECT state,effect_digest,policy_version,expires_at>clock_timestamp(),minimum_actor_id::text,preview"
                " FROM panestria.approval_request WHERE id=%s AND task_id=%s AND owner_id=%s AND project_id=%s"
                " FOR UPDATE",
                (approval_id, intent.task_id, actor.owner_id, actor.project_id),
            ).fetchone()
            if approval is None:
                raise KernelDenied("not_found")
            if (
                approval[0] != "APPROVED"
                or str(approval[1]).strip() != intent.effect_digest
                or approval[2] != intent.policy_version
                or approval[3] is not True
                or approval[4] != actor.owner_id
            ):
                raise KernelDenied("approval_mismatch")
            try:
                preview = load_preview(approval[5])
            except PreviewRejected:
                raise KernelDenied("invalid_preview") from None
            if (
                effect_digest(preview) != intent.effect_digest
                or preview.destination != intent.target
                or intent.request_ref != f"approval:{approval_id}"
            ):
                raise KernelDenied("approval_mismatch")
            contract = uow.execute(
                "SELECT c.sha256,c.version FROM panestria.task t JOIN panestria.goal_contract c ON c.id=t.contract_id"
                " WHERE t.id=%s",
                (intent.task_id,),
            ).fetchone()
            if (
                contract is None
                or str(contract[0]).strip() != preview.contract_sha256
                or contract[1] != preview.contract_version
                or preview.task_id != intent.task_id
                or preview.owner_id != actor.owner_id
                or preview.project_id != actor.project_id
            ):
                raise KernelDenied("approval_mismatch")
            if preview.action_kind in {"merge", "finalize"}:
                verdicts = required_verdicts(uow, intent.task_id, preview.candidate_sha256)
                if [key for key, _ in verdicts] != preview.required_checks or any(
                    verdict != "PASS" for _, verdict in verdicts
                ):
                    raise KernelDenied("unknown_check")
            if (
                uow.execute(
                    "SELECT 1 FROM panestria.approval_consumption WHERE approval_request_id=%s", (approval_id,)
                ).fetchone()
                is not None
            ):
                raise KernelDenied("approval_consumed")
        effect_id = str(uuid4())
        uow.execute(
            "INSERT INTO panestria.side_effect"
            " (id,task_id,effect_key,target,request_hash,state,effect_digest,approval_request_id,"
            "classification,request_ref)"
            " VALUES (%s,%s,%s,%s,%s,'PREPARED',%s,%s,%s,%s)",
            (
                effect_id,
                intent.task_id,
                intent.effect_key,
                intent.target,
                intent.fingerprint(),
                intent.effect_digest,
                approval_id,
                intent.classification,
                intent.request_ref,
            ),
        )
        if approval_id is not None:
            uow.execute(
                "INSERT INTO panestria.approval_consumption"
                " (approval_request_id,side_effect_id,consumed_by,effect_digest) VALUES (%s,%s,%s,%s)",
                (approval_id, effect_id, actor.owner_id, intent.effect_digest),
            )
        uow.execute(
            "INSERT INTO panestria.effect_outbox(effect_id,task_id,state) VALUES (%s,%s,'PENDING')",
            (effect_id, intent.task_id),
        )
        append_event(
            uow,
            goal_id=goal_id,
            task_id=intent.task_id,
            kind="effect.prepared",
            actor=actor.owner_id,
            payload={"effect_id": effect_id, "classification": intent.classification},
        )
        return EffectRef(effect_id, intent.task_id, "PREPARED")

    def _lock(self, uow: UnitOfWork, actor: Actor, effect_id: str) -> tuple[str, str, tuple[object, ...]]:
        hint = uow.execute("SELECT task_id::text FROM panestria.side_effect WHERE id=%s", (effect_id,)).fetchone()
        if hint is None:
            raise KernelDenied("not_found")
        task_id = str(hint[0])
        task = lock_task(uow, actor.owner_id, actor.project_id, task_id)
        if task is None:
            raise KernelDenied("not_found")
        row = uow.execute(
            "SELECT e.state,e.dispatch_epoch,e.target,e.request_ref,e.request_hash,e.classification,"
            " o.state,o.due_at<=clock_timestamp(),o.claim_expires_at<=clock_timestamp(),"
            " e.approval_request_id::text FROM panestria.side_effect e"
            " JOIN panestria.effect_outbox o ON o.effect_id=e.id WHERE e.id=%s FOR UPDATE OF e,o",
            (effect_id,),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        return task[0], task_id, row

    def claim(self, uow: UnitOfWork, actor: Actor, effect_id: str, *, ttl_seconds: int = 60) -> DispatchClaim:
        if not 1 <= ttl_seconds <= 3600:
            raise KernelDenied("invalid_claim")
        goal_id, task_id, row = self._lock(uow, actor, effect_id)
        if row[0] != "PREPARED" or row[6] != "PENDING" or row[7] is not True:
            raise KernelDenied("effect_not_dispatchable")
        current_task = uow.execute("SELECT state FROM panestria.task WHERE id=%s", (task_id,)).fetchone()
        if current_task is None or current_task[0] in {"CANCELLING", "CANCELLED", "FAILED", "REJECTED", "COMPLETED"}:
            raise KernelDenied("illegal_transition")
        if row[9] is not None:
            valid = uow.execute(
                "SELECT a.state='APPROVED' AND a.expires_at>clock_timestamp()"
                " AND a.policy_version=c.body->>'autonomy_profile_ref'"
                " FROM panestria.approval_request a JOIN panestria.task t ON t.id=a.task_id"
                " JOIN panestria.goal_contract c ON c.id=t.contract_id WHERE a.id=%s FOR UPDATE OF a",
                (row[9],),
            ).fetchone()
            if valid is None or valid[0] is not True:
                raise KernelDenied("approval_mismatch")
        epoch = int(str(row[1])) + 1
        uow.execute(
            "UPDATE panestria.side_effect SET state='EXECUTING',dispatch_epoch=%s,"
            " dispatch_attempts=dispatch_attempts+1 WHERE id=%s",
            (epoch, effect_id),
        )
        uow.execute(
            "UPDATE panestria.effect_outbox SET state='CLAIMED',"
            " claim_expires_at=clock_timestamp()+make_interval(secs => %s) WHERE effect_id=%s",
            (ttl_seconds, effect_id),
        )
        append_event(
            uow,
            goal_id=goal_id,
            task_id=task_id,
            kind="effect.dispatch_claimed",
            actor=actor.owner_id,
            payload={"effect_id": effect_id, "epoch": epoch},
        )
        return DispatchClaim(effect_id, task_id, epoch, str(row[2]), str(row[3]), str(row[4]).strip(), str(row[5]))

    def finish(self, uow: UnitOfWork, actor: Actor, claim: DispatchClaim, receipt: str | None) -> None:
        goal_id, task_id, row = self._lock(uow, actor, claim.effect_id)
        if row[0] != "EXECUTING" or row[1] != claim.epoch:
            raise KernelDenied("stale_dispatch")
        if receipt is not None and (not receipt or len(receipt) > 512):
            raise KernelDenied("invalid_receipt")
        state = "UNKNOWN" if receipt is None else "SUCCEEDED"
        uow.execute(
            "UPDATE panestria.side_effect SET state=%s,external_ref=%s WHERE id=%s", (state, receipt, claim.effect_id)
        )
        uow.execute(
            "UPDATE panestria.effect_outbox SET state=%s WHERE effect_id=%s",
            ("PAUSED" if receipt is None else "DONE", claim.effect_id),
        )
        if receipt is None:
            uow.execute(
                "UPDATE panestria.task SET state='RECONCILING',row_version=row_version+1 WHERE id=%s", (task_id,)
            )
        append_event(
            uow,
            goal_id=goal_id,
            task_id=task_id,
            kind="effect.receipt",
            actor=actor.owner_id,
            payload={"effect_id": claim.effect_id, "state": state},
        )

    def begin_reconciliation(self, uow: UnitOfWork, actor: Actor, effect_id: str) -> DispatchClaim:
        goal_id, task_id, row = self._lock(uow, actor, effect_id)
        if row[0] == "EXECUTING" and row[8] is not True:
            raise KernelDenied("dispatch_active")
        if row[0] not in {"UNKNOWN", "RECONCILING", "EXECUTING"}:
            raise KernelDenied("effect_not_reconcilable")
        epoch = int(str(row[1])) + 1
        uow.execute(
            "UPDATE panestria.side_effect SET state='RECONCILING',dispatch_epoch=%s WHERE id=%s", (epoch, effect_id)
        )
        uow.execute("UPDATE panestria.effect_outbox SET state='PAUSED' WHERE effect_id=%s", (effect_id,))
        uow.execute("UPDATE panestria.task SET state='RECONCILING',row_version=row_version+1 WHERE id=%s", (task_id,))
        append_event(
            uow,
            goal_id=goal_id,
            task_id=task_id,
            kind="effect.reconciling",
            actor=actor.owner_id,
            payload={"effect_id": effect_id, "epoch": epoch},
        )
        return DispatchClaim(effect_id, task_id, epoch, str(row[2]), str(row[3]), str(row[4]).strip(), str(row[5]))

    def reconciled(self, uow: UnitOfWork, actor: Actor, claim: DispatchClaim, receipt: str | None) -> EffectRef:
        goal_id, task_id, row = self._lock(uow, actor, claim.effect_id)
        if row[0] != "RECONCILING" or row[1] != claim.epoch:
            raise KernelDenied("stale_dispatch")
        if receipt is not None and (not receipt or len(receipt) > 512):
            raise KernelDenied("invalid_receipt")
        state = "SUCCEEDED" if receipt is not None else "RECONCILING"
        uow.execute(
            "UPDATE panestria.side_effect SET state=%s,external_ref=%s,reconciliation_note=%s WHERE id=%s",
            (state, receipt, "confirmed_by_query" if receipt else "owner_resolution_required", claim.effect_id),
        )
        uow.execute(
            "UPDATE panestria.effect_outbox SET state=%s WHERE effect_id=%s",
            ("DONE" if receipt is not None else "PAUSED", claim.effect_id),
        )
        append_event(
            uow,
            goal_id=goal_id,
            task_id=task_id,
            kind="effect.reconciled",
            actor=actor.owner_id,
            payload={"effect_id": claim.effect_id, "state": state},
        )
        return EffectRef(claim.effect_id, task_id, state)
