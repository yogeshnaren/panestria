"""One owner-submitted PUBLIC Build, using the canonical kernel and exact merge."""

from __future__ import annotations

import re
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4, uuid5

import psycopg

from panestria.brokers.harness.claude_build import ClaudeScopedBashAdapter
from panestria.brokers.harness.claude_proposal import PINNED_BINARY_SHA256, ClaudeProposalAdapter
from panestria.brokers.harness.cli_profile import BinaryPin
from panestria.config_build import BuildSettings
from panestria.contracts.acceptance import GitDiffPathCheck, PolicyDecision, TrustedCommandRef
from panestria.contracts.goal import GoalContract, contract_sha256, load_contract
from panestria.contracts.native_tools import ToolScope
from panestria.contracts.policy import AutonomyAxis, PrivacyAxis, TrustAxis
from panestria.execution.build_merge import VerifiedGitTarget, prepare_merge
from panestria.execution.native_build import AdmittedNativeBuild, runtime_versions
from panestria.execution.outbox import EffectExecutor
from panestria.execution.proposal_demo import _lock, _private
from panestria.execution.scoped_bash import ScopedBashController
from panestria.kernel.approvals import ApprovalService
from panestria.kernel.build import BuildEvidenceService, BuildEvidenceStore
from panestria.kernel.cancellation import CancellationService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor, GoalService
from panestria.kernel.leases import AttemptLease, LeaseService
from panestria.kernel.local_setup import LocalSetupIntent, LocalSetupService
from panestria.kernel.policy import PolicyService
from panestria.kernel.repositories.policy import current_policy, lock_project
from panestria.kernel.repositories.tasks import append_event
from panestria.kernel.retries import RetryService
from panestria.kernel.uow import UnitOfWork
from panestria.policy.profiles import CertificateStore
from panestria.verification.git_snapshot import materialize, protected_git


