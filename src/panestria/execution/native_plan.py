"""One explicit PUBLIC bounded fork/join run; no provider fallback or merge.

Claims/attempts, tool scopes, independent evidence and completion remain canonical.
This foreground driver never adopts an old claim or replays an uncertain call.
"""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4, uuid5

from panestria.brokers.harness.claude_build import ClaudeScopedBashAdapter
from panestria.brokers.harness.claude_proposal import PINNED_BINARY_SHA256, ClaudeProposalAdapter
from panestria.brokers.harness.cli_profile import BinaryPin
from panestria.contracts.build import canonical_sha256
from panestria.contracts.goal import contract_sha256, load_contract
from panestria.contracts.native_tools import ToolScope
from panestria.contracts.plan import HandoffSubmission, ProjectInventory, StoredPlan, WorkerInventory
from panestria.contracts.policy import PolicyRequest
from panestria.execution.build_plan import BuildIntegrator
from panestria.execution.build_storage import build_storage_admission
from panestria.execution.native_build import AdmittedNativeBuild, NativeBuildOutcome, runtime_versions
from panestria.execution.owner_build import OwnerBuild
from panestria.execution.proposal_demo import _lock, _private
from panestria.execution.scoped_bash import ScopedBashController
from panestria.kernel.build import BuildEvidenceService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.plan_lifecycle import PlanLifecycle
from panestria.kernel.plan_scope import task_plan_scope
from panestria.kernel.plan_store import PlanStore
from panestria.kernel.policy import PolicyService
from panestria.kernel.scheduler import Scheduled, Scheduler
from panestria.kernel.uow import UnitOfWork
from panestria.policy.engine import PolicyEngine
from panestria.resources.hardware import HardwareProbe
from panestria.verification.git_snapshot import materialize, protected_git


@lru_cache(maxsize=1)
def controller_binary_sha256() -> str:
    running = Path("/proc/self/exe")
    if not 0 < running.stat().st_size <= 512 * 1024**2:
        raise KernelDenied("controller_executable_unavailable")
    return hashlib.sha256(running.read_bytes()).hexdigest()


def worker_declarations() -> tuple[WorkerInventory, ...]:
    versions = runtime_versions()
    return tuple(
        WorkerInventory(
            worker_ref=role,
            binary_sha256=binary,
            profile_sha256=canonical_sha256({"role": role, "runtime_versions": versions}),
            capabilities=(capability,),
            maximum_parallel=parallel,
        )
        for role, binary, capability, parallel in (
            ("claude-public-bash", PINNED_BINARY_SHA256, "scoped-bash", 2),
            ("trusted-integrator", controller_binary_sha256(), "trusted-test-runner", 1),
        )
    )


