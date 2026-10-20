"""Scoped CAS leases. The caller commits; expiry never proves process cancellation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.repositories.tasks import append_event, lock_task
from panestria.kernel.uow import UnitOfWork


@dataclass(frozen=True)
class AttemptLease:
    attempt_id: str
    task_id: str
    epoch: int
    attempt_number: int
    row_version: int
    expires_at: datetime


class LeaseService:
    def acquire(
        self,
        uow: UnitOfWork,
        actor: Actor,
        task_id: str,
        adapter: str,
        expected_version: int,
        *,
        ttl_seconds: int = 60,
        emit_event: bool = True,
    ) -> AttemptLease:
        if not 1 <= ttl_seconds <= 3600 or not adapter or len(adapter) > 128:
            raise KernelDenied("invalid_lease")
        locked = lock_task(uow, actor.owner_id, actor.project_id, task_id)
        if locked is None:
            raise KernelDenied("not_found")
        goal_id, state, version, epoch = locked
        if version != expected_version:
            raise KernelDenied("version_conflict")
        current = uow.execute(
            "SELECT id::text, lease_expires_at > clock_timestamp(), status"
            " FROM panestria.task_attempt WHERE task_id = %s AND lease_epoch = %s FOR UPDATE",
            (task_id, epoch),
        ).fetchone()
        reclaim = state in {"LEASED", "RUNNING"} and current is not None
        if reclaim:
            assert current is not None
            if current[1] is not False or current[2] not in {"PENDING", "RUNNING"}:
                raise KernelDenied("lease_active")
        elif state not in {"READY", "RETRY_WAIT"}:
            raise KernelDenied("illegal_transition")
        number, maximum, ready = uow.execute(
            "SELECT COALESCE((SELECT max(attempt_number) FROM panestria.task_attempt WHERE task_id = t.id),0)+1,"
            " LEAST(max_attempts,COALESCE((c.body->'budget'->>'max_attempts_per_task')::integer,max_attempts)),"
            " retry_at IS NULL OR retry_at <= clock_timestamp() FROM panestria.task t"
            " JOIN panestria.goal_contract c ON c.id=t.contract_id WHERE t.id = %s",
            (task_id,),
        ).fetchone() or (0, 0, False)
        if number > maximum:
            raise KernelDenied("attempts_exhausted")
        if not ready:
            raise KernelDenied("retry_not_due")
        if reclaim:
            assert current is not None
            uow.execute(
                "UPDATE panestria.task_attempt SET status='LOST', finished_at=clock_timestamp(),"
                " error_code='lease_expired' WHERE id=%s",
                (current[0],),
            )
        attempt_id = str(uuid4())
        expiry = uow.execute(
            "INSERT INTO panestria.task_attempt"
            " (id,task_id,attempt_number,lease_epoch,status,adapter,started_at,heartbeat_at,lease_expires_at)"
            " VALUES (%s,%s,%s,%s,'RUNNING',%s,clock_timestamp(),clock_timestamp(),"
            " clock_timestamp()+make_interval(secs => %s)) RETURNING lease_expires_at",
            (attempt_id, task_id, number, epoch + 1, adapter, ttl_seconds),
        ).fetchone()
        assert expiry is not None
        uow.execute(
            "UPDATE panestria.task SET state='RUNNING', lease_epoch=%s, row_version=row_version+1,"
            " retry_at=NULL, updated_at=clock_timestamp() WHERE id=%s",
            (epoch + 1, task_id),
        )
        if emit_event:
            append_event(
                uow,
                goal_id=goal_id,
                task_id=task_id,
                kind="lease.acquired",
                actor=actor.owner_id,
                payload={"attempt_id": attempt_id, "epoch": epoch + 1, "reclaimed": reclaim},
            )
        return AttemptLease(attempt_id, task_id, epoch + 1, int(number), version + 1, expiry[0])

    def require_current(self, uow: UnitOfWork, actor: Actor, attempt_id: str, epoch: int) -> str:
        hint = uow.execute("SELECT task_id::text FROM panestria.task_attempt WHERE id=%s", (attempt_id,)).fetchone()
        if hint is None:
            raise KernelDenied("not_found")
        task_id = str(hint[0])
        locked = lock_task(uow, actor.owner_id, actor.project_id, task_id)
        if locked is None:
            raise KernelDenied("not_found")
        row = uow.execute(
            "SELECT lease_epoch, status, lease_expires_at > clock_timestamp()"
            " FROM panestria.task_attempt WHERE id=%s AND task_id=%s FOR UPDATE",
            (attempt_id, task_id),
        ).fetchone()
        if row is None or locked[3] != epoch or row[0] != epoch or row[1] != "RUNNING" or row[2] is not True:
            raise KernelDenied("stale_lease")
        if locked[1] not in {"LEASED", "RUNNING", "VERIFYING"}:
            raise KernelDenied("stale_lease")
        return task_id

    def heartbeat(
        self, uow: UnitOfWork, actor: Actor, attempt_id: str, epoch: int, *, ttl_seconds: int = 60
    ) -> datetime:
        if not 1 <= ttl_seconds <= 3600:
            raise KernelDenied("invalid_lease")
        self.require_current(uow, actor, attempt_id, epoch)
        row = uow.execute(
            "UPDATE panestria.task_attempt SET heartbeat_at=clock_timestamp(),"
            " lease_expires_at=clock_timestamp()+make_interval(secs => %s)"
            " WHERE id=%s RETURNING lease_expires_at",
            (ttl_seconds, attempt_id),
        ).fetchone()
        assert row is not None
        return row[0]  # type: ignore[no-any-return]

    def release(self, uow: UnitOfWork, actor: Actor, attempt_id: str, epoch: int) -> None:
        task_id = self.require_current(uow, actor, attempt_id, epoch)
        goal = uow.execute("SELECT goal_id::text FROM panestria.task WHERE id=%s", (task_id,)).fetchone()
        assert goal is not None
        uow.execute(
            "UPDATE panestria.task_attempt SET status='LOST',finished_at=clock_timestamp(),"
            " error_code='lease_released' WHERE id=%s",
            (attempt_id,),
        )
        uow.execute(
            "UPDATE panestria.task SET lease_epoch=lease_epoch+1,row_version=row_version+1,"
            " state='RETRY_WAIT' WHERE id=%s",
            (task_id,),
        )
        append_event(
            uow,
            goal_id=str(goal[0]),
            task_id=task_id,
            kind="lease.released",
            actor=actor.owner_id,
            payload={"attempt_id": attempt_id, "epoch": epoch, "external_cancellation_confirmed": False},
        )