class OwnerBuild:
    def __init__(self, settings: BuildSettings, dsn: str) -> None:
        self.settings, self.dsn = settings, dsn
        self.actor = Actor(str(settings.owner_id), str(settings.project_id))
        self.certificates = CertificateStore(settings.certificates, runtime_versions())
        self.reports = BuildEvidenceStore(settings.root / "reports")
        self.registry = settings.registry()

    def connect(self) -> psycopg.Connection[Any]:
        return psycopg.connect(self.dsn, connect_timeout=2, options="-c statement_timeout=2000 -c lock_timeout=1000")

    def prepare_policy(self) -> dict[str, Any]:
        """Prepare a separate administrative review, never apply it implicitly."""
        s = self.settings
        with _lock(s.root / "operation.lock"), self.connect() as c:
            actor, uow = self.actor, UnitOfWork(c)
            if (
                c.execute(
                    "SELECT 1 FROM panestria.project WHERE id=%s AND owner_id=%s", (actor.project_id, actor.owner_id)
                ).fetchone()
                is None
            ):
                LocalSetupService().initialize(
                    uow, LocalSetupIntent(owner_id=s.owner_id, project_id=s.project_id, intent="OFFLINE_ASK")
                )
            old = current_policy(uow, actor)
            lock_project(uow, actor)
            # Goal contracts require UUIDv4; retain a stable administrative key
            # while setting its version bits to that closed schema.
            setup_goal = str(UUID(bytes=uuid5(s.project_id, "native-build-policy-setup").bytes, version=4))
            setup_task = str(UUID(bytes=uuid5(UUID(setup_goal), "policy-review").bytes, version=4))
            document = {
                "schema_version": 1,
                "goal_id": setup_goal,
                "owner_id": actor.owner_id,
                "project_id": actor.project_id,
                "contract_version": 1,
                "intent": "Administrative native Build policy review; no worker dispatch",
                "privacy_class": "PUBLIC",
                "trust_profile_id": old.trust.profile,
                "autonomy_profile_ref": f"project-policy:{old.version}:{old.sha256()}",
                "constraints": {
                    "allowed_paths": ["review"],
                    "forbidden_paths": [".git/**"],
                    "permitted_capabilities": ["read"],
                    "cloud_egress": "deny",
                },
                "budget": {"max_attempts_per_task": 1, "max_wall_seconds": 30, "max_api_usd": "0"},
                "acceptance": [
                    {
                        "id": "review",
                        "description": "Owner policy decision",
                        "required": True,
                        "evidence": {"required": True, "kind": "policy-decision-report"},
                        "verifier": {
                            "type": "policy-decision",
                            "action": "protected-merge",
                            "expected": "approval-required",
                        },
                    }
                ],
                "non_goals": [],
            }
            if c.execute("SELECT 1 FROM panestria.task WHERE id=%s", (setup_task,)).fetchone() is None:
                GoalService().submit(uow, actor, document, "native-build-policy-setup")
                cid = c.execute(
                    "SELECT id::text FROM panestria.goal_contract WHERE goal_id=%s", (setup_goal,)
                ).fetchone()
                assert cid is not None
                c.execute(
                    "INSERT INTO panestria.task(id,goal_id,contract_id,name,state) VALUES(%s,%s,%s,%s,'READY')",
                    (setup_task, setup_goal, cid[0], "Administrative policy review"),
                )
            actions = dict(old.autonomy.actions)
            actions.update(
                {
                    "read": "act-and-report",
                    "edit": "act-and-report",
                    "external-send": "act-and-report",
                    "merge": "approve-first",
                }
            )
            proposed = old.model_copy(
                update={
                    "version": old.version + 1,
                    "trust": TrustAxis(
                        version=old.trust.version + 1,
                        profile="PERSONAL_SANDBOX",
                        allowed_actions=["read", "edit", "external-send", "merge"],
                        runtime_certificate_sha256=s.certificate_sha256,
                    ),
                    "privacy": PrivacyAxis(version=old.privacy.version + 1, cloud_destinations=["claude-subscription"]),
                    "autonomy": AutonomyAxis(version=old.autonomy.version + 1, actions=actions),
                }
            )
            proposed = proposed.model_copy(
                update={
                    axis: getattr(proposed, axis).model_copy(
                        update={
                            "version": getattr(old, axis).version
                            + int(
                                getattr(proposed, axis).model_dump(exclude={"version"})
                                != getattr(old, axis).model_dump(exclude={"version"})
                            )
                        }
                    )
                    for axis in ("trust", "privacy", "autonomy")
                }
            )
            review = PolicyService(self.certificates).propose(uow, actor, setup_task, proposed)
            return {
                **asdict(review),
                "proposed_policy": proposed.model_dump(),
                "proposed_sha256": proposed.sha256(),
                "scope": "PUBLIC native Build only; no private-cloud permission or release acceptance",
            }

    def confirm_policy(self, review_id: str, digest: str) -> dict[str, Any]:
        with _lock(self.settings.root / "operation.lock"), self.connect() as c:
            service, uow = PolicyService(self.certificates), UnitOfWork(c)
            service.decide(uow, self.actor, review_id, digest, "approve")
            policy = service.apply(uow, self.actor, review_id, digest)
            return {"policy_ref": f"project-policy:{policy.version}:{policy.sha256()}", "policy": policy.model_dump()}

    def submit(
        self, document: dict[str, Any], selected: tuple[str, ...], base: str, key: str, *, public_subscription_run: bool
    ) -> dict[str, Any]:
        if public_subscription_run is not True or not 1 <= len(key) <= 128:
            raise KernelDenied("explicit_public_build_intent_required")
        contract = load_contract(document)
        if (
            (contract.owner_id, contract.project_id) != (self.actor.owner_id, self.actor.project_id)
            or contract.privacy_class != "PUBLIC"
            or contract.trust_profile_id != "PERSONAL_SANDBOX"
            or contract.constraints.cloud_egress != "allow"
            or contract.budget.max_api_usd != "0"
            or contract.budget.max_attempts_per_task != 1
            or not 30 <= contract.budget.max_wall_seconds <= 120
            or not re.fullmatch(r"[0-9a-f]{40}", base)
        ):
            raise KernelDenied("owner_build_contract_not_eligible")
        required = [check.verifier for check in contract.acceptance if check.required]
        if (
            any(not isinstance(spec, (TrustedCommandRef, GitDiffPathCheck, PolicyDecision)) for spec in required)
            or {spec.command_ref for spec in required if isinstance(spec, TrustedCommandRef)}
            != {command.ref for command in self.registry.required()}
            or not any(isinstance(spec, GitDiffPathCheck) for spec in required)
            or not any(
                isinstance(spec, PolicyDecision)
                and spec.action == "protected-merge"
                and spec.expected == "approval-required"
                for spec in required
            )
        ):
            raise KernelDenied("owner_build_required_checks_incomplete")
        task = str(UUID(bytes=uuid5(UUID(contract.goal_id), "owner-native-build").bytes, version=4))
        s = self.settings
        with _lock(s.root / "operation.lock"):
            if s.repository.is_symlink() or s.repository.resolve() != s.repository:
                raise KernelDenied("build_repository_scope_mismatch")
            # Read Git before taking database/event-counter locks. The final
            # protected CAS still enforces the owner's exact expected base.
            observed_base = protected_git(s.repository, ("rev-parse", "refs/heads/main")).decode().strip()
            with self.connect() as c:
                policy = PolicyService(self.certificates).get(UnitOfWork(c), self.actor)
                if (
                    contract.autonomy_profile_ref != f"project-policy:{policy.version}:{policy.sha256()}"
                    or contract.trust_profile_id != policy.trust.profile
                ):
                    raise KernelDenied("policy_changed")
                receipt = GoalService().submit(UnitOfWork(c), self.actor, document, key)
                if receipt.replayed:
                    return {"replayed": True, **self.status(contract.goal_id)}
                if observed_base != base:
                    raise KernelDenied("build_base_changed")
                cid = c.execute(
                    "SELECT id::text FROM panestria.goal_contract WHERE goal_id=%s", (contract.goal_id,)
                ).fetchone()
                assert cid is not None
                c.execute(
                    "INSERT INTO panestria.task(id,goal_id,contract_id,name,state) VALUES(%s,%s,%s,%s,'READY')",
                    (task, contract.goal_id, cid[0], "Owner PUBLIC native Build"),
                )
                for check in contract.acceptance:
                    c.execute(
                        "INSERT INTO panestria.acceptance_check"
                        "(id,contract_id,check_key,description,required,verifier_type,verifier_spec)"
                        " VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb)",
                        (
                            str(uuid4()),
                            cid[0],
                            check.id,
                            check.description,
                            check.required,
                            check.verifier.type,
                            check.verifier.model_dump_json(),
                        ),
                    )
                c.execute("UPDATE panestria.goal SET status='ACTIVE' WHERE id=%s", (contract.goal_id,))
            with self.connect() as c:
                lease = LeaseService().acquire(
                    UnitOfWork(c), self.actor, task, "claude-public-bash", 0, ttl_seconds=120
                )
            scope = ToolScope(
                owner_id=s.owner_id,
                project_id=s.project_id,
                task_id=UUID(task),
                attempt_id=UUID(lease.attempt_id),
                lease_epoch=lease.epoch,
                contract_sha256=contract_sha256(contract),
                policy_ref=contract.autonomy_profile_ref,
            )
            parent = _private(s.root / "attempts")
            try:
                return self._run(contract, selected, base, task, lease, scope, parent)
            except (Exception, KeyboardInterrupt):
                try:
                    with self.connect() as c:
                        RetryService().schedule(
                            UnitOfWork(c), self.actor, lease.attempt_id, lease.epoch, "owner_build_stopped", jitter=0
                        )
                except Exception:
                    pass  # Replaced/cancelled/finished attempts cannot overwrite current state.
                raise

    def _run(
        self,
        contract: GoalContract,
        selected: tuple[str, ...],
        base: str,
        task: str,
        lease: AttemptLease,
        scope: ToolScope,
        parent: Path,
    ) -> dict[str, Any]:
        s = self.settings
        snapshot = materialize(s.repository, base, base, parent / (lease.attempt_id + "-source"))
        controller = ScopedBashController(
            self.dsn,
            self.actor,
            scope,
            contract,
            uuid5(UUID(task), "native-session"),
            snapshot,
            parent / lease.attempt_id,
            self.certificates,
            self.reports,
        )
        native = ClaudeScopedBashAdapter(
            ClaudeProposalAdapter(BinaryPin(s.native_binary, PINNED_BINARY_SHA256), s.native_config, s.skills_archive)
        )
        cancel = threading.Event()
        try:
            outcome = AdmittedNativeBuild(controller, selected).run(
                native,
                s.protected,
                s.repository,
                base,
                parent / (lease.attempt_id + "-verified"),
                self.registry,
                cancel=cancel,
            )
        except KeyboardInterrupt:
            cancel.set()
            raise
        return {"status": outcome.status, "reason": outcome.reason, **self.status(contract.goal_id)}

    def status(self, goal: str, *, diff: bool = False) -> dict[str, Any]:
        with self.connect() as c:
            GoalService().get(UnitOfWork(c), self.actor, goal)
            row = c.execute(
                "SELECT id::text,state,row_version FROM panestria.task WHERE goal_id=%s "
                "AND name='Owner PUBLIC native Build'",
                (goal,),
            ).fetchone()
            if row is None:
                raise KernelDenied("not_found")
            task, state, version = row
            approvals = c.execute(
                "SELECT id::text FROM panestria.approval_request WHERE task_id=%s "
                "AND action_kind='merge' ORDER BY expires_at DESC LIMIT 1",
                (task,),
            ).fetchone()
            result: dict[str, Any] = {"goal_id": goal, "task_id": task, "task_state": state, "row_version": version}
            evidence_digest = None
            if approvals:
                view = ApprovalService().preview(UnitOfWork(c), self.actor, approvals[0])
                result["approval"] = vars(view)
                evidence_digest = str(view.preview["candidate_sha256"])
            else:
                artifact = c.execute(
                    "SELECT sha256 FROM panestria.artifact WHERE task_id=%s AND kind='build-evidence'"
                    " ORDER BY created_at DESC LIMIT 1",
                    (task,),
                ).fetchone()
                if artifact is not None:
                    evidence_digest = str(artifact[0]).strip()
            if evidence_digest:
                bundle = self.reports.read(evidence_digest)
                if (bundle.owner_id, bundle.project_id, bundle.task_id) != (
                    self.actor.owner_id,
                    self.actor.project_id,
                    task,
                ):
                    raise KernelDenied("build_evidence_scope_mismatch")
                result["evidence_sha256"] = evidence_digest
                result["base_commit"], result["candidate_commit"] = bundle.base_commit, bundle.candidate_commit
                result["checks"] = [check.model_dump(mode="json") for check in bundle.checks]
                if diff:
                    result["diff"] = protected_git(
                        self.settings.repository,
                        (
                            "diff",
                            "--no-ext-diff",
                            "--no-textconv",
                            "--no-renames",
                            bundle.base_commit,
                            bundle.candidate_commit,
                        ),
                        limit=64 * 1024,
                    ).decode()
            return result

    def cancel(self, goal: str, version: int) -> dict[str, Any]:
        # Do not take operation.lock: revocation must interrupt a running submit.
        with self.connect() as c:
            receipt = CancellationService().cancel(
                UnitOfWork(c), self.actor, goal, version, "owner_requested_cancel", correlation_id=str(uuid4())
            )
            return vars(receipt)

    def approve(self, approval_id: str, digest: str, version: int, key: str) -> dict[str, Any]:
        with _lock(self.settings.root / "operation.lock"):
            with self.connect() as c:
                preview = ApprovalService().preview(UnitOfWork(c), self.actor, approval_id)
                ApprovalService().decide(UnitOfWork(c), self.actor, approval_id, digest, version, "approve", key)
            with self.connect() as c:
                effect = prepare_merge(UnitOfWork(c), self.actor, approval_id)
            evidence = BuildEvidenceService(self.reports)
            target = VerifiedGitTarget(
                self.settings.protected,
                self.settings.repository,
                self.connect,
                self.actor,
                evidence,
                self.registry,
                self.certificates,
            )
            EffectExecutor(self.connect, target).dispatch(self.actor, effect.effect_id)
            task = str(preview.preview["task_id"])
            # The canonical preview pins the exact evidence digest.
            with self.connect() as c:
                evidence.complete_confirmed(
                    UnitOfWork(c), self.actor, task, str(preview.preview["candidate_sha256"]), effect.effect_id
                )
                goal = c.execute("SELECT goal_id::text FROM panestria.task WHERE id=%s", (task,)).fetchone()
                assert goal is not None
                c.execute(
                    "UPDATE panestria.goal SET status='COMPLETED' WHERE id=%s AND NOT EXISTS"
                    "(SELECT 1 FROM panestria.task WHERE goal_id=%s AND state!='COMPLETED')",
                    (goal[0], goal[0]),
                )
                append_event(
                    UnitOfWork(c),
                    goal_id=goal[0],
                    task_id=task,
                    actor=self.actor.owner_id,
                    kind="owner_build.merge_confirmed",
                    payload={"effect_id": effect.effect_id},
                )
            return self.status(goal[0])
