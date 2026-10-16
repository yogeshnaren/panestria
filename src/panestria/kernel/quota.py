"""Same-Postgres quota evidence. No inference, permission or cash reservation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from psycopg.pq import TransactionStatus
from pydantic import TypeAdapter, ValidationError

from panestria.contracts.quota import QuotaId, QuotaObservation, QuotaScope
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.repositories.policy import lock_project
from panestria.kernel.repositories.tasks import append_event, lock_task
from panestria.kernel.uow import UnitOfWork

_ID = TypeAdapter(QuotaId)
_COLUMNS = "body,body_sha256,scope_sha256,source,observed_at,resets_at,fresh_for_seconds,created_at,task_id::text"


@dataclass(frozen=True)
class QuotaView:
    observation: QuotaObservation
    recorded_at: datetime
    evaluated_at: datetime
    freshness: Literal["FRESH", "STALE", "RESET_PASSED"]
    confidence: Literal["REPORTED", "ESTIMATED", "UNKNOWN"]
    effective_remaining: str | None
    replayed: bool = False
    authority: Literal["OBSERVATION_ONLY"] = "OBSERVATION_ONLY"


def _id(value: str) -> str:
    try:
        return _ID.validate_python(value)
    except ValidationError:
        raise KernelDenied("invalid_quota_identifier") from None


def _clock(uow: UnitOfWork) -> datetime:
    row = uow.execute("SELECT clock_timestamp()").fetchone()
    assert row is not None
    return row[0]  # type: ignore[no-any-return]


def _decoded(row: tuple[Any, ...]) -> QuotaObservation:
    try:
        observation = QuotaObservation.model_validate_json(json.dumps(row[0]))
        if (
            observation.sha256() != str(row[1]).strip()
            or observation.scope.sha256() != str(row[2]).strip()
            or observation.source != row[3]
            or observation.observed_at != row[4]
            or observation.resets_at != row[5]
            or observation.fresh_for_seconds != row[6]
        ):
            raise ValueError
        return observation
    except (ValueError, TypeError, ValidationError):
        raise KernelDenied("quota_observation_corrupt") from None


def _view(observation: QuotaObservation, recorded: datetime, now: datetime, *, replayed: bool = False) -> QuotaView:
    freshness: Literal["FRESH", "STALE", "RESET_PASSED"] = (
        "RESET_PASSED"
        if observation.resets_at is not None and observation.resets_at <= now
        else "STALE"
        if now < observation.observed_at
        or observation.observed_at + timedelta(seconds=observation.fresh_for_seconds) <= now
        else "FRESH"
    )
    confidence: Literal["REPORTED", "ESTIMATED", "UNKNOWN"] = (
        "UNKNOWN"
        if freshness != "FRESH" or observation.source == "UNKNOWN" or observation.remaining is None
        else "ESTIMATED"
        if observation.source == "ESTIMATED"
        else "REPORTED"
    )
    return QuotaView(
        observation,
        recorded,
        now,
        freshness,
        confidence,
        observation.remaining if confidence != "UNKNOWN" else None,
        replayed,
    )


class QuotaService:
    @staticmethod
    def _transaction(uow: UnitOfWork) -> None:
        if uow.connection.autocommit and uow.connection.info.transaction_status != TransactionStatus.INTRANS:
            raise KernelDenied("quota_caller_transaction_required")

    def record(self, uow: UnitOfWork, actor: Actor, task_id: str, observation: QuotaObservation) -> QuotaView:
        # This is trusted ingestion. A future collector must obtain actual
        # supported provider evidence before selecting PROVIDER_REPORTED.
        # HTTP input below is restricted to the owner/unknown lanes.
        self._transaction(uow)
        try:
            observation = QuotaObservation.model_validate(observation)
        except ValidationError:
            raise KernelDenied("invalid_quota_observation") from None
        task_id = _id(task_id)
        lock_project(uow, actor)
        task = lock_task(uow, actor.owner_id, actor.project_id, task_id)
        if task is None:
            raise KernelDenied("not_found")
        prior = uow.execute(
            "SELECT " + _COLUMNS + " FROM panestria.quota_observation WHERE id=%s AND owner_id=%s AND project_id=%s",
            (observation.observation_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if prior is not None:
            if _decoded(prior).sha256() != observation.sha256() or prior[8] != task_id:
                raise KernelDenied("quota_observation_conflict")
            return _view(observation, prior[7], _clock(uow), replayed=True)
        now = _clock(uow)
        if observation.observed_at > now:
            raise KernelDenied("quota_observed_in_future")
        count = uow.execute(
            "SELECT count(*) FROM panestria.quota_observation WHERE owner_id=%s AND project_id=%s",
            (actor.owner_id, actor.project_id),
        ).fetchone()
        assert count is not None
        if count[0] >= 10000:
            raise KernelDenied("quota_observation_storage_limit")
        inserted = uow.execute(
            "INSERT INTO panestria.quota_observation(id,owner_id,project_id,goal_id,task_id,scope_sha256,"
            "source,observed_at,resets_at,fresh_for_seconds,body,body_sha256) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s) "
            "ON CONFLICT(id) DO NOTHING RETURNING created_at",
            (
                observation.observation_id,
                actor.owner_id,
                actor.project_id,
                task[0],
                task_id,
                observation.scope.sha256(),
                observation.source,
                observation.observed_at,
                observation.resets_at,
                observation.fresh_for_seconds,
                observation.model_dump_json(),
                observation.sha256(),
            ),
        ).fetchone()
        if inserted is None:
            raise KernelDenied("quota_observation_conflict")
        append_event(
            uow,
            goal_id=task[0],
            task_id=task_id,
            kind="quota.observed",
            actor=actor.owner_id,
            payload={"observation_id": observation.observation_id, "body_sha256": observation.sha256()},
        )
        return _view(observation, inserted[0], _clock(uow))

    def read(self, uow: UnitOfWork, actor: Actor, observation_id: str) -> QuotaView:
        row = uow.execute(
            "SELECT " + _COLUMNS + " FROM panestria.quota_observation WHERE id=%s AND owner_id=%s AND project_id=%s",
            (_id(observation_id), actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        body = _decoded(row)
        if body.observation_id != observation_id:
            raise KernelDenied("quota_observation_corrupt")
        return _view(body, row[7], _clock(uow))

    def latest(self, uow: UnitOfWork, actor: Actor, scope: QuotaScope) -> tuple[QuotaView, ...]:
        try:
            scope = QuotaScope.model_validate(scope)
        except ValidationError:
            raise KernelDenied("invalid_quota_scope") from None
        rows = uow.execute(
            "SELECT DISTINCT ON(source) " + _COLUMNS + " FROM panestria.quota_observation "
            "WHERE owner_id=%s AND project_id=%s AND scope_sha256=%s "
            "ORDER BY source,observed_at DESC,created_at DESC,id DESC",
            (actor.owner_id, actor.project_id, scope.sha256()),
        ).fetchall()
        now, results = _clock(uow), []
        for row in rows:
            observation = _decoded(row)
            if observation.scope != scope:
                raise KernelDenied("quota_observation_corrupt")
            results.append(_view(observation, row[7], now))
        return tuple(results)
