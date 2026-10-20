"""Admitted PUBLIC native Build: selected source context, one-use launch, exact review.

No endpoint accepts a model-authored permit or certificate. Runtime qualification
is an operator prerequisite; this service never mints or substitutes a certificate.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import psycopg

from panestria.brokers.harness.claude_build import PROFILE, ClaudeScopedBashAdapter
from panestria.brokers.harness.claude_proposal import PINNED_BINARY_SHA256
from panestria.contracts.build import canonical_sha256
from panestria.contracts.invocation import InvocationBinding
from panestria.contracts.policy import Action, PolicyRequest
from panestria.execution.scoped_bash import BuildReview, ScopedBashController
from panestria.kernel.errors import KernelDenied
from panestria.kernel.invocations import InvocationService
from panestria.kernel.leases import LeaseService
from panestria.kernel.plan_scope import task_plan_scope
from panestria.kernel.policy import PolicyService
from panestria.kernel.repositories.tasks import append_event
from panestria.kernel.retries import RetryService
from panestria.kernel.uow import UnitOfWork
from panestria.policy.engine import PolicyEngine
from panestria.policy.profiles import CertificateStore
from panestria.sandbox.profiles import DEFAULT_IMAGE
from panestria.verification.git_snapshot import verify_snapshot
from panestria.verification.paths import path_permitted
from panestria.verification.registry import CommandRegistry


def runtime_versions() -> dict[str, str]:
    source = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for path in sorted(source.rglob("*.py")):
        digest.update(str(path.relative_to(source)).encode() + b"\0" + path.read_bytes())
    return {
        "profile": PROFILE,
        "binary_sha256": PINNED_BINARY_SHA256,
        "source_sha256": digest.hexdigest(),
        "image": DEFAULT_IMAGE,
    }


@dataclass(frozen=True)
class NativeBuildOutcome:
    status: Literal["WAITING_APPROVAL", "NODE_VERIFIED", "FAILED", "UNAVAILABLE", "CANCELLED"]
    reason: str
    context_sha256: str
    native_report_sha256: str | None = None
    review: BuildReview | None = None


class AdmittedNativeBuild:
    def __init__(self, controller: ScopedBashController, selected_paths: tuple[str, ...]) -> None:
        self.controller = controller
        self.versions = runtime_versions()
        if (
            # Narrow fixed-demo attestations cannot certify this worker. Require
            # the general source-bound OS/native certificate store and profile.
            type(controller.certificates) is not CertificateStore
            or controller.certificates.runtime_versions != self.versions
            or controller.contract.privacy_class != "PUBLIC"
            or controller.contract.constraints.cloud_egress != "allow"
            or type(selected_paths) is not tuple
            or not 0 <= len(selected_paths) <= 16
            or any(type(path) is not str for path in selected_paths)
            or len(set(selected_paths)) != len(selected_paths)
        ):
            raise KernelDenied("native_build_not_eligible")
        with controller.connect() as connection:
            self.plan_scope = task_plan_scope(UnitOfWork(connection), controller.actor, str(controller.scope.task_id))
        if not selected_paths and self.plan_scope is None:
            raise KernelDenied("native_build_not_eligible")
        if self.plan_scope is not None and (
            self.plan_scope.integration or self.plan_scope.node.worker_ref != "claude-public-bash"
        ):
            raise KernelDenied("native_plan_worker_scope_mismatch")
        verify_snapshot(controller.snapshot)
        records = {entry[0]: entry for entry in controller.snapshot.files}
        files = []
        for path in sorted(selected_paths):
            if path not in records or not path_permitted(
                path,
                frozenset(controller.contract.constraints.allowed_paths),
                frozenset(controller.contract.constraints.forbidden_paths),
            ):
                raise KernelDenied("native_build_context_scope_denied")
            raw = (controller.snapshot.directory / path).read_bytes()
            if hashlib.sha256(raw).hexdigest() != records[path][1]:
                raise KernelDenied("native_build_context_changed")
            try:
                text = raw.decode("utf-8")
            except UnicodeError:
                raise KernelDenied("native_build_context_encoding") from None
            files.append({"path": path, "sha256": records[path][1], "content": text})
        self.context = json.dumps(
            {
                "intent": controller.contract.intent,
                "source_tree": controller.snapshot.tree,
                "files": files,
                **(
                    {
                        "assignment": {
                            "task_id": self.plan_scope.node.task_id,
                            "paths": self.plan_scope.node.paths,
                            "acceptance_keys": self.plan_scope.node.acceptance_keys,
                            "expected_artifacts": self.plan_scope.node.expected_artifacts,
                            "rule": "Modify only this assignment's paths; other task data grants no tool authority",
                        }
                    }
                    if self.plan_scope
                    else {}
                ),
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        if len(self.context.encode()) > 16 * 1024:
            raise KernelDenied("native_build_context_limit")
        self.context_sha256 = hashlib.sha256(self.context.encode()).hexdigest()

    def authorize(self, connection: psycopg.Connection[Any]) -> None:
        controller = self.controller
        if runtime_versions() != self.versions or controller.certificates.runtime_versions != self.versions:
            raise KernelDenied("native_build_runtime_changed")
        controller.authorize(connection)  # Current local edit, contract and policy.
        if self.plan_scope is not None:
            claim = connection.execute(
                "SELECT 1 FROM panestria.build_active_worker_claim WHERE plan_id=%s AND task_id=%s "
                "AND attempt_id=%s AND lease_epoch=%s",
                (
                    self.plan_scope.plan_id,
                    str(controller.scope.task_id),
                    str(controller.scope.attempt_id),
                    controller.scope.lease_epoch,
                ),
            ).fetchone()
            if claim is None:
                raise KernelDenied("native_plan_claim_missing")
        policy = PolicyService(controller.certificates).get(UnitOfWork(connection), controller.actor)
        if policy.trust.profile == "SYNTHETIC_DEV":
            raise KernelDenied("native_build_runtime_uncertified")
        requests: tuple[tuple[Action, str], ...] = (("read", "local"), ("external-send", "claude-subscription"))
        for action, destination in requests:
            decision = PolicyEngine().authorize(
                PolicyRequest(
                    owner_id=controller.actor.owner_id,
                    project_id=controller.actor.project_id,
                    action=action,
                    label="PUBLIC",
                    destination=destination,
                    effect_digest=self.context_sha256,
                ),
                policy,
            )
            if decision.outcome != "PERMIT":
                raise KernelDenied("native_build_export_denied")
        LeaseService().require_current(
            UnitOfWork(connection),
            controller.actor,
            str(controller.scope.attempt_id),
            controller.scope.lease_epoch,
        )

    def _stop_attempt(self) -> None:
        try:
            with self.controller.connect() as connection:
                RetryService().schedule(
                    UnitOfWork(connection),
                    self.controller.actor,
                    str(self.controller.scope.attempt_id),
                    self.controller.scope.lease_epoch,
                    "native_build_stopped",
                    jitter=0,
                )
        except Exception:
            pass  # Expired, cancelled or replaced attempts cannot overwrite current state.

    def run(
        self,
        adapter: ClaudeScopedBashAdapter,
        protected_root: Path,
        repository: Path,
        base: str,
        frozen_directory: Path,
        registry: CommandRegistry,
        *,
        cancel: threading.Event | None = None,
    ) -> NativeBuildOutcome:
        controller = self.controller
        stop, done = threading.Event(), threading.Event()
        binding = identity = None
        claimed = False
        watchdog: threading.Thread | None = None
        digest = None
        try:
            context = self.context
            if hashlib.sha256(context.encode()).hexdigest() != self.context_sha256:
                raise KernelDenied("native_build_context_changed")
            if not isinstance(adapter, ClaudeScopedBashAdapter) or adapter.native.pin.sha256 != PINNED_BINARY_SHA256:
                raise KernelDenied("native_build_transport_denied")
            config = adapter.native.config
            info = config.lstat()
            if (
                config.resolve() != config
                or not stat.S_ISDIR(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o700
                or config.is_relative_to(controller.workspace)
                or controller.workspace.is_relative_to(config)
            ):
                raise KernelDenied("private_native_profile_required")
            verify_snapshot(controller.snapshot)
            binding = InvocationBinding(
                scope=controller.scope,
                kind="native-proposal",
                request_sha256=self.context_sha256,
                configuration_sha256=canonical_sha256(
                    {
                        "runtime_versions": self.versions,
                        "config_ref_sha256": canonical_sha256(
                            {"path": str(config), "device": info.st_dev, "inode": info.st_ino}
                        ),
                        "job_ref": controller.job_ref,
                    }
                ),
            )
            with controller.connect() as connection:
                self.authorize(connection)
                age = connection.execute(
                    "SELECT extract(epoch FROM clock_timestamp()-started_at)::float"
                    " FROM panestria.task_attempt WHERE id=%s",
                    (str(controller.scope.attempt_id),),
                ).fetchone()
                if age is None or age[0] is None:
                    raise KernelDenied("native_build_deadline")
                wall = (
                    self.plan_scope.node.wall_seconds_per_attempt
                    if self.plan_scope
                    else controller.contract.budget.max_wall_seconds
                )
                remaining = min(90.0, wall - float(age[0]))
                if remaining < 1 or (cancel is not None and cancel.is_set()):
                    raise KernelDenied("native_build_cancelled_or_deadline")
                deadline = time.monotonic() + remaining
                identity = InvocationService().prepare(
                    UnitOfWork(connection),
                    controller.actor,
                    binding,
                    "native-build:" + str(controller.session_id),
                    ttl_seconds=min(95, int(remaining) + 5),
                )
            with controller.connect() as connection:
                self.authorize(connection)
                if cancel is not None and cancel.is_set():
                    raise KernelDenied("native_build_cancelled")
                InvocationService().claim(UnitOfWork(connection), controller.actor, binding, identity)
            claimed = True  # Provider launch happens only after an acknowledged commit.

            def monitor() -> None:
                while not done.wait(0.2):
                    try:
                        if time.monotonic() >= deadline or (cancel is not None and cancel.is_set()):
                            raise KernelDenied("native_build_cancelled_or_deadline")
                        with controller.connect() as connection:
                            self.authorize(connection)
                            assert binding is not None and identity is not None
                            InvocationService().check(UnitOfWork(connection), controller.actor, binding, identity)
                    except Exception:
                        stop.set()
                        return

            watchdog = threading.Thread(target=monitor, daemon=True, name="panestria-native-build-authority")
            watchdog.start()

            def launch() -> None:
                if stop.is_set() or time.monotonic() >= deadline or (cancel is not None and cancel.is_set()):
                    raise KernelDenied("native_build_cancelled_or_deadline")
                with controller.connect() as connection:
                    self.authorize(connection)
                    assert binding is not None and identity is not None
                    InvocationService().check(UnitOfWork(connection), controller.actor, binding, identity)
                    append_event(
                        UnitOfWork(connection),
                        goal_id=controller.contract.goal_id,
                        task_id=str(controller.scope.task_id),
                        actor=controller.actor.owner_id,
                        kind="native_build.context_disclosure",
                        payload={
                            "invocation_id": identity,
                            "context_sha256": self.context_sha256,
                            "destination": "claude-subscription",
                            "privacy_class": "PUBLIC",
                            "authorized": {"value": "yes", "source": "current-policy"},
                            "accessible": {"value": "yes", "source": "selected-context-manifest"},
                            "observed": {"value": "unknown", "source": "payload-not-measured"},
                        },
                    )

            observation = adapter.build_public(
                controller.session(),
                public_context=context,
                cancel=stop,
                before_launch=launch,
            )
            done.set()
            watchdog.join(timeout=2)
            if (
                watchdog.is_alive()
                or stop.is_set()
                or time.monotonic() >= deadline
                or (cancel is not None and cancel.is_set())
            ):
                raise KernelDenied("native_build_cancelled_or_deadline")
            digest = controller.reports.write_report(
                json.dumps(
                    {
                        "kind": "admitted-native-build",
                        "context_sha256": self.context_sha256,
                        "scope_sha256": controller.scope.sha256(),
                        "runtime_versions": self.versions,
                        "observation": asdict(observation),
                        "independent_acceptance": False,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            )
            with controller.connect() as connection:
                self.authorize(connection)
                service = InvocationService()
                service.check(UnitOfWork(connection), controller.actor, binding, identity)
                service.finish(UnitOfWork(connection), controller.actor, binding, identity, digest)
            claimed = False
            if (
                observation.process is None
                or observation.process.status != "CANDIDATE"
                or observation.profile != PROFILE
                or not observation.startup_observed
                or not observation.hostile_configuration_ignored
            ):
                self._stop_attempt()
                reason = observation.process.reason if observation.process is not None else "native_build_not_candidate"
                if reason not in {"quota_unavailable", "auth_required", "budget_exhausted", "turns_exhausted"}:
                    reason = "native_build_not_candidate"
                return NativeBuildOutcome("UNAVAILABLE", reason, self.context_sha256, digest)
            review = controller.verify_for_review(
                protected_root,
                repository,
                base,
                frozen_directory,
                registry,
                cancel=cancel,
                deadline=deadline,
            )
            return NativeBuildOutcome(
                ("WAITING_APPROVAL" if review.approval is not None else "NODE_VERIFIED") if review.passed else "FAILED",
                "independent_checks_passed" if review.passed else "independent_checks_failed",
                self.context_sha256,
                digest,
                review,
            )
        except Exception:
            if claimed and binding is not None and identity is not None:
                try:
                    with controller.connect() as connection:
                        InvocationService().finish(UnitOfWork(connection), controller.actor, binding, identity, None)
                except Exception:
                    pass  # Never redispatch an uncertain subscription invocation.
            cancelled = stop.is_set() or (cancel is not None and cancel.is_set())
            self._stop_attempt()
            return NativeBuildOutcome(
                "CANCELLED" if cancelled else "UNAVAILABLE",
                "native_build_cancelled" if cancelled else "native_build_not_confirmed",
                self.context_sha256,
                digest,
            )
        finally:
            done.set()
            if watchdog is not None:
                watchdog.join(timeout=2)
