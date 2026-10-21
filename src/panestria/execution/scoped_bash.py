"""One durable Bash job in a disposable workspace, separate from verification.

This local controller grants no cloud export permission. A trusted native launch
must authorize its context independently. Tool receipts expose metadata only.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

import psycopg

from panestria.brokers.harness.bash_protocol import ScopedBashSession
from panestria.contracts.goal import GoalContract, contract_sha256, load_contract
from panestria.contracts.native_build import bash_script
from panestria.contracts.native_command import RegisteredCheckReceipt
from panestria.contracts.native_tools import ToolRequest, ToolScope
from panestria.contracts.policy import PolicyRequest
from panestria.execution.tool_authority import DurableToolAuthority, tool_binding
from panestria.kernel.approvals import ApprovalView
from panestria.kernel.build import BuildEvidenceService, BuildEvidenceStore
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.invocations import InvocationService
from panestria.kernel.leases import LeaseService
from panestria.kernel.plan_scope import task_plan_scope
from panestria.kernel.policy import PolicyService
from panestria.kernel.repositories.policy import require_current_policy
from panestria.kernel.uow import UnitOfWork
from panestria.policy.engine import PolicyEngine
from panestria.policy.profiles import CertificateStore
from panestria.sandbox.native_tool_gateway import NativeCommandRegistry, NativeToolGateway, ReviewedCommand, ToolPermit
from panestria.sandbox.profiles import SandboxProfile
from panestria.verification.build import verify_build
from panestria.verification.candidate import capture_candidate
from panestria.verification.git_snapshot import GitSnapshot, materialize, protected_git, verify_snapshot
from panestria.verification.registry import CommandRegistry


class ScopedBashUnavailable(ValueError):
    pass


@dataclass(frozen=True)
class BuildReview:
    candidate_commit: str
    evidence_sha256: str
    passed: bool
    approval: ApprovalView | None


class _EditAuthority(DurableToolAuthority):
    def __init__(self, controller: ScopedBashController, identity: str) -> None:
        super().__init__(controller.connect, controller.actor, identity)
        self.controller, self.claimed = controller, False

    def claim(self, permit: ToolPermit) -> None:
        with self.connect() as connection:
            self.controller.authorize(connection)
            self.service.claim(UnitOfWork(connection), self.actor, tool_binding(permit), self.identity)
        self.claimed = True

    def check(self, permit: ToolPermit) -> None:
        with self.connect() as connection:
            self.controller.authorize(connection)
            self.service.check(UnitOfWork(connection), self.actor, tool_binding(permit), self.identity)

    def observe(self, permit: ToolPermit) -> None:
        with self.connect() as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            self.controller.authorize(connection, observation=True)
            self.service.observe(UnitOfWork(connection), self.actor, tool_binding(permit), self.identity)

    def _authorize_launch(self, connection: psycopg.Connection[Any], permit: ToolPermit) -> None:
        self.controller.authorize(connection)
        super()._authorize_launch(connection, permit)


class ScopedBashController:
    def __init__(
        self,
        dsn: str,
        actor: Actor,
        scope: ToolScope,
        contract: GoalContract,
        session_id: UUID,
        snapshot: GitSnapshot,
        workspace: Path,
        certificates: CertificateStore,
        reports: BuildEvidenceStore,
    ) -> None:
        try:
            self.scope = ToolScope.model_validate_json(scope.model_dump_json())
            self.contract = load_contract(contract.model_dump(mode="json"))
            if (
                type(session_id) is not UUID
                or (str(scope.owner_id), str(scope.project_id)) != (actor.owner_id, actor.project_id)
                or (contract.owner_id, contract.project_id) != (actor.owner_id, actor.project_id)
                or contract_sha256(self.contract) != scope.contract_sha256
                or self.contract.autonomy_profile_ref != scope.policy_ref
                or "scoped-bash" not in self.contract.constraints.permitted_capabilities
                or not workspace.is_absolute()
                or workspace.resolve() != workspace
                or not workspace.parent.is_dir()
                or workspace.parent.stat().st_uid != os.getuid()
                or workspace.parent.stat().st_mode & 0o077
                or workspace.is_relative_to(snapshot.directory)
                or snapshot.directory.is_relative_to(workspace)
            ):
                raise ValueError
            verify_snapshot(snapshot)
            # No checkout, .git, hooks, credential mounts or model-owned command
            # registry. Only protected, already sanitized source bytes enter.
            if not workspace.exists():
                workspace.mkdir(mode=0o700)
                for name, digest, count, mode in snapshot.files:
                    raw = (snapshot.directory / name).read_bytes()
                    if len(raw) != count or hashlib.sha256(raw).hexdigest() != digest:
                        raise ValueError
                    target = workspace / name
                    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    target.write_bytes(raw)
                    target.chmod(0o700 if mode == "100755" else 0o600)
            if not workspace.is_dir() or workspace.stat().st_uid != os.getuid() or workspace.stat().st_mode & 0o077:
                raise ValueError
            script = Path(__file__).resolve().parents[1] / "sandbox/scoped_bash.py"
            self.command = ReviewedCommand(
                "scoped-bash", script, hashlib.sha256(script.read_bytes()).hexdigest(), "edit"
            )
            self.registry = NativeCommandRegistry((self.command,))
            self.workspace, self.snapshot, self.session_id = workspace, snapshot, session_id
            self.actor, self.dsn, self.certificates, self.reports = actor, dsn, certificates, reports
            self.job_ref = (
                "build:"
                + hashlib.sha256((scope.sha256() + snapshot.manifest_sha256 + str(session_id)).encode()).hexdigest()
            )
            self.wall_seconds = min(30, self.contract.budget.max_wall_seconds)
            self.profile = SandboxProfile(
                name="scoped-code-edit",
                uid=os.getuid(),
                gid=os.getgid(),
                wall_seconds=self.wall_seconds,
                output_bytes=8192,
                stdin_mode="native-frame-v1",
            )
            self.profile.validate()
        except Exception:
            raise ScopedBashUnavailable("invalid_scoped_bash_binding") from None

    def connect(self) -> psycopg.Connection[Any]:
        return psycopg.connect(self.dsn, connect_timeout=1, options="-c statement_timeout=300 -c lock_timeout=300")

    def authorize(self, connection: psycopg.Connection[Any], *, observation: bool = False) -> None:
        # Match scheduler/cancellation order before taking an attempt/task lock.
        if observation:
            InvocationService().require_observation(UnitOfWork(connection))
        else:
            require_current_policy(UnitOfWork(connection), self.actor, self.scope.policy_ref)
        policy = PolicyService(self.certificates).get(UnitOfWork(connection), self.actor)
        if (
            f"project-policy:{policy.version}:{policy.sha256()}" != self.scope.policy_ref
            or policy.trust.profile != self.contract.trust_profile_id
        ):
            raise KernelDenied("policy_changed")
        row = connection.execute(
            "SELECT c.body,c.sha256 FROM panestria.task t JOIN panestria.goal_contract c ON c.id=t.contract_id"
            " WHERE t.id=%s AND c.goal_id=%s",
            (str(self.scope.task_id), self.contract.goal_id),
        ).fetchone()
        if row is None or str(row[1]).strip() != self.scope.contract_sha256:
            raise KernelDenied("build_contract_changed")
        if contract_sha256(load_contract(row[0])) != self.scope.contract_sha256:
            raise KernelDenied("build_contract_changed")
        decision = PolicyEngine().authorize(
            PolicyRequest(
                owner_id=self.actor.owner_id,
                project_id=self.actor.project_id,
                action="edit",
                label=self.contract.privacy_class,
                destination="local",
                effect_digest=self.scope.sha256(),
            ),
            policy,
        )
        if decision.outcome != "PERMIT":
            raise KernelDenied("scoped_bash_edit_denied")

    def session(self) -> ScopedBashSession:
        return ScopedBashSession(self.job_ref, self.execute)

    def verify_for_review(
        self,
        protected_root: Path,
        repository: Path,
        base: str,
        frozen_directory: Path,
        registry: CommandRegistry,
        *,
        destination_ref: str = "refs/heads/main",
        cancel: threading.Event | None = None,
        deadline: float | None = None,
    ) -> BuildReview:
        """Trusted controller continuation, after a confirmed and reaped tool run.

        No worker can choose the protected repository, verifier registry or check
        set. This creates an exact review request; it never approves or merges it.
        """
        expected = protected_root.resolve() / self.actor.owner_id / self.actor.project_id / "destination.git"

        def active() -> None:
            if (cancel is not None and cancel.is_set()) or (deadline is not None and time.monotonic() >= deadline):
                raise ScopedBashUnavailable("build_verification_cancelled_or_deadline")

        active()
        if repository.is_symlink() or repository.resolve() != expected or not re.fullmatch(r"[0-9a-f]{40}", base):
            raise ScopedBashUnavailable("build_repository_scope_mismatch")
        verify_snapshot(self.snapshot)
        if (
            protected_git(repository, ("rev-parse", "--verify", base + "^{tree}")).decode().strip()
            != self.snapshot.tree
        ):
            raise ScopedBashUnavailable("build_base_changed")
        with self.connect() as connection:
            self.authorize(connection)
            LeaseService().require_current(
                UnitOfWork(connection),
                self.actor,
                str(self.scope.attempt_id),
                self.scope.lease_epoch,
            )
            row = connection.execute(
                "SELECT state,receipt_sha256,binding FROM panestria.worker_invocation"
                " WHERE attempt_id=%s AND invocation_key=%s",
                (str(self.scope.attempt_id), "scoped-bash:" + str(self.session_id)),
            ).fetchone()
            if row is None or row[0] != "RETURNED":
                raise ScopedBashUnavailable("bash_execution_not_confirmed")
            report = json.loads(self.reports.read_blob(str(row[1]).strip()))
            if (
                report.get("job_ref") != self.job_ref
                or report.get("exit_code") != 0
                or report.get("scope_sha256") != self.scope.sha256()
                or row[2]
                != tool_binding(
                    ToolPermit(
                        self.scope,
                        report["request_sha256"],
                        self.registry.sha256(),
                        self.workspace,
                        self.profile,
                        time.monotonic() + self.wall_seconds,
                    )
                ).model_dump(mode="json")
            ):
                raise ScopedBashUnavailable("bash_execution_not_confirmed")
            policy = PolicyService(self.certificates).get(UnitOfWork(connection), self.actor)
            if (
                PolicyEngine()
                .authorize(
                    PolicyRequest(
                        owner_id=self.actor.owner_id,
                        project_id=self.actor.project_id,
                        action="read",
                        label=self.contract.privacy_class,
                        destination="local",
                        effect_digest=self.scope.sha256(),
                    ),
                    policy,
                )
                .outcome
                != "PERMIT"
            ):
                raise KernelDenied("build_verification_read_denied")
            cid = connection.execute(
                "SELECT contract_id::text FROM panestria.task WHERE id=%s", (str(self.scope.task_id),)
            ).fetchone()
            assert cid is not None
            checks = dict(
                connection.execute(
                    "SELECT check_key,id::text FROM panestria.acceptance_check WHERE contract_id=%s",
                    (cid[0],),
                ).fetchall()
            )
            plan_scope = task_plan_scope(UnitOfWork(connection), self.actor, str(self.scope.task_id))
        candidate = capture_candidate(repository, base, self.workspace)
        active()
        snapshot = materialize(repository, base, candidate, frozen_directory)
        verified = verify_build(
            self.contract,
            cid[0],
            str(self.scope.task_id),
            str(self.scope.attempt_id),
            self.scope.lease_epoch,
            base,
            candidate,
            snapshot,
            checks,
            registry,
            policy=policy,
            deadline=deadline,
            plan_scope=plan_scope,
        )
        for raw in verified.reports:
            self.reports.write_report(raw)
        active()
        evidence = BuildEvidenceService(self.reports)
        with self.connect() as connection:
            self.authorize(connection)
            digest = evidence.publish(UnitOfWork(connection), self.actor, verified.bundle)
        approval = None
        if verified.bundle.passed() and (plan_scope is None or plan_scope.integration):
            with self.connect() as connection:
                self.authorize(connection)
                approval = evidence.request_merge(
                    UnitOfWork(connection),
                    self.actor,
                    str(self.scope.task_id),
                    digest,
                    destination_ref,
                )
        return BuildReview(candidate, digest, verified.bundle.passed(), approval)

    def execute(self, script: str, job_ref: str, cancel: threading.Event) -> RegisteredCheckReceipt:
        if job_ref != self.job_ref or cancel.is_set():
            return RegisteredCheckReceipt(outcome="DENIED")
        binding = identity = authority = None
        try:
            script = bash_script(script)
            request = ToolRequest(
                request_id=uuid5(self.session_id, self.job_ref),
                command_ref="scoped-bash",
                payload_json=json.dumps({"job_ref": self.job_ref, "script": script}),
            )
            permit = ToolPermit(
                self.scope,
                request.sha256(),
                self.registry.sha256(),
                self.workspace,
                self.profile,
                time.monotonic() + self.wall_seconds,
            )
            binding = tool_binding(permit)
            with self.connect() as connection:
                self.authorize(connection)
                identity = InvocationService().prepare(
                    UnitOfWork(connection),
                    self.actor,
                    binding,
                    "scoped-bash:" + str(self.session_id),
                    ttl_seconds=self.wall_seconds + 5,
                )
            authority = _EditAuthority(self, identity)
            result = NativeToolGateway(self.workspace.parent, self.registry, authority).execute(
                request,
                permit,
                cancel=cancel,
            )
            sandbox = result.sandbox
            if (
                result.outcome not in {"completed", "failed"}
                or sandbox is None
                or sandbox.reason not in {"completed", "process_failed"}
                or sandbox.exit_code is None
                or (sandbox.reason == "completed") != (sandbox.exit_code == 0)
                or sandbox.oom_killed
                or cancel.is_set()
                or len(sandbox.output) > 8192
            ):
                raise ScopedBashUnavailable("unconfirmed_bash_execution")
            report = json.dumps(
                {
                    "schema_version": 1,
                    "kind": "scoped-bash",
                    "independent_verification": False,
                    "scope_sha256": self.scope.sha256(),
                    "invocation_id": identity,
                    "request_sha256": request.sha256(),
                    "registry_sha256": self.registry.sha256(),
                    "job_ref": self.job_ref,
                    "base_manifest_sha256": self.snapshot.manifest_sha256,
                    "privacy_class": self.contract.privacy_class,
                    "exit_code": sandbox.exit_code,
                    "output_base64": base64.b64encode(sandbox.output).decode("ascii"),
                    "output_sha256": hashlib.sha256(sandbox.output).hexdigest(),
                    "sandbox_profile_sha256": sandbox.profile_sha256,
                    "sandbox_effective_sha256": sandbox.effective_config_sha256,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
            digest = self.reports.write_report(report)
            if self.reports.read_blob(digest) != report or cancel.is_set():
                raise ScopedBashUnavailable("bash_report_unavailable")
            with self.connect() as connection:
                self.authorize(connection)
                service = InvocationService()
                service.check(UnitOfWork(connection), self.actor, binding, identity)
                if cancel.is_set():
                    raise ScopedBashUnavailable("cancelled_before_receipt")
                service.finish(UnitOfWork(connection), self.actor, binding, identity, digest)
            return RegisteredCheckReceipt(outcome="COMPLETED", exit_code=sandbox.exit_code, report_sha256=digest)
        except Exception:
            if authority is not None and authority.claimed and binding is not None and identity is not None:
                try:
                    with self.connect() as connection:
                        InvocationService().finish(UnitOfWork(connection), self.actor, binding, identity, None)
                except Exception:
                    pass  # Unknown effects remain fenced; transport reopen never redispatches.
            return RegisteredCheckReceipt(outcome="CANCELLED" if cancel.is_set() else "UNKNOWN")
