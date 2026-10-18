"""Caller-owned transactions; a committed claim is consumed even after a crash.

No plaintext queries, result URLs or snippets are retained in this audit. The
ledger counts authorized outbound dispatches, never measured upstream usage.
"""

from dataclasses import dataclass
from typing import Literal
from uuid import uuid4

from psycopg.pq import TransactionStatus

from panestria.contracts.build import canonical_sha256
from panestria.contracts.search import SearchDisclosure
from panestria.contracts.search_admission import SearchPlan
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.repositories.tasks import append_event, lock_task
from panestria.kernel.research_authority import require_public_research
from panestria.kernel.uow import UnitOfWork
from panestria.policy.search import PublicSearchCertificateStore


@dataclass(frozen=True)
class SearchDispatch:
    dispatch_id: str
    ordinal: int
    disclosure_sha256: str


class SearchAdmissionService:
    def __init__(self, certificates: PublicSearchCertificateStore) -> None:
        if type(certificates) is not PublicSearchCertificateStore:
            raise KernelDenied("public_search_certificate_store_required")
        self.certificates = certificates

    def current(self, uow: UnitOfWork, actor: Actor, plan: SearchPlan, attempt_id: str, epoch: int) -> float:
        return require_public_research(
            uow, actor, SearchPlan.model_validate(plan), attempt_id, epoch, self.certificates, "public-search"
        )

    def prepare(self, uow: UnitOfWork, actor: Actor, plan: SearchPlan, attempt_id: str, epoch: int) -> None:
        self.current(uow, actor, plan, attempt_id, epoch)
        digest = canonical_sha256(plan.model_dump())
        old = uow.execute(
            "SELECT plan_sha256 FROM panestria.search_plan WHERE task_id=%s", (plan.scope.task_id,)
        ).fetchone()
        if old is not None:
            if str(old[0]).strip() != digest:
                raise KernelDenied("search_plan_conflict")
            return
        uow.execute(
            "INSERT INTO panestria.search_plan(task_id,request_id,request_sha256,contract_sha256,policy_sha256,"
            "configuration_sha256,max_queries,plan_sha256) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                plan.scope.task_id,
                plan.request_id,
                plan.request_sha256,
                plan.contract_sha256,
                plan.policy_sha256,
                plan.configuration_sha256,
                plan.max_queries,
                digest,
            ),
        )
        append_event(
            uow,
            goal_id=plan.scope.goal_id,
            task_id=plan.scope.task_id,
            actor=actor.owner_id,
            kind="search.plan.prepared",
            payload={"plan_sha256": digest, "max_queries": plan.max_queries},
        )

    def claim(
        self, uow: UnitOfWork, actor: Actor, plan: SearchPlan, attempt_id: str, epoch: int, disclosure: SearchDisclosure
    ) -> SearchDispatch:
        self.current(uow, actor, plan, attempt_id, epoch)
        disclosure = SearchDisclosure.model_validate(disclosure)
        if (
            disclosure.scope != plan.scope
            or str(disclosure.request_id) != plan.request_id
            or disclosure.configuration_sha256 != plan.configuration_sha256
        ):
            raise KernelDenied("search_disclosure_mismatch")
        row = uow.execute(
            "SELECT plan_sha256 FROM panestria.search_plan WHERE task_id=%s", (plan.scope.task_id,)
        ).fetchone()
        if row is None or str(row[0]).strip() != canonical_sha256(plan.model_dump()):
            raise KernelDenied("search_plan_conflict")
        if (
            uow.execute(
                "SELECT 1 FROM panestria.search_dispatch WHERE task_id=%s AND query_sha256=%s",
                (plan.scope.task_id, disclosure.query_sha256),
            ).fetchone()
            is not None
        ):
            raise KernelDenied("search_already_dispatched")
        count = uow.execute(
            "SELECT count(*) FROM panestria.search_dispatch WHERE task_id=%s", (plan.scope.task_id,)
        ).fetchone()
        assert count is not None
        if int(count[0]) >= plan.max_queries:
            raise KernelDenied("search_query_budget_exhausted")
        body = disclosure.model_dump(mode="json")
        receipt = SearchDispatch(str(uuid4()), int(count[0]) + 1, canonical_sha256(body))
        uow.execute(
            "INSERT INTO panestria.search_dispatch(id,task_id,attempt_id,lease_epoch,ordinal,query_sha256,"
            "disclosure_sha256,disclosure,request_id,configuration_sha256) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)",
            (
                receipt.dispatch_id,
                plan.scope.task_id,
                attempt_id,
                epoch,
                receipt.ordinal,
                disclosure.query_sha256,
                receipt.disclosure_sha256,
                disclosure.model_dump_json(),
                plan.request_id,
                plan.configuration_sha256,
            ),
        )
        append_event(
            uow,
            goal_id=plan.scope.goal_id,
            task_id=plan.scope.task_id,
            actor=actor.owner_id,
            kind="search.outbound.authorized",
            payload={
                "dispatch_id": receipt.dispatch_id,
                "ordinal": receipt.ordinal,
                "disclosure": body,
                "disclosure_sha256": receipt.disclosure_sha256,
                "authorized": "YES",
                "accessible": "YES",
                "observed": "UNKNOWN",
            },
        )
        return receipt

    def finish(
        self,
        uow: UnitOfWork,
        actor: Actor,
        task_id: str,
        dispatch_id: str,
        status: Literal["RETURNED", "UNAVAILABLE", "UNKNOWN"],
        response_sha256: str | None = None,
        candidate_count: int | None = None,
    ) -> None:
        # Historical receipt recording after cancellation cannot restore authority.
        if uow.connection.autocommit and uow.connection.info.transaction_status != TransactionStatus.INTRANS:
            raise KernelDenied("search_caller_transaction_required")
        task = lock_task(uow, actor.owner_id, actor.project_id, task_id)
        if (
            task is None
            or uow.execute(
                "SELECT 1 FROM panestria.search_dispatch WHERE id=%s AND task_id=%s", (dispatch_id, task_id)
            ).fetchone()
            is None
        ):
            raise KernelDenied("not_found")
        values = (status, response_sha256, candidate_count)
        old = uow.execute(
            "SELECT status,response_sha256,candidate_count FROM panestria.search_outcome WHERE dispatch_id=%s",
            (dispatch_id,),
        ).fetchone()
        if old is not None:
            if tuple(None if v is None else str(v).strip() for v in old) != tuple(
                None if v is None else str(v) for v in values
            ):
                raise KernelDenied("search_outcome_conflict")
            return
        uow.execute(
            "INSERT INTO panestria.search_outcome(dispatch_id,status,response_sha256,candidate_count) "
            "VALUES(%s,%s,%s,%s)",
            (dispatch_id, *values),
        )
        append_event(
            uow,
            goal_id=task[0],
            task_id=task_id,
            actor=actor.owner_id,
            kind="search.outbound.finished",
            payload={
                "dispatch_id": dispatch_id,
                "status": status,
                "response_sha256": response_sha256,
                "candidate_count": candidate_count,
                "upstream_observed": "UNKNOWN",
            },
        )
