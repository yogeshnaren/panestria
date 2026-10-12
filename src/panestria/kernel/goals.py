"""Scoped goal admission and idempotency. The caller commits."""

from __future__ import annotations

import json
from collections.abc import Mapping
from uuid import uuid4

from psycopg.errors import ForeignKeyViolation, UniqueViolation

from panestria.contracts.acceptance import ContractRejected
from panestria.contracts.goal import contract_sha256, load_contract
from panestria.kernel.errors import KernelDenied
from panestria.kernel.repositories.goals import (
    insert_contract,
    insert_goal,
    insert_idempotency,
    lock_idempotency,
    read_events,
    read_goal,
)
from panestria.kernel.repositories.tasks import append_event
from panestria.kernel.uow import UnitOfWork

_CLIENT_AUTHORITY = frozenset({"approved_by", "policy_granted", "action_permit"})


class Actor:
    def __init__(self, owner_id: str, project_id: str) -> None:
        self.owner_id = owner_id
        self.project_id = project_id


class GoalReceipt:
    def __init__(self, goal_id: str, contract_version: int, contract_sha256: str, replayed: bool) -> None:
        self.goal_id = goal_id
        self.contract_version = contract_version
        self.contract_sha256 = contract_sha256
        self.replayed = replayed


class GoalView:
    def __init__(self, goal_id: str, status: str) -> None:
        self.goal_id = goal_id
        self.status = status


class GoalService:
    def events(
        self,
        uow: UnitOfWork,
        actor: Actor,
        goal_id: str,
        after: int,
        limit: int,
    ) -> list[tuple[int, str, dict[str, object]]]:
        rows = read_events(uow, actor.owner_id, actor.project_id, goal_id, after, limit)
        if rows is None:
            raise KernelDenied("not_found")
        return rows

    def get(self, uow: UnitOfWork, actor: Actor, goal_id: str) -> GoalView:
        row = read_goal(uow, actor.owner_id, actor.project_id, goal_id)
        if row is None:
            raise KernelDenied("not_found")
        found_id, status = row
        return GoalView(found_id, status)

    def submit(
        self,
        uow: UnitOfWork,
        actor: Actor,
        request: Mapping[str, object],
        idempotency_key: str,
    ) -> GoalReceipt:
        if _CLIENT_AUTHORITY.intersection(request):
            raise KernelDenied("invalid_contract")
        try:
            contract = load_contract(dict(request))
        except ContractRejected as exc:
            raise KernelDenied(exc.code) from None
        if contract.owner_id != actor.owner_id or contract.project_id != actor.project_id:
            raise KernelDenied("not_found")
        digest = contract_sha256(contract)
        existing = lock_idempotency(uow, actor.owner_id, actor.project_id, idempotency_key)
        if existing is not None:
            return _replay(existing, digest)
        receipt = GoalReceipt(str(contract.goal_id), contract.contract_version, digest, False)
        body = json.dumps(json.loads(contract.model_dump_json()), separators=(",", ":"), sort_keys=True)
        try:
            insert_goal(uow, str(contract.goal_id), actor.owner_id, actor.project_id, contract.intent)
            insert_contract(uow, str(uuid4()), str(contract.goal_id), contract.contract_version, body, digest)
        except ForeignKeyViolation:
            raise KernelDenied("not_found") from None
        response = json.dumps(
            {
                "contract_sha256": digest,
                "contract_version": receipt.contract_version,
                "goal_id": receipt.goal_id,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        try:
            insert_idempotency(uow, actor.owner_id, actor.project_id, idempotency_key, digest, response)
        except UniqueViolation:
            raise KernelDenied("idempotency_conflict") from None
        append_event(
            uow,
            goal_id=str(contract.goal_id),
            task_id=None,
            kind="goal.submitted",
            actor=actor.owner_id,
            payload={"idempotency_key": idempotency_key},
        )
        return receipt


def _replay(existing: tuple[str, object], digest: str) -> GoalReceipt:
    stored_hash, response = existing
    if stored_hash != digest:
        raise KernelDenied("idempotency_conflict")
    if isinstance(response, str):
        loaded = json.loads(response)
    else:
        loaded = response
    if not isinstance(loaded, dict):
        raise KernelDenied("invalid_contract")
    return GoalReceipt(
        str(loaded["goal_id"]),
        int(loaded["contract_version"]),
        str(loaded["contract_sha256"]),
        True,
    )
