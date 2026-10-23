"""Optional trusted-controller intersection, never constructed from worker data."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import psycopg

from panestria.contracts.build import canonical_sha256
from panestria.kernel.errors import KernelDenied


def worker_failure_code(error: Exception) -> str:
    """Closed diagnostic categories only; never SQL, process output or exception text."""
    if isinstance(error, psycopg.errors.LockNotAvailable):
        return "database_lock_timeout"
    if isinstance(error, psycopg.errors.QueryCanceled):
        return "database_statement_timeout"
    if isinstance(error, psycopg.errors.DeadlockDetected):
        return "database_deadlock"
    if isinstance(error, psycopg.errors.SerializationFailure):
        return "database_serialization_failure"
    if isinstance(error, psycopg.OperationalError):
        return "database_unavailable"
    if isinstance(error, KernelDenied):
        return "controller_authority_denied"
    return "worker_execution_unconfirmed"


@dataclass(frozen=True)
class WorkerAuthority:
    binding_sha256: str
    authorize: Callable[[psycopg.Connection[Any]], None]
    refresh: Callable[[], None]


def intersect_authorities(*values: WorkerAuthority | None) -> WorkerAuthority | None:
    guards = tuple(value for value in values if value is not None)
    if not guards:
        return None
    if len(guards) == 1:
        return guards[0]

    def authorize(connection: psycopg.Connection[Any]) -> None:
        for guard in guards:
            guard.authorize(connection)

    def refresh() -> None:
        for guard in guards:
            guard.refresh()

    return WorkerAuthority(canonical_sha256([g.binding_sha256 for g in guards]), authorize, refresh)
