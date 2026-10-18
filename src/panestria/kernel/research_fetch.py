"""One-use source reservations; uncertain/failed transfers never refund or retry."""

import hashlib
from dataclasses import dataclass
from typing import Literal
from uuid import uuid4

from panestria.contracts.build import canonical_sha256
from panestria.contracts.research_admission import FetchPlan
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.repositories.tasks import append_event, lock_task
from panestria.kernel.research_authority import require_public_research
from panestria.kernel.uow import UnitOfWork
from panestria.policy.research_fetch import PublicFetchCertificateStore


@dataclass(frozen=True)
class FetchDispatch:
    dispatch_id: str
    ordinal: int
    body_cap: int
    max_redirects: int


class FetchAdmissionService:
    def __init__(self, certificates: PublicFetchCertificateStore) -> None:
        if type(certificates) is not PublicFetchCertificateStore:
            raise KernelDenied("public_fetch_certificate_store_required")
        self.certificates = certificates

    def current(self, uow: UnitOfWork, actor: Actor, plan: FetchPlan, attempt_id: str, epoch: int) -> float:
        return require_public_research(
            uow, actor, FetchPlan.model_validate(plan), attempt_id, epoch, self.certificates, "public-fetch"
        )

    def prepare(self, uow: UnitOfWork, actor: Actor, plan: FetchPlan, attempt_id: str, epoch: int) -> None:
        self.current(uow, actor, plan, attempt_id, epoch)
        old = uow.execute(
            "SELECT plan_sha256 FROM panestria.fetch_plan WHERE task_id=%s", (plan.scope.task_id,)
        ).fetchone()
        digest = canonical_sha256(plan.model_dump())
        if old is not None:
            if str(old[0]).strip() != digest:
                raise KernelDenied("fetch_plan_conflict")
            return
        uow.execute(
            "INSERT INTO panestria.fetch_plan(task_id,request_id,plan_sha256,request_sha256,contract_sha256,"
            "policy_sha256,configuration_sha256) VALUES(%s,%s,%s,%s,%s,%s,%s)",
            (
                plan.scope.task_id,
                plan.request_id,
                digest,
                plan.request_sha256,
                plan.contract_sha256,
                plan.policy_sha256,
                plan.configuration_sha256,
            ),
        )
        append_event(
            uow,
            goal_id=plan.scope.goal_id,
            task_id=plan.scope.task_id,
            actor=actor.owner_id,
            kind="fetch.plan.prepared",
            payload={"plan_sha256": digest},
        )

    def claim(
        self, uow: UnitOfWork, actor: Actor, plan: FetchPlan, attempt_id: str, epoch: int, url_sha256: str
    ) -> FetchDispatch:
        self.current(uow, actor, plan, attempt_id, epoch)
        old = uow.execute(
            "SELECT plan_sha256 FROM panestria.fetch_plan WHERE task_id=%s", (plan.scope.task_id,)
        ).fetchone()
        if old is None or str(old[0]).strip() != canonical_sha256(plan.model_dump()):
            raise KernelDenied("fetch_plan_conflict")
        limits = uow.execute(
            "SELECT max_sources,max_source_bytes,max_total_bytes,max_redirects "
            "FROM panestria.research_request WHERE id=%s",
            (plan.request_id,),
        ).fetchone()
        assert limits is not None
        if (
            uow.execute(
                "SELECT 1 FROM panestria.fetch_dispatch WHERE task_id=%s AND url_sha256=%s",
                (plan.scope.task_id, url_sha256),
            ).fetchone()
            is not None
        ):
            raise KernelDenied("fetch_already_dispatched")
        consumed = uow.execute(
            "SELECT count(*),coalesce(sum(reserved_body_bytes),0) FROM panestria.fetch_dispatch WHERE task_id=%s",
            (plan.scope.task_id,),
        ).fetchone()
        assert consumed is not None
        cap = min(int(limits[1]), int(limits[2]) - int(consumed[1]) - 1)
        if int(consumed[0]) >= int(limits[0]) or cap < 1:
            raise KernelDenied("fetch_budget_exhausted")
        dispatch = FetchDispatch(str(uuid4()), int(consumed[0]) + 1, cap, int(limits[3]))
        uow.execute(
            "INSERT INTO panestria.fetch_dispatch(id,task_id,request_id,attempt_id,lease_epoch,ordinal,"
            "url_sha256,reserved_body_bytes) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                dispatch.dispatch_id,
                plan.scope.task_id,
                plan.request_id,
                attempt_id,
                epoch,
                dispatch.ordinal,
                url_sha256,
                cap + 1,
            ),
        )
        append_event(
            uow,
            goal_id=plan.scope.goal_id,
            task_id=plan.scope.task_id,
            actor=actor.owner_id,
            kind="fetch.body.reserved",
            payload={
                "dispatch_id": dispatch.dispatch_id,
                "ordinal": dispatch.ordinal,
                "url_sha256": url_sha256,
                "reserved_body_bytes": cap + 1,
                "observed": "UNKNOWN",
            },
        )
        return dispatch

    def hop(
        self,
        uow: UnitOfWork,
        actor: Actor,
        plan: FetchPlan,
        attempt_id: str,
        epoch: int,
        dispatch_id: str,
        ordinal: int,
        url: str,
        host: str,
    ) -> None:
        self.current(uow, actor, plan, attempt_id, epoch)
        dispatch = uow.execute(
            "SELECT url_sha256 FROM panestria.fetch_dispatch "
            "WHERE id=%s AND task_id=%s AND attempt_id=%s AND lease_epoch=%s",
            (dispatch_id, plan.scope.task_id, attempt_id, epoch),
        ).fetchone()
        limit = uow.execute(
            "SELECT max_redirects FROM panestria.research_request WHERE id=%s", (plan.request_id,)
        ).fetchone()
        count = uow.execute("SELECT count(*) FROM panestria.fetch_hop WHERE dispatch_id=%s", (dispatch_id,)).fetchone()
        digest = hashlib.sha256(url.encode()).hexdigest()
        if (
            dispatch is None
            or limit is None
            or count is None
            or ordinal != int(count[0])
            or not 0 <= ordinal <= int(limit[0])
            or (ordinal == 0 and digest != str(dispatch[0]).strip())
        ):
            raise KernelDenied("fetch_hop_not_current")
        host_sha = hashlib.sha256(host.encode()).hexdigest()
        uow.execute(
            "INSERT INTO panestria.fetch_hop(dispatch_id,ordinal,url_sha256,host_sha256,url_bytes) "
            "VALUES(%s,%s,%s,%s,%s)",
            (dispatch_id, ordinal, digest, host_sha, len(url.encode())),
        )
        append_event(
            uow,
            goal_id=plan.scope.goal_id,
            task_id=plan.scope.task_id,
            actor=actor.owner_id,
            kind="fetch.outbound.authorized",
            payload={
                "dispatch_id": dispatch_id,
                "ordinal": ordinal,
                "url_sha256": digest,
                "host_sha256": host_sha,
                "url_bytes": len(url.encode()),
                "authorized": "YES",
                "accessible": "YES",
                "observed": "UNKNOWN",
            },
        )

    def finish(
        self,
        uow: UnitOfWork,
        actor: Actor,
        task_id: str,
        dispatch_id: str,
        status: Literal["RETAINED", "FETCH_ERROR", "READER_ERROR", "UNKNOWN"],
        snapshot_id: str | None = None,
    ) -> None:
        # Historical-only receipt after cancellation; no authority or refund.
        if uow.connection.autocommit:
            raise KernelDenied("fetch_caller_transaction_required")
        task = lock_task(uow, actor.owner_id, actor.project_id, task_id)
        dispatch = uow.execute(
            "SELECT request_id::text FROM panestria.fetch_dispatch WHERE id=%s AND task_id=%s", (dispatch_id, task_id)
        ).fetchone()
        if task is None or dispatch is None:
            raise KernelDenied("not_found")
        source = None
        if snapshot_id is not None:
            source = uow.execute(
                "SELECT s.body_sha256 FROM panestria.research_source_snapshot s "
                "JOIN panestria.research_source_capture c "
                "ON c.snapshot_id=s.id WHERE s.id=%s AND s.request_id=%s AND s.task_id=%s "
                "AND s.owner_id=%s AND s.project_id=%s",
                (snapshot_id, dispatch[0], task_id, actor.owner_id, actor.project_id),
            ).fetchone()
            if source is None:
                raise KernelDenied("fetch_retained_source_mismatch")
        old = uow.execute(
            "SELECT status,snapshot_id::text FROM panestria.fetch_outcome WHERE dispatch_id=%s", (dispatch_id,)
        ).fetchone()
        if old is not None:
            if old != (status, snapshot_id):
                raise KernelDenied("fetch_outcome_conflict")
            return
        uow.execute(
            "INSERT INTO panestria.fetch_outcome(dispatch_id,task_id,request_id,status,snapshot_id,"
            "source_metadata_sha256) "
            "VALUES(%s,%s,%s,%s,%s,%s)",
            (dispatch_id, task_id, dispatch[0], status, snapshot_id, str(source[0]).strip() if source else None),
        )
        append_event(
            uow,
            goal_id=task[0],
            task_id=task_id,
            actor=actor.owner_id,
            kind="fetch.outbound.finished",
            payload={"dispatch_id": dispatch_id, "status": status, "snapshot_id": snapshot_id},
        )
