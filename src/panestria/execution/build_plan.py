"""Collect current completed nodes, integrate safely and verify the exact final tree.

No model launch, protected-ref update, conflict auto-resolution or goal completion.
Filesystem/Git/independent checks run outside caller-owned DB transactions; current
policy, accepted plan, handoffs and fenced final attempt are rechecked afterwards.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg

from panestria.contracts.acceptance import TrustedCommandRef
from panestria.contracts.build import canonical_sha256
from panestria.contracts.goal import load_contract
from panestria.contracts.invocation import InvocationBinding
from panestria.contracts.native_tools import ToolScope
from panestria.execution.scoped_bash import BuildReview
from panestria.execution.worker_authority import WorkerAuthority
from panestria.kernel.build import BuildEvidenceService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.invocations import InvocationService
from panestria.kernel.leases import LeaseService
from panestria.kernel.plan_scope import task_plan_scope
from panestria.kernel.plan_store import PlanStore
from panestria.kernel.policy import PolicyService
from panestria.kernel.repositories.tasks import append_event
from panestria.kernel.scheduler import Scheduler
from panestria.kernel.uow import UnitOfWork
from panestria.policy.profiles import CertificateStore
from panestria.verification.build import VerifiedBuild, verifier_bundle_digest, verify_build
from panestria.verification.git_snapshot import materialize
from panestria.verification.merge import integrate
from panestria.verification.registry import CommandRegistry


@dataclass(frozen=True)
class IntegrationOutcome:
    status: str
    report_sha256: str
    review: BuildReview | None = None


class BuildIntegrator:
    def __init__(
        self,
        connect: Callable[[], psycopg.Connection[Any]],
        actor: Actor,
        evidence: BuildEvidenceService,
        certificates: CertificateStore,
        *,
        authority: WorkerAuthority | None = None,
    ) -> None:
        self.connect, self.actor, self.evidence, self.certificates = connect, actor, evidence, certificates
        self.authority = authority

    def _authorize(self) -> None:
        if self.authority is not None:
            with self.connect() as connection:
                self.authority.authorize(connection)

    def _inputs(self, uow: UnitOfWork, plan_id: str, attempt_id: str, epoch: int) -> dict[str, Any]:
        plan = Scheduler()._plan(uow, self.actor, plan_id)
        task = LeaseService().require_current(uow, self.actor, attempt_id, epoch)
        scope = task_plan_scope(uow, self.actor, task)
        if scope is None or not scope.integration or scope.plan_id != plan_id:
            raise KernelDenied("integration_final_task_required")
        claim = uow.execute(
            "SELECT 1 FROM panestria.build_active_worker_claim WHERE plan_id=%s AND task_id=%s AND attempt_id=%s "
            "AND lease_epoch=%s AND released_at IS NULL",
            (plan_id, task, attempt_id, epoch),
        ).fetchone()
        if claim is None:
            raise KernelDenied("integration_claim_missing")
        if self.authority is not None:
            self.authority.authorize(uow.connection)
        policy = PolicyService(self.certificates).get(uow, self.actor)
        handoffs = []
        for node in plan.proposal.nodes:
            if node.task_id == task:
                continue
            row = uow.execute(
                "SELECT c.handoff_id::text FROM panestria.build_worker_claim c "
                "JOIN panestria.task t ON t.id=c.task_id AND t.lease_epoch=c.lease_epoch "
                "WHERE c.plan_id=%s AND c.task_id=%s AND c.released_at IS NOT NULL AND t.state='COMPLETED'",
                (plan_id, node.task_id),
            ).fetchone()
            if row is None:
                raise KernelDenied("integration_dependency_not_verified")
            handoffs.append(PlanStore().read_handoff(uow, self.actor, row[0], self.evidence))
        record = uow.execute(
            "SELECT c.id::text,c.body FROM panestria.goal_contract c "
            "JOIN panestria.task t ON t.contract_id=c.id WHERE t.id=%s",
            (task,),
        ).fetchone()
        assert record is not None
        checks = dict(
            uow.execute(
                "SELECT check_key,id::text FROM panestria.acceptance_check WHERE contract_id=%s", (record[0],)
            ).fetchall()
        )
        remaining = uow.execute(
            "SELECT extract(epoch FROM lease_expires_at-clock_timestamp())::float "
            "FROM panestria.task_attempt WHERE id=%s",
            (attempt_id,),
        ).fetchone()
        if remaining is None or remaining[0] is None or remaining[0] <= 0:
            raise KernelDenied("integration_deadline")
        return {
            "remaining_seconds": remaining[0],
            "plan": plan,
            "scope": scope,
            "handoffs": tuple(handoffs),
            "policy": policy,
            "contract_id": record[0],
            "contract": load_contract(record[1]),
            "checks": checks,
        }

    @staticmethod
    def _fingerprint(inputs: dict[str, Any]) -> str:
        return canonical_sha256(
            {
                "plan": inputs["plan"].proposal.sha256(),
                "scope": inputs["scope"].sha256(),
                "handoffs": [h.sha256() for h in inputs["handoffs"]],
                "policy": inputs["policy"].sha256(),
                "checks": inputs["checks"],
            }
        )

    def verify_for_review(
        self,
        plan_id: str,
        attempt_id: str,
        epoch: int,
        protected_root: Path,
        repository: Path,
        staging: Path,
        registry: CommandRegistry,
    ) -> IntegrationOutcome:
        expected = protected_root / self.actor.owner_id / self.actor.project_id / "destination.git"
        if (
            not protected_root.is_absolute()
            or protected_root.resolve() != protected_root
            or repository != expected
            or repository.resolve() != repository
            or not staging.is_absolute()
            or staging.resolve() != staging
            or staging.exists()
            or not staging.parent.is_dir()
            or staging.parent.stat().st_uid != os.getuid()
            or staging.parent.stat().st_mode & 0o077
            or staging.is_relative_to(protected_root)
            or protected_root.is_relative_to(staging)
        ):
            raise KernelDenied("integration_private_scope_required")
        # This acknowledged invocation covers trusted Git assembly and independent
        # verification. Cancellation must not mistake active checks for no dispatch.
        with self.connect() as c:
            inputs = self._inputs(UnitOfWork(c), plan_id, attempt_id, epoch)
            scope = inputs["scope"]
            binding = InvocationBinding(
                scope=ToolScope(
                    owner_id=UUID(self.actor.owner_id),
                    project_id=UUID(self.actor.project_id),
                    task_id=UUID(scope.node.task_id),
                    attempt_id=UUID(attempt_id),
                    lease_epoch=epoch,
                    contract_sha256=inputs["plan"].proposal.contract_sha256,
                    policy_ref=inputs["contract"].autonomy_profile_ref,
                ),
                kind="build-integration",
                request_sha256=self._fingerprint(inputs),
                configuration_sha256=(
                    canonical_sha256(
                        {
                            "verifier_bundle_sha256": verifier_bundle_digest(inputs["contract"], registry),
                            "additional_authority_sha256": self.authority.binding_sha256,
                        }
                    )
                    if self.authority is not None
                    else verifier_bundle_digest(inputs["contract"], registry)
                ),
            )
            identity = InvocationService().prepare(
                UnitOfWork(c),
                self.actor,
                binding,
                "build-integration:" + attempt_id,
                ttl_seconds=min(900, scope.node.wall_seconds_per_attempt + 5),
            )
        with self.connect() as c:
            self._inputs(UnitOfWork(c), plan_id, attempt_id, epoch)
            InvocationService().claim(UnitOfWork(c), self.actor, binding, identity)
        finished = False

        def returned(report: str, checked: VerifiedBuild | None = None) -> bool:
            nonlocal finished
            safe = True
            if checked is not None:
                command_keys = {
                    check.id for check in inputs["contract"].acceptance if isinstance(check.verifier, TrustedCommandRef)
                }
                # These reasons come only after an actual stopped-and-cleaned
                # runner receipt, or the trusted prelaunch deadline check. All
                # unrecognized/uncertain cleanup failures retain UNKNOWN capacity.
                safe = all(
                    json.loads(raw)["reason"]
                    in {
                        "ok",
                        "process_failed",
                        "deadline_exceeded",
                        "memory_limit",
                        "output_limit",
                        "deadline",
                        "unregistered_command",
                        "unreviewed_executable_or_args",
                        "unreviewed_path",
                        "bundle_tampered",
                    }
                    for raw in checked.reports
                    if json.loads(raw)["check_key"] in command_keys
                )
            receipt = self.evidence.store.write_report(
                json.dumps(
                    {
                        "kind": "build-integration-return",
                        "binding_sha256": binding.sha256(),
                        "integration_report_sha256": report,
                        "verifier_report_sha256": []
                        if checked is None
                        else [canonical_sha256(json.loads(raw)) for raw in checked.reports],
                        "physical_return": "CONFIRMED" if safe else "UNCONFIRMED",
                        "scope_sha256": binding.scope.sha256(),
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            )
            with self.connect() as c:
                InvocationService().finish(UnitOfWork(c), self.actor, binding, identity, receipt if safe else None)
            finished = True  # Historical return may be acknowledged after cancellation.
            return safe

        try:
            return self._verify(plan_id, attempt_id, epoch, protected_root, repository, staging, registry, returned)
        except BaseException:
            if not finished:
                try:
                    with self.connect() as c:
                        InvocationService().finish(UnitOfWork(c), self.actor, binding, identity, None)
                except Exception:
                    pass  # Never turn an uncertain/lost reply into retry permission.
            raise

    def _verify(
        self,
        plan_id: str,
        attempt_id: str,
        epoch: int,
        protected_root: Path,
        repository: Path,
        staging: Path,
        registry: CommandRegistry,
        returned: Callable[[str, VerifiedBuild | None], bool],
    ) -> IntegrationOutcome:
        with self.connect() as c:
            inputs = self._inputs(UnitOfWork(c), plan_id, attempt_id, epoch)
        plan, scope = inputs["plan"], inputs["scope"]
        fingerprint = self._fingerprint(inputs)
        deadline = time.monotonic() + min(120, scope.node.wall_seconds_per_attempt, inputs["remaining_seconds"])
        staging.mkdir(mode=0o700)
        base = plan.inventory.base_commit
        base_snapshot = materialize(repository, base, base, staging / "base", deadline=deadline)
        if base_snapshot.manifest_sha256 != plan.inventory.snapshot_sha256:
            raise KernelDenied("integration_inventory_changed")
        workers = []
        nodes = {n.task_id: n for n in plan.proposal.nodes}
        for handoff in inputs["handoffs"]:
            self._authorize()
            task = handoff.submission.task_id
            snapshot = materialize(repository, base, handoff.candidate_commit, staging / task, deadline=deadline)
            if (
                snapshot.tree != handoff.candidate_tree
                or snapshot.manifest_sha256 != handoff.snapshot_sha256
                or set(snapshot.changed_paths) - set(nodes[task].paths)
            ):
                raise KernelDenied("integration_handoff_tree_changed")
            workers.append((task, snapshot))
        self._authorize()
        combined = integrate(repository, base, base_snapshot, tuple(workers), staging / "combined", deadline=deadline)
        report = {
            "kind": "plan-integrated-candidate",
            "execution_mode": "CONTROLLER_INTEGRATION",
            "worker_inference": "NOT_RUN",
            "plan_id": plan_id,
            "inputs_sha256": fingerprint,
            "attempt_id": attempt_id,
            "lease_epoch": epoch,
            "base_commit": base,
            "handoff_sha256": [h.sha256() for h in inputs["handoffs"]],
            "candidate_commit": combined.candidate,
            "conflicts": [asdict(c) for c in combined.conflicts],
            "conflict_authority": "OWNER_REVIEW_REQUIRED",
            "protected_ref_changed": False,
        }
        digest = self.evidence.store.write_report(json.dumps(report, sort_keys=True, separators=(",", ":")).encode())
        if combined.conflicts:
            returned(digest, None)  # No verifier was launched; trusted Git calls have returned.
            # Retain the exact blocked outcome canonically, without a candidate,
            # verifier PASS, merge approval or protected-ref update.
            with self.connect() as c:
                current = self._inputs(UnitOfWork(c), plan_id, attempt_id, epoch)
                if self._fingerprint(current) != fingerprint:
                    raise KernelDenied("integration_inputs_changed")
                c.execute(
                    "UPDATE panestria.task SET state='RECONCILING',row_version=row_version+1 WHERE id=%s",
                    (scope.node.task_id,),
                )
                append_event(
                    UnitOfWork(c),
                    goal_id=plan.proposal.goal_id,
                    task_id=scope.node.task_id,
                    actor=self.actor.owner_id,
                    kind="build.plan.integration_conflict",
                    payload={
                        "plan_id": plan_id,
                        "inputs_sha256": fingerprint,
                        "report_sha256": digest,
                        "resolution": "OWNER_REVIEW_REQUIRED",
                    },
                )
            return IntegrationOutcome("CONFLICT", digest)
        assert combined.candidate is not None
        if time.monotonic() >= deadline:
            raise KernelDenied("integration_deadline")
        self._authorize()
        final = materialize(repository, base, combined.candidate, staging / "final", deadline=deadline)
        verified = verify_build(
            inputs["contract"],
            inputs["contract_id"],
            scope.node.task_id,
            attempt_id,
            epoch,
            base,
            combined.candidate,
            final,
            inputs["checks"],
            registry,
            policy=inputs["policy"],
            deadline=deadline,
            plan_scope=scope,
            before_check=self._authorize if self.authority is not None else None,
        )
        for raw in verified.reports:
            self.evidence.store.write_report(raw)
        if not returned(digest, verified):
            with self.connect() as c:
                self._inputs(UnitOfWork(c), plan_id, attempt_id, epoch)
                c.execute(
                    "UPDATE panestria.task SET state='RECONCILING',row_version=row_version+1 WHERE id=%s",
                    (scope.node.task_id,),
                )
                append_event(
                    UnitOfWork(c),
                    goal_id=plan.proposal.goal_id,
                    task_id=scope.node.task_id,
                    actor=self.actor.owner_id,
                    kind="build.plan.integration_unconfirmed",
                    payload={"plan_id": plan_id, "report_sha256": digest, "reason": "verification_cleanup_unconfirmed"},
                )
            return IntegrationOutcome("RECONCILING", digest)
        if time.monotonic() >= deadline:
            raise KernelDenied("integration_deadline")
        with self.connect() as c:
            current = self._inputs(UnitOfWork(c), plan_id, attempt_id, epoch)
            if self._fingerprint(current) != fingerprint:
                raise KernelDenied("integration_inputs_changed")
            evidence_sha = self.evidence.publish(UnitOfWork(c), self.actor, verified.bundle)
        approval = None
        if verified.bundle.passed():
            with self.connect() as c:
                if self.authority is not None:
                    self.authority.authorize(c)
                approval = self.evidence.request_merge(
                    UnitOfWork(c), self.actor, scope.node.task_id, evidence_sha, "refs/heads/main"
                )
        return IntegrationOutcome(
            "WAITING_APPROVAL" if approval else "FAILED",
            digest,
            BuildReview(combined.candidate, evidence_sha, verified.bundle.passed(), approval),
        )
