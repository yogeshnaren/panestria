"""Dispatch only after intent commit; never blindly retry an ambiguous effect."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import psycopg

from panestria.kernel.effects import DispatchClaim, EffectRef, SideEffectService
from panestria.kernel.goals import Actor
from panestria.kernel.uow import UnitOfWork


@dataclass(frozen=True)
class Confirmed:
    receipt: str


@dataclass(frozen=True)
class NoEffect:
    """Only a definitive target query can establish no effect. Still requires reviewed retry."""


@dataclass(frozen=True)
class Unknown:
    reason: str = "owner_resolution_required"


class EffectTarget(Protocol):
    def dispatch(self, claim: DispatchClaim) -> str: ...
    def query(self, claim: DispatchClaim) -> Confirmed | NoEffect | Unknown: ...


class EffectExecutor:
    def __init__(self, connect: Callable[[], psycopg.Connection[Any]], target: EffectTarget) -> None:
        self._connect = connect
        self._target = target
        self._service = SideEffectService()

    def dispatch(self, actor: Actor, effect_id: str) -> None:
        with self._connect() as connection:
            claim = self._service.claim(UnitOfWork(connection), actor, effect_id)
        # Claim and intent are committed before any external I/O.
        try:
            receipt = self._target.dispatch(claim)
        except Exception:
            receipt = None  # A transport exception is not proof that nothing happened.
        with self._connect() as connection:
            self._service.finish(UnitOfWork(connection), actor, claim, receipt)

    def reconcile(self, actor: Actor, effect_id: str) -> EffectRef:
        with self._connect() as connection:
            claim = self._service.begin_reconciliation(UnitOfWork(connection), actor, effect_id)
        try:
            outcome = self._target.query(claim)
        except Exception:
            outcome = Unknown()
        receipt = outcome.receipt if isinstance(outcome, Confirmed) else None
        with self._connect() as connection:
            return self._service.reconciled(UnitOfWork(connection), actor, claim, receipt)
