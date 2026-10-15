"""Fenced invocation intents. Admission policy is the trusted caller's responsibility.

The caller commits each transition and its event atomically. No subprocess,
network request or filesystem mutation happens inside these transactions.
"""

from __future__ import annotations

import re
from uuid import uuid4

from panestria.contracts.invocation import InvocationBinding
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.leases import LeaseService
from panestria.kernel.repositories.policy import require_current_policy
from panestria.kernel.repositories.tasks import append_event
from panestria.kernel.uow import UnitOfWork


class InvocationService:
    def _current(self, uow: UnitOfWork, actor: Actor, binding: InvocationBinding) -> str:
        scope = binding.scope
        if (str(scope.owner_id), str(scope.project_id)) != (actor.owner_id, actor.project_id):
            raise KernelDenied("not_found")
        require_current_policy(uow, actor, scope.policy_ref)
        task = LeaseService().require_current(uow, actor, str(scope.attempt_id), scope.lease_epoch)
        if task != str(scope.task_id):
            raise KernelDenied("invocation_scope_mismatch")
        row = uow.execute(
            "SELECT t.goal_id::text,c.sha256,c.body->>'autonomy_profile_ref' FROM panestria.task t"
            " JOIN panestria.goal_contract c ON c.id=t.contract_id WHERE t.id=%s",
            (task,),
        ).fetchone()
        if row is None or (str(row[1]).strip(), row[2]) != (scope.contract_sha256, scope.policy_ref):
            raise KernelDenied("invocation_contract_changed")
        return str(row[0])

    def prepare(
        self, uow: UnitOfWork, actor: Actor, binding: InvocationBinding, key: str, *, ttl_seconds: int = 120
    ) -> str:
        if re.fullmatch(r"[a-zA-Z0-9:._-]{1,128}", key) is None or not 1 <= ttl_seconds <= 900:
            raise KernelDenied("invalid_invocation")
        goal = self._current(uow, actor, binding)
        existing = uow.execute(
            "SELECT id::text,binding_sha256 FROM panestria.worker_invocation WHERE attempt_id=%s"
            " AND invocation_key=%s FOR UPDATE",
            (str(binding.scope.attempt_id), key),
        ).fetchone()
        if existing is not None:
            if str(existing[1]).strip() != binding.sha256():
                raise KernelDenied("idempotency_conflict")
            return str(existing[0])
        identity = str(uuid4())
        uow.execute(
            "INSERT INTO panestria.worker_invocation"
            "(id,task_id,attempt_id,invocation_key,binding,binding_sha256,expires_at)"
            " VALUES (%s,%s,%s,%s,%s::jsonb,%s,clock_timestamp()+make_interval(secs => %s))",
            (
                identity,
                str(binding.scope.task_id),
                str(binding.scope.attempt_id),
                key,
                binding.model_dump_json(),
                binding.sha256(),
                ttl_seconds,
            ),
        )
        append_event(
            uow,
            goal_id=goal,
            task_id=str(binding.scope.task_id),
            actor=actor.owner_id,
            kind="invocation.prepared",
            payload={"invocation_id": identity, "kind": binding.kind, "binding_sha256": binding.sha256()},
        )
        return identity

    def _row(self, uow: UnitOfWork, binding: InvocationBinding, identity: str) -> tuple[object, ...]:
        row = uow.execute(
            "SELECT state,binding_sha256,expires_at>clock_timestamp(),receipt_sha256 FROM panestria.worker_invocation"
            " WHERE id=%s AND task_id=%s AND attempt_id=%s FOR UPDATE",
            (identity, str(binding.scope.task_id), str(binding.scope.attempt_id)),
        ).fetchone()
        if row is None or str(row[1]).strip() != binding.sha256():
            raise KernelDenied("invocation_binding_mismatch")
        return row

    def claim(self, uow: UnitOfWork, actor: Actor, binding: InvocationBinding, identity: str) -> None:
        goal = self._current(uow, actor, binding)
        row = self._row(uow, binding, identity)
        if row[0] != "PREPARED" or row[2] is not True:
            raise KernelDenied("invocation_not_dispatchable")
        uow.execute("UPDATE panestria.worker_invocation SET state='CLAIMED' WHERE id=%s", (identity,))
        append_event(
            uow,
            goal_id=goal,
            task_id=str(binding.scope.task_id),
            actor=actor.owner_id,
            kind="invocation.claimed",
            payload={"invocation_id": identity},
        )

    def check(self, uow: UnitOfWork, actor: Actor, binding: InvocationBinding, identity: str) -> None:
        self._current(uow, actor, binding)
        row = self._row(uow, binding, identity)
        if row[0] != "CLAIMED" or row[2] is not True:
            raise KernelDenied("invocation_inactive")

    def finish(
        self, uow: UnitOfWork, actor: Actor, binding: InvocationBinding, identity: str, receipt_sha256: str | None
    ) -> None:
        # Historical receipt recording is allowed after expiry/revocation; it
        # does not publish a candidate or restore current execution authority.
        row = uow.execute(
            "SELECT g.id::text FROM panestria.task t JOIN panestria.goal g ON g.id=t.goal_id"
            " WHERE t.id=%s AND g.owner_id=%s AND g.project_id=%s FOR UPDATE OF t",
            (str(binding.scope.task_id), actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        goal = str(row[0])
        current = self._row(uow, binding, identity)
        if receipt_sha256 is not None and re.fullmatch(r"[0-9a-f]{64}", receipt_sha256) is None:
            raise KernelDenied("invalid_invocation_receipt")
        state = "RETURNED" if receipt_sha256 is not None else "UNKNOWN"
        if current[0] == state and (None if current[3] is None else str(current[3]).strip()) == receipt_sha256:
            return
        if current[0] != "CLAIMED":
            raise KernelDenied("invocation_already_finished")
        uow.execute(
            "UPDATE panestria.worker_invocation SET state=%s,receipt_sha256=%s,finished_at=clock_timestamp()"
            " WHERE id=%s",
            (state, receipt_sha256, identity),
        )
        append_event(
            uow,
            goal_id=goal,
            task_id=str(binding.scope.task_id),
            actor=actor.owner_id,
            kind="invocation.returned" if receipt_sha256 else "invocation.unknown",
            payload={"invocation_id": identity, "receipt_sha256": receipt_sha256},
        )
