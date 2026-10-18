"""Canonical collection lifecycle; no acceptance, synthesis or semantic verdict."""

import math
from dataclasses import dataclass
from uuid import uuid4

from psycopg.pq import TransactionStatus

from panestria.contracts.build import canonical_sha256
from panestria.contracts.goal import GoalContract, contract_sha256, load_contract
from panestria.contracts.policy import PolicyRequest
from panestria.contracts.research import ResearchArtifactRef, ResearchLimits, ResearchRequestRecord, ResearchScope
from panestria.contracts.research_admission import CollectionStop as CollectionStop
from panestria.contracts.task import ALLOWED_TRANSITIONS
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.leases import AttemptLease, LeaseService
from panestria.kernel.policy import PolicyService
from panestria.kernel.repositories.policy import lock_project
from panestria.kernel.repositories.tasks import append_event, lock_task
from panestria.kernel.tasks import TaskService
from panestria.kernel.uow import UnitOfWork
from panestria.policy.engine import PolicyEngine
from panestria.policy.research import RESEARCH_PROFILE
from panestria.policy.research_fetch import PublicFetchCertificateStore
from panestria.policy.search import PublicSearchCertificateStore


@dataclass(frozen=True)
class CollectionBinding:
    request: ResearchRequestRecord
    request_sha256: str
    contract: GoalContract
    contract_sha256: str
    task_state: str
    row_version: int
    epoch: int
    goal_status: str


