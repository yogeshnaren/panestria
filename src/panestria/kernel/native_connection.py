"""Current native account/context grant intersection; no transport or secret reads.

Reservations live in the existing immutable event ledger and never refund an
uncertain launch. Existing policy/certificate/lease/invocation checks still own
execution. Monitoring uses read-only queries, never project lock upgrades.
"""

import json
from datetime import timedelta
from typing import Any

from panestria.contracts.native_account import NativeAccountObservation
from panestria.contracts.native_connection import NativeConnectionReservation, NativeConnectionSelection
from panestria.contracts.native_tools import ToolScope
from panestria.kernel.connections import ConnectionDeclaration, ConnectionReviewService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.leases import LeaseService
from panestria.kernel.repositories.policy import current_policy, lock_project
from panestria.kernel.repositories.tasks import append_event
from panestria.kernel.uow import UnitOfWork


class NativeConnectionBroker:
    def _rows(self, uow: UnitOfWork, actor: Actor, selection: NativeConnectionSelection) -> list[tuple[Any, ...]]:
        rows = uow.execute(
            "SELECT e.seq,e.payload,e.occurred_at FROM panestria.task_event e "
            "JOIN panestria.goal g ON g.id=e.goal_id WHERE g.owner_id=%s AND g.project_id=%s "
            "AND e.kind='native_connection.reserved' "
            "AND e.payload->'reservation'->'selection'->>'grant_id'=%s "
            "AND e.payload->'reservation'->'selection'->>'version'=%s ORDER BY e.seq LIMIT 65",
            (actor.owner_id, actor.project_id, selection.grant_id, str(selection.version)),
        ).fetchall()
        if len(rows) > 64:
            raise KernelDenied("native_connection_history_limit")
        return rows

    @staticmethod
    def _record(row: tuple[Any, ...], actor: Actor) -> NativeConnectionReservation:
        try:
            value = NativeConnectionReservation.model_validate_json(json.dumps(row[1]["reservation"]))
            if value.sha256() != row[1]["reservation_sha256"] or (
                str(value.scope.owner_id),
                str(value.scope.project_id),
            ) != (actor.owner_id, actor.project_id):
                raise ValueError
            return value
        except (ValueError, KeyError, TypeError):
            raise KernelDenied("native_connection_reservation_invalid") from None

    def authorize(
        self,
        uow: UnitOfWork,
        actor: Actor,
        selection: NativeConnectionSelection,
        configuration_sha256: str,
        observation: NativeAccountObservation,
        scope: ToolScope | None = None,
    ) -> ConnectionDeclaration:
        declaration = ConnectionReviewService().current(uow, actor, selection.grant_id)
        manifest = declaration.manifest
        policy = current_policy(uow, actor)
        if (
            declaration.version != selection.version
            or declaration.state != "DECLARED_ACTIVE"
            or declaration.policy_status != "CURRENT"
            or (scope is not None and declaration.policy_ref != scope.policy_ref)
        ):
            raise KernelDenied("native_connection_not_current")
        if (
            manifest.schema_version != 2
            or manifest.conformance_sha256 != policy.trust.runtime_certificate_sha256
            or manifest.configuration_sha256 != configuration_sha256
            or manifest.account_ref != observation.account_ref
            or manifest.root_refs != (observation.profile_sha256,)
            or (observation.owner_id, observation.project_id) != (actor.owner_id, actor.project_id)
        ):
            raise KernelDenied("native_connection_account_or_configuration_changed")
        now = uow.execute("SELECT clock_timestamp()").fetchone()
        assert now is not None
        if not observation.observed_at <= now[0] < observation.observed_at + timedelta(seconds=300):
            raise KernelDenied("native_connection_account_observation_stale_or_future")
        rows = self._rows(uow, actor, selection)
        records = [self._record(row, actor) for row in rows]
        if any(r.configuration_sha256 != configuration_sha256 for r in records):
            raise KernelDenied("native_connection_reservation_invalid")
        if len(rows) > manifest.budget.max_calls or sum(r.context_bytes for r in records) > manifest.budget.max_bytes:
            raise KernelDenied("native_connection_budget_unconfirmed")
        if rows and not 0 <= (now[0] - rows[0][2]).total_seconds() < manifest.budget.max_wall_seconds:
            raise KernelDenied("native_connection_deadline")
        return declaration

    def reserve(
        self,
        uow: UnitOfWork,
        actor: Actor,
        reservation: NativeConnectionReservation,
        observation: NativeAccountObservation,
    ) -> None:
        ConnectionReviewService._transaction(uow)
        lock_project(uow, actor)  # Before any task/share lock; serializes grant/revoke/capacity.
        scope, selection = reservation.scope, reservation.selection
        if (str(scope.owner_id), str(scope.project_id)) != (actor.owner_id, actor.project_id):
            raise KernelDenied("not_found")
        declaration = self.authorize(uow, actor, selection, reservation.configuration_sha256, observation, scope)
        rows = self._rows(uow, actor, selection)
        records = [self._record(row, actor) for row in rows]
        for old in records:
            if old.scope.attempt_id == scope.attempt_id:
                if old != reservation:
                    raise KernelDenied("native_connection_reservation_conflict")
                return  # Exact acknowledged reservation, never another dispatch.
        if len(rows) >= declaration.manifest.budget.max_calls or (
            sum(r.context_bytes for r in records) + reservation.context_bytes > declaration.manifest.budget.max_bytes
        ):
            raise KernelDenied("native_connection_budget_exhausted")
        if LeaseService().require_current(uow, actor, str(scope.attempt_id), scope.lease_epoch) != str(scope.task_id):
            raise KernelDenied("native_connection_scope_mismatch")
        task = uow.execute(
            "SELECT t.goal_id::text,c.sha256,c.body FROM panestria.task t JOIN panestria.goal g ON g.id=t.goal_id "
            "JOIN panestria.goal_contract c ON c.id=t.contract_id "
            "WHERE t.id=%s AND g.owner_id=%s AND g.project_id=%s",
            (str(scope.task_id), actor.owner_id, actor.project_id),
        ).fetchone()
        if (
            task is None
            or str(task[1]).strip() != scope.contract_sha256
            or (
                task[2].get("privacy_class") != "PUBLIC"
                or task[2].get("constraints", {}).get("cloud_egress") != "allow"
            )
        ):
            raise KernelDenied("not_found")
        append_event(
            uow,
            goal_id=task[0],
            task_id=str(scope.task_id),
            actor=actor.owner_id,
            kind="native_connection.reserved",
            payload={"reservation": reservation.model_dump(mode="json"), "reservation_sha256": reservation.sha256()},
        )

    def require_reserved(
        self,
        uow: UnitOfWork,
        actor: Actor,
        reservation: NativeConnectionReservation,
        observation: NativeAccountObservation,
    ) -> None:
        self.authorize(
            uow, actor, reservation.selection, reservation.configuration_sha256, observation, reservation.scope
        )
        if reservation not in [self._record(r, actor) for r in self._rows(uow, actor, reservation.selection)]:
            raise KernelDenied("native_connection_reservation_required")
