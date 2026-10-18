"""Shared canonical PUBLIC research checks; trusted callers separately pin capability/store types."""

from typing import Literal

from psycopg.pq import TransactionStatus

from panestria.contracts.acceptance import ContractRejected
from panestria.contracts.build import canonical_sha256
from panestria.contracts.goal import contract_sha256, load_contract
from panestria.contracts.policy import PolicyRequest
from panestria.contracts.research_admission import ResearchAuthorityBinding
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.leases import LeaseService
from panestria.kernel.policy import PolicyService
from panestria.kernel.repositories.policy import lock_project
from panestria.kernel.uow import UnitOfWork
from panestria.policy.engine import PolicyEngine
from panestria.policy.profiles import CertificateStore


def require_public_research(
    uow: UnitOfWork,
    actor: Actor,
    plan: ResearchAuthorityBinding,
    attempt_id: str,
    epoch: int,
    certificates: CertificateStore,
    capability: Literal["public-search", "public-fetch"],
) -> float:
    c = uow.connection
    if c.autocommit and c.info.transaction_status != TransactionStatus.INTRANS:
        raise KernelDenied("search_caller_transaction_required")
    s = plan.scope
    if (s.owner_id, s.project_id) != (actor.owner_id, actor.project_id):
        raise KernelDenied("not_found")
    lock_project(uow, actor)  # Project -> task/attempt -> audit -> event last.
    if LeaseService().require_current(uow, actor, attempt_id, epoch) != s.task_id:
        raise KernelDenied("search_scope_mismatch")
    row = uow.execute(
        "SELECT c.body,c.sha256,g.status,r.request_sha256,r.privacy_class,r.deadline_seconds,"
        " extract(epoch FROM clock_timestamp()-(SELECT min(started_at) FROM panestria.task_attempt "
        " WHERE task_id=t.id))::float FROM panestria.task t "
        "JOIN panestria.goal g ON g.id=t.goal_id JOIN panestria.goal_contract c ON c.id=t.contract_id "
        "JOIN panestria.research_request r ON r.task_id=t.id AND r.goal_id=g.id "
        "WHERE t.id=%s AND g.id=%s AND r.id=%s",
        (s.task_id, s.goal_id, plan.request_id),
    ).fetchone()
    if row is None or row[2] != "ACTIVE":
        raise KernelDenied("search_request_inactive")
    try:
        contract = load_contract(row[0])
    except ContractRejected:
        raise KernelDenied("search_contract_invalid") from None
    policy = PolicyService(certificates).get(uow, actor)
    if (
        str(row[1]).strip() != plan.contract_sha256
        or contract_sha256(contract) != plan.contract_sha256
        or (contract.owner_id, contract.project_id, contract.goal_id) != (s.owner_id, s.project_id, s.goal_id)
        or str(row[3]).strip() != plan.request_sha256
        or row[4] != "PUBLIC"
        or contract.privacy_class != "PUBLIC"
        or contract.constraints.cloud_egress != "allow"
        or capability not in contract.constraints.permitted_capabilities
        or contract.budget.max_api_usd != "0"
        or policy.sha256() != plan.policy_sha256
        or contract.autonomy_profile_ref != f"project-policy:{policy.version}:{policy.sha256()}"
        or contract.trust_profile_id != policy.trust.profile
        or certificates.runtime_versions.get("configuration_sha256") != plan.configuration_sha256
    ):
        raise KernelDenied("search_contract_or_policy_mismatch")
    decision = PolicyEngine().authorize(
        PolicyRequest(
            owner_id=actor.owner_id,
            project_id=actor.project_id,
            action="external-send",
            label="PUBLIC",
            destination="public-web",
            effect_digest=canonical_sha256(plan.model_dump()),
        ),
        policy,
    )
    if decision.outcome != "PERMIT":
        raise KernelDenied("public_search_export_denied")
    remaining = min(contract.budget.max_wall_seconds, float(row[5])) - float(row[6])
    if remaining <= 0:
        raise KernelDenied("search_deadline")
    return remaining