class CollectionLifecycle:
    def __init__(self, search: PublicSearchCertificateStore, fetch: PublicFetchCertificateStore, certificate: str):
        if (
            type(search) is not PublicSearchCertificateStore
            or type(fetch) is not PublicFetchCertificateStore
            or search.runtime_versions != fetch.runtime_versions
            or search.runtime_versions.get("profile") != RESEARCH_PROFILE
        ):
            raise KernelDenied("joint_research_runtime_required")
        self.search, self.fetch, self.certificate = search, fetch, certificate

    def load(self, uow: UnitOfWork, actor: Actor, request_id: str) -> CollectionBinding:
        if uow.connection.autocommit and uow.connection.info.transaction_status != TransactionStatus.INTRANS:
            raise KernelDenied("research_caller_transaction_required")
        lock_project(uow, actor)
        hint = uow.execute(
            "SELECT task_id::text,goal_id::text FROM panestria.research_request "
            "WHERE id=%s AND owner_id=%s AND project_id=%s",
            (request_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if hint is None:
            raise KernelDenied("not_found")
        # Activation updates the goal. Cancellation already locks goal -> task;
        # taking the goal here first prevents the inverse task -> goal wait.
        if (
            uow.execute(
                "SELECT id FROM panestria.goal WHERE id=%s AND owner_id=%s AND project_id=%s FOR NO KEY UPDATE",
                (str(hint[1]), actor.owner_id, actor.project_id),
            ).fetchone()
            is None
        ):
            raise KernelDenied("not_found")
        task = lock_task(uow, actor.owner_id, actor.project_id, str(hint[0]))
        if task is None:
            raise KernelDenied("not_found")
        row = uow.execute(
            "SELECT r.goal_id::text,r.question_artifact_id::text,r.question_sha256,r.question_size_bytes,"
            "r.privacy_class,r.max_sources,r.max_source_bytes,r.max_total_bytes,r.max_redirects,"
            "r.deadline_seconds,r.request_sha256,c.body,c.sha256,g.status,"
            "a.store_key,a.sha256,a.size_bytes,a.privacy_class "
            "FROM panestria.research_request r JOIN panestria.task t ON t.id=r.task_id "
            "JOIN panestria.goal g ON g.id=t.goal_id JOIN panestria.goal_contract c ON c.id=t.contract_id "
            "JOIN panestria.artifact a ON a.id=r.question_artifact_id AND a.task_id=t.id "
            "WHERE r.id=%s AND r.goal_id=g.id AND g.owner_id=%s AND g.project_id=%s",
            (request_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        request = ResearchRequestRecord(
            request_id=request_id,
            scope=ResearchScope(
                owner_id=actor.owner_id, project_id=actor.project_id, goal_id=str(row[0]), task_id=str(hint[0])
            ),
            question=ResearchArtifactRef(
                artifact_id=str(row[1]),
                task_id=str(hint[0]),
                sha256=str(row[2]).strip(),
                size_bytes=row[3],
                privacy_label=row[4],
            ),
            limits=ResearchLimits(
                max_sources=row[5],
                max_source_bytes=row[6],
                max_total_bytes=row[7],
                max_redirects=row[8],
                deadline_seconds=float(row[9]),
            ),
        )
        contract = load_contract(row[11])
        request_hash, contract_hash = str(row[10]).strip(), str(row[12]).strip()
        if (
            canonical_sha256(request.model_dump(mode="json")) != request_hash
            or contract_sha256(contract) != contract_hash
            or (contract.owner_id, contract.project_id, str(contract.goal_id))
            != (actor.owner_id, actor.project_id, request.scope.goal_id)
            or tuple(str(v).strip() for v in row[14:])
            != (
                request.question.sha256,
                request.question.sha256,
                str(request.question.size_bytes),
                request.question.privacy_label,
            )
        ):
            raise KernelDenied("research_collection_binding_invalid")
        return CollectionBinding(
            request, request_hash, contract, contract_hash, task[1], task[2], task[3], str(row[13])
        )

    def eligible(self, uow: UnitOfWork, actor: Actor, binding: CollectionBinding) -> None:
        # Local read only. A certificate profile and a cloud flag independently
        # cannot authorize collection; both complete stores and all policy axes apply.
        policy = PolicyService(self.search).get(uow, actor)
        PolicyService(self.fetch).get(uow, actor)
        c = binding.contract
        if (
            c.privacy_class != "PUBLIC"
            or binding.request.question.privacy_label != "PUBLIC"
            or c.constraints.cloud_egress != "allow"
            or c.budget.max_api_usd != "0"
            or set(c.constraints.permitted_capabilities) - {"read", "public-search", "public-fetch"}
            or not {"public-search", "public-fetch"}.issubset(c.constraints.permitted_capabilities)
            or c.autonomy_profile_ref != f"project-policy:{policy.version}:{policy.sha256()}"
            or c.trust_profile_id != policy.trust.profile
            or policy.trust.runtime_certificate_sha256 != self.certificate
        ):
            raise KernelDenied("research_collection_contract_or_policy_denied")
        decision = PolicyEngine().authorize(
            PolicyRequest(
                owner_id=actor.owner_id,
                project_id=actor.project_id,
                action="external-send",
                label="PUBLIC",
                destination="public-web",
                effect_digest=binding.request_sha256,
            ),
            policy,
        )
        if decision.outcome != "PERMIT":
            raise KernelDenied("research_collection_export_denied")

    def begin(self, uow: UnitOfWork, actor: Actor, binding: CollectionBinding) -> None:
        self.eligible(uow, actor, binding)
        task_id, goal_id = binding.request.scope.task_id, binding.request.scope.goal_id
        if binding.task_state != "CREATED" or binding.goal_status != "CREATED" or binding.epoch != 0:
            raise KernelDenied("research_collection_already_started_inspect_state")
        if uow.execute("SELECT 1 FROM panestria.task_attempt WHERE task_id=%s", (task_id,)).fetchone() is not None:
            raise KernelDenied("research_collection_already_started_inspect_state")
        uow.execute("UPDATE panestria.goal SET status='ACTIVE' WHERE id=%s", (goal_id,))
        TaskService().transition(
            uow,
            actor,
            task_id,
            binding.row_version,
            0,
            "VALIDATING",
            "research_collection_requested",
            policy_version=binding.contract.autonomy_profile_ref,
            correlation_id=str(uuid4()),
        )

    def ready(self, uow: UnitOfWork, actor: Actor, binding: CollectionBinding) -> None:
        self.eligible(uow, actor, binding)
        if binding.task_state != "VALIDATING" or binding.goal_status != "ACTIVE" or binding.epoch != 0:
            raise KernelDenied("research_collection_start_interrupted")
        TaskService().transition(
            uow,
            actor,
            binding.request.scope.task_id,
            binding.row_version,
            0,
            "READY",
            "research_collection_validated",
            policy_version=binding.contract.autonomy_profile_ref,
            correlation_id=str(uuid4()),
        )

    def lease(self, uow: UnitOfWork, actor: Actor, binding: CollectionBinding) -> AttemptLease:
        self.eligible(uow, actor, binding)
        if binding.task_state != "READY" or binding.goal_status != "ACTIVE" or binding.epoch != 0:
            raise KernelDenied("research_collection_start_interrupted")
        ttl = math.ceil(min(binding.request.limits.deadline_seconds, binding.contract.budget.max_wall_seconds))
        return LeaseService().acquire(
            uow,
            actor,
            binding.request.scope.task_id,
            "public-research-collection",
            binding.row_version,
            ttl_seconds=max(1, ttl),
        )

    def finish(
        self,
        uow: UnitOfWork,
        actor: Actor,
        binding: CollectionBinding,
        lease: AttemptLease,
        *,
        reason: CollectionStop,
        known: bool,
    ) -> None:
        current = self.load(uow, actor, binding.request.request_id)
        task_id = current.request.scope.task_id
        attempt = uow.execute(
            "SELECT status,lease_epoch FROM panestria.task_attempt WHERE id=%s AND task_id=%s",
            (lease.attempt_id, task_id),
        ).fetchone()
        if (
            current.request_sha256 != binding.request_sha256
            or current.contract_sha256 != binding.contract_sha256
            or current.epoch != lease.epoch
            or attempt != ("RUNNING", lease.epoch)
        ):
            raise KernelDenied("stale_lease")
        if known:
            LeaseService().require_current(uow, actor, lease.attempt_id, lease.epoch)
            uncertain = uow.execute(
                "SELECT EXISTS(SELECT 1 FROM panestria.search_dispatch d "
                "LEFT JOIN panestria.search_outcome o ON o.dispatch_id=d.id "
                "WHERE d.task_id=%s AND d.request_id=%s AND (o.status IS NULL OR o.status='UNKNOWN')) "
                "OR EXISTS(SELECT 1 FROM panestria.fetch_dispatch d "
                "LEFT JOIN panestria.fetch_outcome o ON o.dispatch_id=d.id "
                "WHERE d.task_id=%s AND d.request_id=%s AND (o.status IS NULL OR o.status='UNKNOWN'))",
                (task_id, binding.request.request_id, task_id, binding.request.request_id),
            ).fetchone()
            if uncertain is None or uncertain[0]:
                raise KernelDenied("research_collection_outcome_unknown")
        # An expired, unreplaced epoch may only be retrospectively fenced LOST;
        # it cannot publish a known success or overwrite cancellation/reclamation.
        task = lock_task(uow, actor.owner_id, actor.project_id, task_id)
        assert task is not None
        target = "VERIFYING" if known else "RECONCILING"
        if task[1] != "RUNNING" or (task[1], target) not in ALLOWED_TRANSITIONS:
            raise KernelDenied("illegal_transition")
        # Completing this adapter is not a PASS of a goal/acceptance check.
        uow.execute(
            "UPDATE panestria.task_attempt SET status=%s,finished_at=clock_timestamp(),error_code=%s WHERE id=%s",
            ("SUCCEEDED" if known else "LOST", None if known else "collection_interrupted", lease.attempt_id),
        )
        uow.execute(
            "UPDATE panestria.task SET state=%s,row_version=row_version+1,lease_epoch=lease_epoch+1,"
            "updated_at=clock_timestamp() WHERE id=%s",
            (target, task_id),
        )
        append_event(
            uow,
            goal_id=task[0],
            task_id=task_id,
            actor=actor.owner_id,
            kind="research.collection.stopped",
            payload={
                "reason": reason,
                "request_id": binding.request.request_id,
                "state": target,
                "semantic_support": "NOT_ASSESSED",
                "attempt_id": lease.attempt_id,
                "lease_epoch": lease.epoch,
            },
        )
