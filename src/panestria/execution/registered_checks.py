"""One controller-bound read-only check; receipts cannot accept or merge a task."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import threading
import time
from typing import Any
from uuid import UUID, uuid5

import psycopg

from panestria.brokers.harness.command_protocol import RegisteredCheckSession
from panestria.contracts.acceptance import TrustedCommandRef
from panestria.contracts.goal import GoalContract, contract_sha256, load_contract
from panestria.contracts.native_command import RegisteredCheckReceipt
from panestria.contracts.native_tools import ToolRequest, ToolScope
from panestria.contracts.policy import PolicyRequest
from panestria.execution.tool_authority import DurableToolAuthority, tool_binding
from panestria.kernel.build import BuildEvidenceStore
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.invocations import InvocationService
from panestria.kernel.policy import PolicyService
from panestria.kernel.uow import UnitOfWork
from panestria.policy.engine import PolicyEngine
from panestria.policy.profiles import CertificateStore
from panestria.sandbox.native_tool_gateway import (
    NativeCommandRegistry,
    NativeToolGateway,
    ReviewedCommand,
    ToolPermit,
)
from panestria.sandbox.profiles import SandboxProfile
from panestria.verification.git_snapshot import GitSnapshot, verify_snapshot


class RegisteredCheckUnavailable(ValueError):
    pass


class _ReadAuthority(DurableToolAuthority):
    def __init__(self, controller: RegisteredCheckController, identity: str) -> None:
        super().__init__(controller.connect, controller.actor, identity)
        self.controller = controller
        self.claimed = False

    def claim(self, permit: ToolPermit) -> None:
        with self.connect() as connection:
            self.controller.authorize(connection)
            self.service.claim(UnitOfWork(connection), self.actor, tool_binding(permit), self.identity)
        self.claimed = True  # Only after this controller's claim commit returned.

    def check(self, permit: ToolPermit) -> None:
        with self.connect() as connection:
            self.controller.authorize(connection)
            self.service.check(UnitOfWork(connection), self.actor, tool_binding(permit), self.identity)

    def _authorize_launch(self, connection: psycopg.Connection[Any], permit: ToolPermit) -> None:
        self.controller.authorize(connection)
        super()._authorize_launch(connection, permit)


class RegisteredCheckController:
    def __init__(
        self,
        dsn: str,
        actor: Actor,
        scope: ToolScope,
        contract: GoalContract,
        session_id: UUID,
        snapshot: GitSnapshot,
        command: ReviewedCommand,
        certificates: CertificateStore,
        reports: BuildEvidenceStore,
    ) -> None:
        try:
            self.scope = ToolScope.model_validate_json(scope.model_dump_json())
            self.contract = load_contract(contract.model_dump(mode="json"))
            specs = [
                check.verifier
                for check in self.contract.acceptance
                if check.required
                and isinstance(check.verifier, TrustedCommandRef)
                and check.verifier.command_ref == command.ref
            ]
            if (
                type(session_id) is not UUID
                or command.access != "read"
                or not specs
                or (str(scope.owner_id), str(scope.project_id)) != (actor.owner_id, actor.project_id)
                or (contract.owner_id, contract.project_id) != (actor.owner_id, actor.project_id)
                or contract_sha256(self.contract) != scope.contract_sha256
                or self.contract.autonomy_profile_ref != scope.policy_ref
                or not snapshot.directory.is_absolute()
                or snapshot.directory.resolve(strict=True) != snapshot.directory
                or snapshot.directory == snapshot.directory.parent
                or len(snapshot.files) > 2000
            ):
                raise ValueError
            verify_snapshot(snapshot)
            self.registry = NativeCommandRegistry((command,))
            self.registry.resolve(command.ref)
            # Detached body and immutable snapshot records prevent caller contract mutation.
            self.snapshot, self.command, self.actor = snapshot, command, actor
            self.dsn, self.certificates, self.reports = dsn, certificates, reports
            self.session_id = session_id
            self.candidate_ref = "snapshot:" + snapshot.manifest_sha256
            self.wall_seconds = min(min(spec.timeout_seconds for spec in specs), contract.budget.max_wall_seconds, 30)
            self.request = ToolRequest(
                request_id=uuid5(session_id, command.ref + ":" + self.candidate_ref),
                command_ref=command.ref,
                payload_json=json.dumps({"candidate_ref": self.candidate_ref, "candidate_tree": snapshot.tree}),
            )
            self.profile = SandboxProfile(
                name="read-only-research",
                uid=os.getuid(),
                gid=os.getgid(),
                wall_seconds=self.wall_seconds,
                output_bytes=8192,
                stdin_mode="native-frame-v1",
            )
            self.profile.validate()
        except Exception:
            raise RegisteredCheckUnavailable("invalid_registered_check_binding") from None

    def connect(self) -> psycopg.Connection[Any]:
        return psycopg.connect(self.dsn, connect_timeout=1, options="-c statement_timeout=300 -c lock_timeout=300")

    def authorize(self, connection: psycopg.Connection[Any]) -> None:
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
            raise KernelDenied("check_contract_changed")
        if contract_sha256(load_contract(row[0])) != self.scope.contract_sha256:
            raise KernelDenied("check_contract_changed")
        decision = PolicyEngine().authorize(
            PolicyRequest(
                owner_id=self.actor.owner_id,
                project_id=self.actor.project_id,
                action="read",
                label=self.contract.privacy_class,
                destination="local",
                effect_digest=self.request.sha256(),
            ),
            policy,
        )
        if decision.outcome != "PERMIT":
            raise KernelDenied("registered_check_read_denied")

    def session(self) -> RegisteredCheckSession:
        return RegisteredCheckSession((self.command.ref,), self.candidate_ref, self.execute, max_calls=1)

    def execute(self, command_ref: str, candidate_ref: str, cancel: threading.Event) -> RegisteredCheckReceipt:
        if command_ref != self.command.ref or candidate_ref != self.candidate_ref or cancel.is_set():
            return RegisteredCheckReceipt(outcome="DENIED")
        binding = identity = authority = None
        try:
            verify_snapshot(self.snapshot)
            permit = ToolPermit(
                self.scope,
                self.request.sha256(),
                self.registry.sha256(),
                self.snapshot.directory,
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
                    "registered-check:" + str(self.session_id),
                    ttl_seconds=self.wall_seconds + 5,
                )
            authority = _ReadAuthority(self, identity)
            result = NativeToolGateway(
                self.snapshot.directory.parent,
                self.registry,
                authority,
                runner_factory=authority.runner_factory(permit),
            ).execute(
                self.request,
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
                raise RegisteredCheckUnavailable("unconfirmed_registered_check")
            verify_snapshot(self.snapshot)
            report = json.dumps(
                {
                    "schema_version": 1,
                    "kind": "registered-read-check",
                    "independent_verification": False,
                    "task_id": str(self.scope.task_id),
                    "attempt_id": str(self.scope.attempt_id),
                    "lease_epoch": self.scope.lease_epoch,
                    "scope_sha256": self.scope.sha256(),
                    "invocation_id": identity,
                    "request_sha256": self.request.sha256(),
                    "registry_sha256": self.registry.sha256(),
                    "command_sha256": self.command.sha256,
                    "candidate_ref": self.candidate_ref,
                    "candidate_tree": self.snapshot.tree,
                    "privacy_class": self.contract.privacy_class,
                    "execution_outcome": result.outcome,
                    "sandbox_reason": sandbox.reason,
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
                raise RegisteredCheckUnavailable("registered_check_report_unavailable")
            # Check again after report publication; revocation never becomes a success receipt.
            with self.connect() as connection:
                self.authorize(connection)
                service = InvocationService()
                service.check(UnitOfWork(connection), self.actor, binding, identity)
                if cancel.is_set():
                    raise RegisteredCheckUnavailable("cancelled_before_receipt")
                service.finish(UnitOfWork(connection), self.actor, binding, identity, digest)
            if cancel.is_set():
                return RegisteredCheckReceipt(outcome="CANCELLED")
            return RegisteredCheckReceipt(outcome="COMPLETED", exit_code=sandbox.exit_code, report_sha256=digest)
        except Exception:
            if authority is not None and authority.claimed and binding is not None and identity is not None:
                try:
                    with self.connect() as connection:
                        InvocationService().finish(UnitOfWork(connection), self.actor, binding, identity, None)
                except Exception:
                    pass  # A lost DB reply stays fenced/uncertain, never safe to redispatch.
            return RegisteredCheckReceipt(outcome="CANCELLED" if cancel.is_set() else "UNKNOWN")