class NativePlanRunner:
    def __init__(
        self, owner: OwnerBuild, *, on_storage_observation: Callable[[dict[str, Any]], None] | None = None
    ) -> None:
        self.on_storage_observation = on_storage_observation
        self.storage_observation: dict[str, Any] | None = None
        self.storage_notice_key: object = None
        self.owner = owner
        self.evidence = BuildEvidenceService(owner.reports)
        self.cancel = threading.Event()

    def _storage_allows_new_work(self) -> bool:
        observation = build_storage_admission(self.owner.settings)
        self.storage_observation = observation
        if observation is None:
            self.storage_notice_key = None
            return True
        key = (
            observation["decision"],
            observation["reason"],
            tuple(w["code"] for w in observation.get("report", {}).get("warnings", ())),
        )
        if self.on_storage_observation is not None and key != self.storage_notice_key:
            try:
                self.on_storage_observation(observation)
            except Exception:
                self.storage_observation = {"decision": "DEFER", "reason": "storage_notification_unconfirmed"}
                return False
            self.storage_notice_key = key
        return bool(observation["decision"] == "ALLOW")

    def inventory(self, base: str) -> ProjectInventory:
        s = self.owner.settings
        if protected_git(s.repository, ("rev-parse", "refs/heads/main")).decode().strip() != base:
            raise KernelDenied("build_base_changed")
        if not self._storage_allows_new_work():
            assert self.storage_observation is not None
            raise KernelDenied(str(self.storage_observation["reason"]))
        parent = _private(s.root / "plan-inventory")
        snapshot = materialize(s.repository, base, base, parent / str(uuid4()))
        return ProjectInventory(
            owner_id=self.owner.actor.owner_id,
            project_id=self.owner.actor.project_id,
            base_commit=base,
            snapshot_sha256=snapshot.manifest_sha256,
            workers=worker_declarations(),
            maximum_nodes=3,
            maximum_depth=2,
        )

    def _preflight(self, plan_id: str) -> StoredPlan:
        owner = self.owner
        with owner.connect() as c:
            uow = UnitOfWork(c)
            plan = PlanStore().get(uow, owner.actor, plan_id)
            if plan.state != "ACCEPTED":
                raise KernelDenied("plan_not_accepted")
            scope = task_plan_scope(uow, owner.actor, plan.proposal.nodes[0].task_id)
            assert scope is not None
            policy = PolicyService(owner.certificates).get(uow, owner.actor)
            document = c.execute(
                "SELECT body FROM panestria.goal_contract WHERE goal_id=%s ORDER BY version DESC LIMIT 1",
                (plan.proposal.goal_id,),
            ).fetchone()
            assert document is not None
            contract = load_contract(document[0])
            if (
                plan.state != "ACCEPTED"
                or contract.privacy_class != "PUBLIC"
                or contract.constraints.cloud_egress != "allow"
                or contract.budget.max_api_usd != "0"
                or policy.trust.profile != "PERSONAL_SANDBOX"
                or owner.certificates.runtime_versions != runtime_versions()
            ):
                raise KernelDenied("public_native_plan_not_eligible")
            decision = PolicyEngine().authorize(
                PolicyRequest(
                    owner_id=owner.actor.owner_id,
                    project_id=owner.actor.project_id,
                    action="external-send",
                    label="PUBLIC",
                    destination="claude-subscription",
                    effect_digest=plan.proposal.sha256(),
                ),
                policy,
            )
            if decision.outcome != "PERMIT":
                raise KernelDenied("native_plan_disclosure_not_permitted")
        expected = {w.worker_ref: w for w in worker_declarations()}
        if set(w.worker_ref for w in plan.inventory.workers) != set(expected):
            raise KernelDenied("native_plan_worker_unavailable")
        for declared in plan.inventory.workers:
            supported = expected[declared.worker_ref]
            if (
                declared.model_dump(exclude={"maximum_parallel"}) != supported.model_dump(exclude={"maximum_parallel"})
                or declared.maximum_parallel > supported.maximum_parallel
            ):
                raise KernelDenied("native_plan_inventory_changed")
        final = next(n for n in plan.proposal.nodes if n.task_id == scope.integration_task_id)
        workers = [n for n in plan.proposal.nodes if n.task_id != final.task_id]
        if (
            not 1 <= len(workers) <= 2
            or any(n.depends_on or n.worker_ref != "claude-public-bash" for n in workers)
            or final.worker_ref != "trusted-integrator"
            or set(final.depends_on) != {n.task_id for n in workers}
            or any(not 30 <= n.wall_seconds_per_attempt <= 120 for n in plan.proposal.nodes)
        ):
            raise KernelDenied("supported_bounded_fork_join_required")
        s = owner.settings
        if protected_git(s.repository, ("rev-parse", "refs/heads/main")).decode().strip() != plan.inventory.base_commit:
            raise KernelDenied("build_base_changed")
        # Official redacted metadata verifies the expected binary/private profile
        # before capacity is reserved. It is not inference or quota precision.
        ClaudeProposalAdapter(
            BinaryPin(s.native_binary, PINNED_BINARY_SHA256), s.native_config, s.skills_archive
        ).inspect()
        return plan

    def _one(self, plan: StoredPlan, job: Scheduled) -> NativeBuildOutcome:
        owner, s = self.owner, self.owner.settings
        node = next(n for n in plan.proposal.nodes if n.task_id == job.lease.task_id)
        with owner.connect() as c:
            row = c.execute(
                "SELECT c.body FROM panestria.task t JOIN panestria.goal_contract c ON c.id=t.contract_id "
                "WHERE t.id=%s",
                (node.task_id,),
            ).fetchone()
            assert row is not None
            contract = load_contract(row[0])
        scope = ToolScope(
            owner_id=s.owner_id,
            project_id=s.project_id,
            task_id=UUID(node.task_id),
            attempt_id=UUID(job.lease.attempt_id),
            lease_epoch=job.lease.epoch,
            contract_sha256=contract_sha256(contract),
            policy_ref=contract.autonomy_profile_ref,
        )
        parent = _private(s.root / "plan-attempts")
        source = materialize(
            s.repository,
            plan.inventory.base_commit,
            plan.inventory.base_commit,
            parent / (job.lease.attempt_id + "-source"),
        )
        if source.manifest_sha256 != plan.inventory.snapshot_sha256:
            raise KernelDenied("native_plan_base_snapshot_changed")
        controller = ScopedBashController(
            owner.dsn,
            owner.actor,
            scope,
            contract,
            uuid5(UUID(job.lease.attempt_id), "native-plan-session"),
            source,
            parent / job.lease.attempt_id,
            owner.certificates,
            owner.reports,
        )
        selected = tuple(path for path in node.paths if path in {entry[0] for entry in source.files})
        adapter = ClaudeScopedBashAdapter(
            ClaudeProposalAdapter(BinaryPin(s.native_binary, PINNED_BINARY_SHA256), s.native_config, s.skills_archive)
        )
        outcome = AdmittedNativeBuild(controller, selected).run(
            adapter,
            s.protected,
            s.repository,
            plan.inventory.base_commit,
            parent / (job.lease.attempt_id + "-verified"),
            owner.registry,
            cancel=self.cancel,
        )
        if outcome.status == "NODE_VERIFIED" and outcome.review is not None:
            with owner.connect() as c:
                version = c.execute("SELECT row_version FROM panestria.task WHERE id=%s", (node.task_id,)).fetchone()
                assert version is not None
                handoff = PlanStore().handoff(
                    UnitOfWork(c),
                    owner.actor,
                    HandoffSubmission(
                        handoff_id=str(uuid4()),
                        plan_id=plan.proposal.plan_id,
                        task_id=node.task_id,
                        expected_task_version=version[0],
                        evidence_sha256=outcome.review.evidence_sha256,
                    ),
                    self.evidence,
                )
            with owner.connect() as c:
                Scheduler().complete_node(
                    UnitOfWork(c), owner.actor, plan.proposal.plan_id, handoff.submission.handoff_id, self.evidence
                )
        return outcome

    def _summary(self, plan: StoredPlan) -> list[dict[str, object]]:
        with self.owner.connect() as c:
            rows = c.execute(
                "SELECT t.id::text,t.state,t.lease_epoch FROM panestria.task t "
                "JOIN panestria.build_plan_task p ON p.task_id=t.id WHERE p.plan_id=%s ORDER BY t.id",
                (plan.proposal.plan_id,),
            ).fetchall()
        return [{"task_id": identity, "task_state": state, "lease_epoch": epoch} for identity, state, epoch in rows]

    def run(self, plan_id: str, *, public_subscription_run: bool) -> dict[str, object]:
        if public_subscription_run is not True:
            raise KernelDenied("explicit_public_build_intent_required")
        owner = self.owner
        results: list[dict[str, str]] = []
        with _lock(owner.settings.root / "operation.lock"):
            plan = self._preflight(plan_id)
            probe = HardwareProbe(owner.settings.skills_archive)
            active: dict[Future[NativeBuildOutcome], Scheduled] = {}
            stop_new, storage_deferred = False, False
            with ThreadPoolExecutor(max_workers=2, thread_name_prefix="panestria-native-plan") as pool:
                try:
                    while True:
                        while len(active) < 2 and not stop_new and not self.cancel.is_set():
                            if not self._storage_allows_new_work():
                                stop_new, storage_deferred = True, True
                                break
                            capacity = probe.collect_cpu()
                            with owner.connect() as c:
                                job = Scheduler().claim_ready(
                                    UnitOfWork(c), owner.actor, plan_id, capacity, self.evidence
                                )
                            if not isinstance(job, Scheduled):
                                break
                            node = next(n for n in plan.proposal.nodes if n.task_id == job.lease.task_id)
                            if node.worker_ref == "trusted-integrator":
                                parent = _private(owner.settings.root / "plan-integration")
                                outcome = BuildIntegrator(
                                    owner.connect, owner.actor, self.evidence, owner.certificates
                                ).verify_for_review(
                                    plan_id,
                                    job.lease.attempt_id,
                                    job.lease.epoch,
                                    owner.settings.protected,
                                    owner.settings.repository,
                                    parent / str(uuid4()),
                                    owner.registry,
                                )
                                return {
                                    "status": outcome.status,
                                    "plan_id": plan_id,
                                    "report_sha256": outcome.report_sha256,
                                    "worker_observations": results,
                                    "tasks": self._summary(plan),
                                    "goal_id": plan.proposal.goal_id,
                                    "storage_admission": self.storage_observation,
                                }
                            active[pool.submit(self._one, plan, job)] = job
                        if not active:
                            return {
                                "status": "STOPPED"
                                if stop_new
                                and (not storage_deferred or any(r["status"] != "NODE_VERIFIED" for r in results))
                                else "WAIT",
                                "plan_id": plan_id,
                                "worker_observations": results,
                                "tasks": self._summary(plan),
                                "goal_id": plan.proposal.goal_id,
                                "reason": "storage_admission_deferred"
                                if storage_deferred
                                else "inspect_canonical_queue_and_claims",
                                "storage_admission": self.storage_observation,
                            }
                        finished, _ = wait(active, timeout=0.2, return_when=FIRST_COMPLETED)
                        for future in finished:
                            job = active.pop(future)
                            try:
                                result = future.result()
                                results.append(
                                    {"task_id": job.lease.task_id, "status": result.status, "reason": result.reason}
                                )
                                stop_new |= result.status != "NODE_VERIFIED"
                            except Exception:
                                # A claimed slot is deliberately retained until
                                # a real outcome/reconciliation proves release safe.
                                results.append({"task_id": job.lease.task_id, "status": "UNCONFIRMED"})
                                stop_new = True
                except BaseException:
                    self.cancel.set()
                    with owner.connect() as c:
                        PlanLifecycle().cancel(UnitOfWork(c), owner.actor, plan_id, plan.proposal.sha256())
                    raise
