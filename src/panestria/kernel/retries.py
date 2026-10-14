"""Persist bounded retry eligibility and fence the failed attempt."""

from __future__ import annotations

import math
from datetime import datetime

from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.leases import LeaseService
from panestria.kernel.repositories.tasks import append_event
from panestria.kernel.uow import UnitOfWork

_RETRYABLE = frozenset({"transport", "timeout", "rate_limited"})


def retry_delay(attempt_number: int, *, jitter: float, retry_after_seconds: int | None = None) -> float:
    if (
        type(attempt_number) is not int
        or not 1 <= attempt_number <= 20
        or not math.isfinite(jitter)
        or not 0 <= jitter <= 1
    ):
        raise KernelDenied("invalid_retry")
    if retry_after_seconds is not None and (
        type(retry_after_seconds) is not int or not 1 <= retry_after_seconds <= 3600
    ):
        raise KernelDenied("invalid_retry")
    delay = min(60.0, 2.0 ** (attempt_number - 1) * (1 + jitter))
    return max(delay, float(retry_after_seconds or 0))


class RetryService:
    def schedule(
        self,
        uow: UnitOfWork,
        actor: Actor,
        attempt_id: str,
        epoch: int,
        failure_code: str,
        *,
        jitter: float,
        retry_after_seconds: int | None = None,
    ) -> datetime | None:
        task_id = LeaseService().require_current(uow, actor, attempt_id, epoch)
        row = uow.execute(
            "SELECT t.goal_id::text,a.attempt_number,LEAST(t.max_attempts,"
            " COALESCE((c.body->'budget'->>'max_attempts_per_task')::integer,t.max_attempts))"
            " FROM panestria.task t JOIN panestria.task_attempt a ON a.task_id=t.id AND a.id=%s"
            " JOIN panestria.goal_contract c ON c.id=t.contract_id WHERE t.id=%s",
            (attempt_id, task_id),
        ).fetchone()
        assert row is not None
        delay = retry_delay(int(row[1]), jitter=jitter, retry_after_seconds=retry_after_seconds)
        retry = failure_code in _RETRYABLE and row[1] < row[2]
        uow.execute(
            "UPDATE panestria.task_attempt SET status='FAILED',finished_at=clock_timestamp(),error_code=%s WHERE id=%s",
            (failure_code if failure_code in _RETRYABLE else "non_retryable", attempt_id),
        )
        updated = uow.execute(
            "UPDATE panestria.task SET state=%s,lease_epoch=lease_epoch+1,row_version=row_version+1,"
            " retry_at=CASE WHEN %s THEN clock_timestamp()+make_interval(secs => %s) ELSE NULL END"
            " WHERE id=%s RETURNING retry_at",
            ("RETRY_WAIT" if retry else "FAILED", retry, delay, task_id),
        ).fetchone()
        assert updated is not None
        append_event(
            uow,
            goal_id=str(row[0]),
            task_id=task_id,
            kind="retry.scheduled" if retry else "retry.exhausted",
            actor=actor.owner_id,
            payload={"attempt_id": attempt_id, "delay_seconds": delay if retry else None, "retryable": retry},
        )
        return updated[0]  # type: ignore[no-any-return]
