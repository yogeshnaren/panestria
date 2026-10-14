"""Connect protected Git effects to current kernel evidence, policy and certificates."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import psycopg

from panestria.contracts.build import BuildEvidenceBundle
from panestria.contracts.effects import EffectIntent
from panestria.contracts.policy import PolicyRequest
from panestria.execution.protected_merge import MergeSpec, ProtectedGitTarget
from panestria.kernel.approvals import ApprovalService
from panestria.kernel.build import BuildEvidenceService
from panestria.kernel.effects import DispatchClaim, EffectRef, SideEffectService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.policy import PolicyService
from panestria.kernel.repositories.policy import require_current_policy
from panestria.kernel.uow import UnitOfWork
from panestria.policy.engine import PolicyEngine
from panestria.policy.profiles import CertificateStore
from panestria.verification.build import verifier_bundle_digest
from panestria.verification.registry import CommandRegistry


class VerifiedGitTarget(ProtectedGitTarget):
    def __init__(
        self,
        protected_root: Path,
        repository: Path,
        connect: Callable[[], psycopg.Connection[Any]],
        actor: Actor,
        evidence: BuildEvidenceService,
        registry: CommandRegistry,
        certificates: CertificateStore,
    ) -> None:
        self.connect, self.actor, self.evidence, self.registry, self.certificates = (
            connect,
            actor,
            evidence,
            registry,
            certificates,
        )
        expected_repository = protected_root.resolve() / actor.owner_id / actor.project_id / "destination.git"
        if repository.is_symlink() or repository.resolve() != expected_repository:
            raise KernelDenied("merge_repository_scope_mismatch")
        super().__init__(protected_root, repository, self._authorize, self._historical)

    def _spec(self, claim: DispatchClaim, bundle: BuildEvidenceBundle) -> MergeSpec:
        destination, sep, candidate = claim.target.partition("@")
        if sep != "@" or candidate != bundle.candidate_commit:
            raise KernelDenied("merge_target_mismatch")
        return MergeSpec(
            destination, bundle.base_commit, bundle.candidate_commit, bundle.candidate_tree, bundle.sha256()
        )

    def _authorize(self, claim: DispatchClaim) -> MergeSpec:
        with self.connect() as c:
            uow = UnitOfWork(c)
            bundle = self.evidence.authorize_dispatch(uow, self.actor, claim)
            policy = PolicyService(self.certificates).get(uow, self.actor)
            request = PolicyRequest(
                owner_id=self.actor.owner_id,
                project_id=self.actor.project_id,
                action="merge",
                label="RESTRICTED",
                destination="local",
                effect_digest=claim.fingerprint,
            )
            if PolicyEngine().authorize(request, policy).outcome == "DENY":
                raise KernelDenied("policy_denied")
            row = uow.execute("SELECT body FROM panestria.goal_contract WHERE id=%s", (bundle.contract_id,)).fetchone()
            assert row is not None
            from panestria.contracts.goal import load_contract

            contract = load_contract(row[0])
            if (
                contract.trust_profile_id != policy.trust.profile
                or verifier_bundle_digest(contract, self.registry, recheck=True) != bundle.verifier_bundle_sha256
            ):
                raise KernelDenied("verifier_bundle_changed")
            spec = self._spec(claim, bundle)
        # Successful revalidation is the dispatch authorization point. An action
        # already started must be reconciled if cancellation arrives afterwards.
        # Git I/O remains outside the application database transaction.
        return spec

    def _historical(self, claim: DispatchClaim) -> MergeSpec:
        with self.connect() as c:
            return self._spec(claim, self.evidence.historical_effect(UnitOfWork(c), self.actor, claim))


def prepare_merge(uow: UnitOfWork, actor: Actor, approval_id: str) -> EffectRef:
    hint = uow.execute(
        "SELECT policy_version FROM panestria.approval_request WHERE id=%s AND owner_id=%s AND project_id=%s",
        (approval_id, actor.owner_id, actor.project_id),
    ).fetchone()
    if hint is None:
        raise KernelDenied("not_found")
    require_current_policy(uow, actor, str(hint[0]))
    preview = ApprovalService().preview(uow, actor, approval_id)
    body = preview.preview
    if body["action_kind"] != "merge":
        raise KernelDenied("approval_mismatch")
    intent = EffectIntent(
        task_id=str(body["task_id"]),
        effect_key="merge:" + approval_id,
        target=str(body["destination"]),
        request_ref="approval:" + approval_id,
        classification="reconcile-by-query",
        policy_version=str(body["policy_version"]),
        effect_digest=preview.effect_digest,
    )
    # Complete application writes before SideEffectService appends the last
    # event and acquires the global sequence lock. Task serialization makes the
    # existing-effect test stable until this caller commits.
    task = uow.execute("SELECT state FROM panestria.task WHERE id=%s", (intent.task_id,)).fetchone()
    existing = uow.execute(
        "SELECT 1 FROM panestria.side_effect WHERE task_id=%s AND effect_key=%s", (intent.task_id, intent.effect_key)
    ).fetchone()
    if existing is None:
        if task is None or task[0] != "WAITING_APPROVAL":
            raise KernelDenied("illegal_transition")
        uow.execute(
            "UPDATE panestria.task SET state='VERIFYING',row_version=row_version+1 WHERE id=%s", (intent.task_id,)
        )
    return SideEffectService().prepare(uow, actor, intent, approval_id)
