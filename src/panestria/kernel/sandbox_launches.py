"""Same-PostgreSQL immutable launch intent and historical cleanup metadata.

All mutation/event writes use the caller transaction. No Docker, filesystem,
network, retry, task completion or permission grant is performed here.
"""

from __future__ import annotations

import json
from uuid import UUID

from psycopg.pq import TransactionStatus

from panestria.contracts.invocation import InvocationBinding
from panestria.contracts.sandbox_launch import SandboxLaunchIntent, SandboxLaunchObservation
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.invocations import InvocationService
from panestria.kernel.repositories.tasks import append_event
from panestria.kernel.uow import UnitOfWork


def _transaction(uow: UnitOfWork) -> None:
    if uow.connection.autocommit and uow.connection.info.transaction_status != TransactionStatus.INTRANS:
        raise KernelDenied("sandbox_launch_transaction_required")


class SandboxLaunchService:
    def record(
        self, uow: UnitOfWork, actor: Actor, binding: InvocationBinding, identity: str, intent: SandboxLaunchIntent
    ) -> None:
        _transaction(uow)
        try:
            intent = SandboxLaunchIntent.model_validate_json(intent.model_dump_json())
            valid = (
                binding.kind == "native-tool"
                and str(intent.invocation_id) == identity
                and intent.binding_sha256 == binding.sha256()
                and intent.scope_sha256 == binding.scope.sha256()
            )
        except (ValueError, TypeError, AttributeError):
            valid = False
        if not valid:
            raise KernelDenied("sandbox_launch_binding_mismatch")
        invocations = InvocationService()
        goal = invocations._current(uow, actor, binding)
        row = invocations._row(uow, binding, identity)
        if row[0] != "CLAIMED" or row[2] is not True:
            raise KernelDenied("sandbox_launch_invocation_inactive")
        inserted = uow.execute(
            "INSERT INTO panestria.worker_invocation_launch "
            "(invocation_id,binding_sha256,launch_id,runtime_attempt_id,body,body_sha256) "
            "VALUES (%s,%s,%s,%s,%s::jsonb,%s) ON CONFLICT DO NOTHING RETURNING invocation_id",
            (
                identity,
                intent.binding_sha256,
                str(intent.launch_id),
                str(intent.runtime_attempt_id),
                intent.model_dump_json(),
                intent.sha256(),
            ),
        ).fetchone()
        if inserted is None:
            # Even an identical old record cannot authorize another create.
            raise KernelDenied("sandbox_launch_already_recorded")
        append_event(
            uow,
            goal_id=goal,
            task_id=str(binding.scope.task_id),
            actor=actor.owner_id,
            kind="sandbox.launch.recorded",
            payload={"invocation_id": identity, "launch_id": str(intent.launch_id), "intent_sha256": intent.sha256()},
        )

    def read(self, uow: UnitOfWork, actor: Actor, binding: InvocationBinding, identity: str) -> SandboxLaunchIntent:
        """Historical owner/project scope; never renews lease or execution authority."""
        try:
            valid_identity = type(identity) is str and str(UUID(identity)) == identity
        except (ValueError, TypeError, AttributeError):
            valid_identity = False
        if not valid_identity:
            raise KernelDenied("invalid_sandbox_invocation")
        if binding.kind != "native-tool" or (str(binding.scope.owner_id), str(binding.scope.project_id)) != (
            actor.owner_id,
            actor.project_id,
        ):
            raise KernelDenied("not_found")
        row = uow.execute(
            "SELECT l.body,l.body_sha256,l.binding_sha256 FROM panestria.worker_invocation_launch l "
            "JOIN panestria.worker_invocation i ON i.id=l.invocation_id "
            "JOIN panestria.task t ON t.id=i.task_id JOIN panestria.goal g ON g.id=t.goal_id "
            "WHERE l.invocation_id=%s AND i.task_id=%s AND i.attempt_id=%s "
            "AND g.owner_id=%s AND g.project_id=%s",
            (identity, str(binding.scope.task_id), str(binding.scope.attempt_id), actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        try:
            intent = SandboxLaunchIntent.model_validate_json(json.dumps(row[0]))
            valid = (
                intent.sha256() == str(row[1]).strip()
                and intent.binding_sha256 == str(row[2]).strip() == binding.sha256()
                and intent.scope_sha256 == binding.scope.sha256()
                and str(intent.invocation_id) == identity
            )
        except (ValueError, TypeError):
            valid = False
        if not valid:
            raise KernelDenied("sandbox_launch_reference_unconfirmed")
        return intent

    def observe(
        self,
        uow: UnitOfWork,
        actor: Actor,
        binding: InvocationBinding,
        identity: str,
        observation: SandboxLaunchObservation,
    ) -> None:
        _transaction(uow)
        try:
            observation = SandboxLaunchObservation.model_validate_json(observation.model_dump_json())
        except (ValueError, TypeError, AttributeError):
            raise KernelDenied("invalid_launch_observation") from None
        goal = uow.execute(
            "SELECT t.goal_id::text FROM panestria.task t JOIN panestria.goal g ON g.id=t.goal_id "
            "WHERE t.id=%s AND g.owner_id=%s AND g.project_id=%s FOR UPDATE OF t",
            (str(binding.scope.task_id), actor.owner_id, actor.project_id),
        ).fetchone()
        if goal is None:
            raise KernelDenied("not_found")
        intent = self.read(uow, actor, binding, identity)
        if observation.intent_sha256 != intent.sha256():
            raise KernelDenied("sandbox_launch_binding_mismatch")
        current = InvocationService()._row(uow, binding, identity)
        if current[0] not in {"CLAIMED", "UNKNOWN", "RETURNED"}:
            raise KernelDenied("sandbox_launch_reference_unconfirmed")
        if current[0] == "CLAIMED":
            uow.execute(
                "UPDATE panestria.worker_invocation SET state='UNKNOWN',finished_at=clock_timestamp() WHERE id=%s",
                (identity,),
            )
            append_event(
                uow,
                goal_id=str(goal[0]),
                task_id=str(binding.scope.task_id),
                actor=actor.owner_id,
                kind="invocation.unknown",
                payload={"invocation_id": identity, "receipt_sha256": None},
            )
        append_event(
            uow,
            goal_id=str(goal[0]),
            task_id=str(binding.scope.task_id),
            actor=actor.owner_id,
            kind="sandbox.launch.reconciled",
            payload={
                "invocation_id": identity,
                "launch_id": str(intent.launch_id),
                **observation.model_dump(mode="json"),
            },
        )
