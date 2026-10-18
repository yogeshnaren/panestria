"""Fixed public single-worker demo. PostgreSQL remains the source of task truth.

External calls have committed one-use intents. Restart never replays a native
call or a container write. Only explicit owner decisions dispatch protected CAS.
"""

from __future__ import annotations

import difflib
import fcntl
import hashlib
import json
import os
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator
from uuid import UUID, uuid4

import psycopg

from panestria.brokers.harness.claude_proposal import ClaudeProposalAdapter, ProposalUnavailable
from panestria.contracts.build import canonical_sha256
from panestria.contracts.goal import contract_sha256, load_contract
from panestria.contracts.invocation import InvocationBinding
from panestria.contracts.native_proposal import BASE_SOURCE, PROFILE, PROMPT_SHA256, TASK, CodeProposal
from panestria.contracts.native_tools import ToolRequest, ToolScope
from panestria.contracts.policy import (
    Action,
    Autonomy,
    AutonomyAxis,
    PolicyContext,
    PolicyRequest,
    PrivacyAxis,
    TrustAxis,
)
from panestria.execution.build_merge import VerifiedGitTarget, prepare_merge
from panestria.execution.outbox import EffectExecutor
from panestria.execution.proposal_certificate import ACTIONS, ASSETS, CASES, ProposalCertificateStore, runtime_versions
from panestria.execution.tool_authority import DurableToolAuthority, tool_binding
from panestria.kernel.approvals import ApprovalService
from panestria.kernel.build import BuildEvidenceService, BuildEvidenceStore
from panestria.kernel.cancellation import CancellationService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor, GoalService
from panestria.kernel.invocations import InvocationService
from panestria.kernel.leases import LeaseService
from panestria.kernel.policy import PolicyService
from panestria.kernel.repositories.policy import current_policy
from panestria.kernel.repositories.tasks import append_event
from panestria.kernel.uow import UnitOfWork
from panestria.policy.engine import PolicyEngine
from panestria.policy.profiles import CertificateRejected
from panestria.sandbox.native_tool_gateway import NativeCommandRegistry, NativeToolGateway, ReviewedCommand, ToolPermit
from panestria.sandbox.profiles import DEFAULT_IMAGE, SandboxProfile
from panestria.verification.build import verify_build
from panestria.verification.git_snapshot import materialize
from panestria.verification.registry import CommandRegistry
from panestria.verification.sandboxed import SandboxedCheckRunner


class DemoUnavailable(Exception):
    pass


def _git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), "-c", "core.hooksPath=/dev/null", *args],
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
        env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "GIT_CONFIG_NOSYSTEM": "1"},
    )
    return result.stdout.strip()


def _private(path: Path) -> Path:
    if path.is_symlink():
        raise DemoUnavailable("unsafe_demo_root")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.resolve() != path or path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
        raise DemoUnavailable("private_demo_root_required")
    return path


def _atomic(path: Path, body: object) -> None:
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(body, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


@contextmanager
def _lock(path: Path) -> Iterator[None]:
    with path.open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise DemoUnavailable("demo_operation_running") from None
        yield


def contract_document(actor: Actor, goal: str, policy: PolicyContext) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "goal_id": goal,
        "contract_version": 1,
        "owner_id": actor.owner_id,
        "project_id": actor.project_id,
        "intent": TASK,
        "privacy_class": "PUBLIC",
        "trust_profile_id": policy.trust.profile,
        "autonomy_profile_ref": f"project-policy:{policy.version}:{policy.sha256()}",
        "constraints": {
            "allowed_paths": ["calculator.py"],
            "forbidden_paths": [".env*", ".git/**", "secrets/**"],
            "permitted_capabilities": ["scoped-file-edit", "trusted-test-runner"],
            "cloud_egress": "allow",
        },
        "budget": {"max_attempts_per_task": 1, "max_wall_seconds": 300, "max_api_usd": "0.000000"},
        "acceptance": [
            {
                "id": "AC-001",
                "description": "Independent arithmetic tests in a read-only container",
                "required": True,
                "verifier": {
                    "type": "trusted-command-ref",
                    "command_ref": "synthetic-required",
                    "expected_exit_code": 0,
                    "timeout_seconds": 30,
                },
                "evidence": {"required": True, "kind": "trusted-command-ref-report"},
            },
            {
                "id": "AC-002",
                "description": "Only calculator.py changes",
                "required": True,
                "verifier": {
                    "type": "git-diff-path-check",
                    "allowed_paths": ["calculator.py"],
                    "forbidden_paths": [".env*", ".git/**", "secrets/**"],
                },
                "evidence": {"required": True, "kind": "git-diff-path-check-report"},
            },
            {
                "id": "AC-003",
                "description": "Protected merge needs owner approval",
                "required": True,
                "verifier": {"type": "policy-decision", "action": "protected-merge", "expected": "approval-required"},
                "evidence": {"required": True, "kind": "policy-decision-report"},
            },
        ],
        "non_goals": [
            "private repositories",
            "Cursor orchestration",
            "native tools",
            "provider fallback",
            "API billing",
        ],
    }


class ProposalDemo:
    def __init__(self, root: Path, dsn: str, adapter: ClaudeProposalAdapter) -> None:
        self.root, self.dsn, self.adapter = _private(root), dsn, adapter
        self.store = BuildEvidenceStore(_private(root / "evidence"))
        self.evidence = BuildEvidenceService(self.store)
        self.certificates = ProposalCertificateStore(_private(root / "certificates"))
        assets_sha = canonical_sha256(
            {
                name: hashlib.sha256((ASSETS / name).read_bytes()).hexdigest()
                for name in ("apply.py", "required_check.py")
            }
        )
        self.assets = _private(_private(root / "reviewed-assets") / assets_sha)
        for name in ("apply.py", "required_check.py"):
            target, raw = self.assets / name, (ASSETS / name).read_bytes()
            if target.exists() or target.is_symlink():
                if target.is_symlink() or target.read_bytes() != raw or target.stat().st_mode & 0o022:
                    raise DemoUnavailable("reviewed_asset_changed")
                continue
            fd, temporary = tempfile.mkstemp(dir=self.assets)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                    os.fchmod(stream.fileno(), 0o400)
                os.replace(temporary, target)
            finally:
                Path(temporary).unlink(missing_ok=True)
        self.registry = CommandRegistry.load(self.assets, "/reviewed/python")
        self._jobs: dict[str, threading.Thread] = {}
        self._cancels: dict[str, threading.Event] = {}
        self._mutex = threading.Lock()
        identity = root / "identity.json"
        if not identity.exists():
            _atomic(
                identity,
                {
                    "owner": str(uuid4()),
                    "project": str(uuid4()),
                    "setup_goal": str(uuid4()),
                    "setup_task": str(uuid4()),
                    "session_secret": os.urandom(32).hex(),
                },
            )
        if identity.is_symlink() or identity.stat().st_mode & 0o077:
            raise DemoUnavailable("private_demo_identity_required")
        self.identity = json.loads(identity.read_bytes())
        self.actor = Actor(self.identity["owner"], self.identity["project"])
        self.protected = _private(root / "protected")
        scope = _private(_private(self.protected / self.actor.owner_id) / self.actor.project_id)
        self.bare = scope / "destination.git"

    def connect(self) -> psycopg.Connection[Any]:
        return psycopg.connect(self.dsn, connect_timeout=1, options="-c statement_timeout=3000")

    def initialize(self) -> None:
        with _lock(self.root / "operation.lock"):
            with self.connect() as c:
                exists = c.execute(
                    "SELECT 1 FROM panestria.project WHERE id=%s AND owner_id=%s",
                    (self.actor.project_id, self.actor.owner_id),
                ).fetchone()
                if exists is None:
                    c.execute(
                        "INSERT INTO panestria.principal(id,display_name) VALUES (%s,'Demo owner')",
                        (self.actor.owner_id,),
                    )
                    c.execute(
                        "INSERT INTO panestria.project(id,owner_id) VALUES (%s,%s)",
                        (self.actor.project_id, self.actor.owner_id),
                    )
                    c.execute(
                        "INSERT INTO panestria.goal(id,owner_id,project_id,intent,status) "
                        "VALUES (%s,%s,%s,'Demo setup','CREATED')",
                        (self.identity["setup_goal"], self.actor.owner_id, self.actor.project_id),
                    )
                    cid = str(uuid4())
                    c.execute(
                        "INSERT INTO panestria.goal_contract(id,goal_id,version,body,sha256)"
                        " VALUES (%s,%s,1,%s::jsonb,%s)",
                        (cid, self.identity["setup_goal"], "{}", "00" * 32),
                    )
                    c.execute(
                        "INSERT INTO panestria.task(id,goal_id,contract_id,name,state) VALUES "
                        "(%s,%s,%s,'setup','READY')",
                        (self.identity["setup_task"], self.identity["setup_goal"], cid),
                    )
                    PolicyService(self.certificates).initialize(UnitOfWork(c), self.actor, self.identity["setup_task"])
            if not self.bare.exists():
                with tempfile.TemporaryDirectory(dir=self.root) as directory:
                    source = Path(directory)
                    _git(source, "init", "-b", "main")
                    _git(source, "config", "user.name", "Panestria synthetic demo")
                    _git(source, "config", "user.email", "demo@panestria.invalid")
                    (source / "calculator.py").write_text(BASE_SOURCE)
                    _git(source, "add", "calculator.py")
                    _git(source, "commit", "-m", "chore(demo): add synthetic calculator exercise")
                    _git(source, "clone", "--bare", str(source), str(self.bare))

    def proposed_policy(self, digest: str) -> PolicyContext:
        with self.connect() as c:
            old = current_policy(UnitOfWork(c), self.actor)
        trust = TrustAxis(
            version=old.trust.version + 1,
            profile="PERSONAL_SANDBOX",
            allowed_actions=ACTIONS,
            runtime_certificate_sha256=digest,
        )
        actions: dict[Action, Autonomy] = {action: "observe" for action in old.autonomy.actions}
        actions.update(
            {
                "read": "act-and-report",
                "edit": "act-and-report",
                "external-send": "act-and-report",
                "merge": "approve-first",
            }
        )
        privacy = PrivacyAxis(version=old.privacy.version + 1, cloud_destinations=["claude-subscription"])
        autonomy = AutonomyAxis(version=old.autonomy.version + 1, actions=actions)
        if old.trust.model_dump(exclude={"version"}) == trust.model_dump(exclude={"version"}):
            trust = old.trust
        if old.privacy.model_dump(exclude={"version"}) == privacy.model_dump(exclude={"version"}):
            privacy = old.privacy
        if old.autonomy.model_dump(exclude={"version"}) == autonomy.model_dump(exclude={"version"}):
            autonomy = old.autonomy
        if trust == old.trust and privacy == old.privacy and autonomy == old.autonomy:
            return old
        return PolicyContext(
            owner_id=old.owner_id,
            project_id=old.project_id,
            version=old.version + 1,
            trust=trust,
            privacy=privacy,
            autonomy=autonomy,
        )

    def readiness(self) -> dict[str, Any]:
        state: dict[str, Any] = {
            "profile": PROFILE,
            "provider": "Claude Code / Anthropic subscription",
            "prompt_sha256": PROMPT_SHA256,
            "task": TASK,
            "base_source": BASE_SOURCE,
            "ready": False,
            "reason": "native_qualification_required",
            "policy": None,
            "certificate_sha256": None,
            "qualification": None,
        }
        receipt = self.root / "qualification.json"
        if receipt.exists():
            state["qualification"] = json.loads(receipt.read_bytes())
        pointer = self.root / "certificate.json"
        if pointer.exists():
            digest = json.loads(pointer.read_bytes())["sha256"]
            try:
                self.certificates.validate(
                    TrustAxis(
                        version=1,
                        profile="PERSONAL_SANDBOX",
                        allowed_actions=ACTIONS,
                        runtime_certificate_sha256=digest,
                    )
                )
                policy = self.proposed_policy(digest)
            except (CertificateRejected, KernelDenied):
                state["reason"] = "native_qualification_stale"
            else:
                state.update(
                    ready=True,
                    reason="qualified_fixed_public_demo",
                    certificate_sha256=digest,
                    policy=policy.model_dump(),
                    policy_sha256=policy.sha256(),
                )
        return state

    def _runtime_ready(self) -> bool:
        try:
            result = subprocess.run(
                ["docker", "image", "inspect", DEFAULT_IMAGE], capture_output=True, timeout=5, check=False
            )
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def qualify(self) -> dict[str, Any]:
        # Explicit operator diagnostic, before task cloud permissions exist.
        # No arbitrary input, project context or automatic retry is supported.
        with _lock(self.root / "operation.lock"):
            with self.connect() as c:
                active = c.execute(
                    "SELECT 1 FROM panestria.goal WHERE project_id=%s AND id!=%s "
                    "AND status NOT IN ('COMPLETED','FAILED','CANCELLED','REJECTED')",
                    (self.actor.project_id, self.identity["setup_goal"]),
                ).fetchone()
                if active:
                    raise DemoUnavailable("another_demo_goal_active")
            journal = self.root / "qualification.json"
            if journal.exists() and json.loads(journal.read_bytes()).get("status") == "STARTED":
                raise DemoUnavailable("qualification_outcome_unknown_owner_resolution_required")
            if not self._runtime_ready():
                outcome = {"status": "UNAVAILABLE", "reason": "container_runtime_not_prepared"}
                _atomic(journal, outcome)
                return outcome
            versions = runtime_versions()
            if versions != self.certificates.runtime_versions:
                outcome = {"status": "UNAVAILABLE", "reason": "runtime_changed_restart_required"}
                _atomic(journal, outcome)
                return outcome
            _atomic(
                journal,
                {"status": "STARTED", "reason": "operator_requested", "started_at": datetime.now(UTC).isoformat()},
            )
            try:
                native = self.adapter.propose()
                if native.status != "CANDIDATE" or native.proposal is None:
                    raise DemoUnavailable(native.reason)
                with tempfile.TemporaryDirectory(dir=self.root, prefix="qualification-") as directory:
                    parent = Path(directory)
                    workspace = parent / "candidate"
                    workspace.mkdir()
                    (workspace / "calculator.py").write_text(BASE_SOURCE)

                    # Qualification probes the actual no-secret writer and separate
                    # readonly verifier; it does not claim kernel invocation proof.
                    class ProbeAuthority:
                        claimed = False

                        def claim(self, permit: ToolPermit) -> None:
                            if self.claimed:
                                raise DemoUnavailable("probe_already_claimed")
                            self.claimed = True

                        def check(self, permit: ToolPermit) -> None:
                            if not self.claimed:
                                raise DemoUnavailable("probe_not_claimed")

                    request, permit, registry = self._tool(
                        native.proposal,
                        workspace,
                        ToolScope(
                            owner_id=UUID(self.actor.owner_id),
                            project_id=UUID(self.actor.project_id),
                            task_id=uuid4(),
                            attempt_id=uuid4(),
                            lease_epoch=1,
                            contract_sha256=PROMPT_SHA256,
                            policy_ref="operator-probe",
                        ),
                    )
                    applied = NativeToolGateway(parent, registry, ProbeAuthority()).execute(request, permit)
                    if applied.outcome != "completed" or applied.sandbox is None or applied.sandbox.exit_code != 0:
                        raise DemoUnavailable("qualification_apply_failed")
                    checked = SandboxedCheckRunner(self.registry, parent).run("synthetic-required", workspace, 30)
                    if checked.verdict != "PASS":
                        raise DemoUnavailable("qualification_verifier_failed")
                cases = {}
                for key, mode in CASES.items():
                    report = {
                        "case_id": key,
                        "verdict": "PASS",
                        "execution_mode": mode,
                        "runtime_versions": versions,
                        "native_stdout_sha256": native.process.stdout_sha256,
                        "native_stderr_sha256": native.process.stderr_sha256,
                        "proposal_sha256": canonical_sha256(native.proposal.model_dump()),
                        "apply_profile_sha256": applied.sandbox.profile_sha256,
                        "verify_output_sha256": checked.output_sha256,
                    }
                    cases[key] = self.certificates.blobs.write_report(json.dumps(report, sort_keys=True).encode())
                if versions != runtime_versions():
                    raise DemoUnavailable("runtime_changed_during_qualification")
                certificate = {
                    "purpose": PROFILE,
                    "runtime_versions": versions,
                    "cases": cases,
                    "expires_at": (datetime.now(UTC) + timedelta(hours=24)).isoformat(),
                }
                digest = self.certificates.blobs.write_report(json.dumps(certificate, sort_keys=True).encode())
                _atomic(self.root / "certificate.json", {"sha256": digest})
                outcome = {"status": "PASS", "reason": "fixed_public_profile_only", "certificate_sha256": digest}
            except (DemoUnavailable, ProposalUnavailable) as exc:
                outcome = {"status": "UNAVAILABLE", "reason": str(exc)}
            except Exception:
                outcome = {"status": "UNAVAILABLE", "reason": "qualification_failed"}
            _atomic(journal, outcome)
            return outcome

    def _tool(
        self, proposal: CodeProposal, workspace: Path, scope: ToolScope
    ) -> tuple[ToolRequest, ToolPermit, NativeCommandRegistry]:
        script = self.assets / "apply.py"
        registry = NativeCommandRegistry(
            (ReviewedCommand("apply-calculator", script, hashlib.sha256(script.read_bytes()).hexdigest(), "edit"),)
        )
        request = ToolRequest(
            request_id=uuid4(), command_ref="apply-calculator", payload_json=proposal.model_dump_json()
        )
        permit = ToolPermit(
            scope,
            request.sha256(),
            registry.sha256(),
            workspace,
            SandboxProfile(name="scoped-code-edit", uid=os.getuid(), gid=os.getgid(), stdin_mode="native-frame-v1"),
            time.monotonic() + 30,
        )
        return request, permit, registry

    def start(
        self,
        goal_id: str,
        certificate: str,
        policy_sha: str,
        *,
        authorize: Callable[[psycopg.Connection[Any]], None] | None = None,
    ) -> bool:
        try:
            if str(UUID(goal_id, version=4)) != goal_id:
                raise ValueError
        except ValueError:
            raise DemoUnavailable("invalid_goal_id") from None
        with _lock(self.root / "operation.lock"):
            if not self._runtime_ready():
                raise DemoUnavailable("container_runtime_not_prepared")
            ready = self.readiness()
            if not ready["ready"] or ready["certificate_sha256"] != certificate or ready["policy_sha256"] != policy_sha:
                raise DemoUnavailable("reviewed_policy_changed_or_unavailable")
            policy = self.proposed_policy(certificate)
            with self.connect() as c:
                if authorize:
                    authorize(c)
                uow = UnitOfWork(c)
                c.execute(
                    "SELECT id FROM panestria.project WHERE id=%s AND owner_id=%s FOR UPDATE",
                    (self.actor.project_id, self.actor.owner_id),
                )
                existing = c.execute(
                    "SELECT id FROM panestria.goal WHERE id=%s AND owner_id=%s AND project_id=%s",
                    (goal_id, self.actor.owner_id, self.actor.project_id),
                ).fetchone()
                if existing:
                    return False
                active = c.execute(
                    "SELECT 1 FROM panestria.goal WHERE project_id=%s AND id!=%s"
                    " AND status NOT IN ('COMPLETED','FAILED','CANCELLED','REJECTED')",
                    (self.actor.project_id, self.identity["setup_goal"]),
                ).fetchone()
                if active:
                    raise DemoUnavailable("another_demo_goal_active")
                if _git(self.bare, "show", "refs/heads/main:calculator.py") + "\n" != BASE_SOURCE:
                    raise DemoUnavailable("exercise_already_merged_use_new_demo_root")
                old = current_policy(uow, self.actor)
                if old != policy:
                    service = PolicyService(self.certificates)
                    review = service.propose(uow, self.actor, self.identity["setup_task"], policy)
                    service.decide(uow, self.actor, review.review_id, review.effect_digest, "approve")
                    service.apply(uow, self.actor, review.review_id, review.effect_digest)
                document = contract_document(self.actor, goal_id, policy)
                GoalService().submit(uow, self.actor, document, goal_id)
                contract_row = c.execute(
                    "SELECT id::text FROM panestria.goal_contract WHERE goal_id=%s", (goal_id,)
                ).fetchone()
                assert contract_row
                task_id = str(uuid4())
                c.execute(
                    "INSERT INTO panestria.task(id,goal_id,contract_id,name,state) VALUES (%s,%s,%s,'Claude "
                    "calculator','READY')",
                    (task_id, goal_id, contract_row[0]),
                )
                contract = load_contract(document)
                for check in contract.acceptance:
                    c.execute(
                        "INSERT INTO panestria.acceptance_check(id,contract_id,check_key,description,required,"
                        "verifier_type,verifier_spec) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)",
                        (
                            str(uuid4()),
                            contract_row[0],
                            check.id,
                            check.description,
                            check.required,
                            check.verifier.type,
                            check.verifier.model_dump_json(),
                        ),
                    )
                c.execute("UPDATE panestria.goal SET status='ACTIVE' WHERE id=%s", (goal_id,))
                append_event(
                    uow,
                    goal_id=goal_id,
                    task_id=task_id,
                    kind="demo.started",
                    actor=self.actor.owner_id,
                    payload={"profile": PROFILE, "prompt_sha256": PROMPT_SHA256},
                )
            cancel = threading.Event()
            thread = threading.Thread(target=self._run, args=(goal_id, task_id, cancel), daemon=True)
            with self._mutex:
                self._jobs[goal_id], self._cancels[goal_id] = thread, cancel
            thread.start()
            return True

    def _permit(self, c: psycopg.Connection[Any], policy_ref: str, action: Action, digest: str) -> PolicyContext:
        policy = PolicyService(self.certificates).get(UnitOfWork(c), self.actor)
        if f"project-policy:{policy.version}:{policy.sha256()}" != policy_ref:
            raise DemoUnavailable("policy_changed")
        decision = PolicyEngine().authorize(
            PolicyRequest(
                owner_id=self.actor.owner_id,
                project_id=self.actor.project_id,
                action=action,
                label="PUBLIC",
                destination="claude-subscription" if action == "external-send" else "local",
                effect_digest=digest,
            ),
            policy,
        )
        if decision.outcome != "PERMIT":
            raise DemoUnavailable("policy_denied")
        return policy

    def _run(self, goal: str, task: str, cancel: threading.Event) -> None:
        heartbeat_stop = threading.Event()
        heartbeat: threading.Thread | None = None
        pending: tuple[InvocationBinding, str] | None = None
        try:
            with self.connect() as c:
                row = c.execute(
                    "SELECT c.id::text,c.body FROM panestria.task t JOIN panestria.goal_contract c ON "
                    "c.id=t.contract_id WHERE t.id=%s",
                    (task,),
                ).fetchone()
                assert row
                cid, contract = str(row[0]), load_contract(row[1])
                self._permit(c, contract.autonomy_profile_ref, "external-send", PROMPT_SHA256)
                lease = LeaseService().acquire(UnitOfWork(c), self.actor, task, PROFILE, 0, ttl_seconds=30)
            scope = ToolScope(
                owner_id=UUID(self.actor.owner_id),
                project_id=UUID(self.actor.project_id),
                task_id=UUID(task),
                attempt_id=UUID(lease.attempt_id),
                lease_epoch=lease.epoch,
                contract_sha256=contract_sha256(contract),
                policy_ref=contract.autonomy_profile_ref,
            )

            def renew() -> None:
                deadline = time.monotonic() + 240
                while not heartbeat_stop.wait(2):
                    try:
                        if time.monotonic() >= deadline:
                            raise DemoUnavailable("demo_deadline")
                        with self.connect() as c:
                            self._permit(c, contract.autonomy_profile_ref, "external-send", PROMPT_SHA256)
                            LeaseService().heartbeat(
                                UnitOfWork(c), self.actor, lease.attempt_id, lease.epoch, ttl_seconds=30
                            )
                    except Exception:
                        cancel.set()
                        return

            heartbeat = threading.Thread(target=renew, daemon=True)
            heartbeat.start()
            binding = InvocationBinding(
                scope=scope,
                kind="native-proposal",
                request_sha256=PROMPT_SHA256,
                configuration_sha256=canonical_sha256(runtime_versions()),
            )
            with self.connect() as c:
                identity = InvocationService().prepare(UnitOfWork(c), self.actor, binding, "native-proposal")
            with self.connect() as c:
                self._permit(c, contract.autonomy_profile_ref, "external-send", PROMPT_SHA256)
                InvocationService().claim(UnitOfWork(c), self.actor, binding, identity)
            pending = binding, identity
            native = self.adapter.propose(cancel=cancel)
            digest = self.store.write_report(
                json.dumps(
                    {
                        "status": native.status,
                        "reason": native.reason,
                        "process": asdict(native.process),
                        "proposal": None if native.proposal is None else native.proposal.model_dump(),
                    },
                    sort_keys=True,
                ).encode()
            )
            with self.connect() as c:
                InvocationService().finish(UnitOfWork(c), self.actor, binding, identity, digest)
            pending = None
            if native.status != "CANDIDATE" or native.proposal is None:
                raise DemoUnavailable(native.reason)
            work_root = _private(self.root / "attempts")
            workspace = work_root / lease.attempt_id
            workspace.mkdir(mode=0o700)
            (workspace / "calculator.py").write_text(BASE_SOURCE)
            request, permit, commands = self._tool(native.proposal, workspace, scope)
            binding = tool_binding(permit)
            with self.connect() as c:
                self._permit(c, contract.autonomy_profile_ref, "edit", request.sha256())
                identity = InvocationService().prepare(UnitOfWork(c), self.actor, binding, "apply-calculator")
            pending = binding, identity
            receipt = NativeToolGateway(
                work_root, commands, DurableToolAuthority(self.connect, self.actor, identity)
            ).execute(request, permit, cancel=cancel)
            digest = self.store.write_report(
                json.dumps(
                    asdict(receipt),
                    sort_keys=True,
                    default=lambda value: hashlib.sha256(value).hexdigest() if isinstance(value, bytes) else str(value),
                ).encode()
            )
            with self.connect() as c:
                InvocationService().finish(UnitOfWork(c), self.actor, binding, identity, digest)
            pending = None
            if (
                receipt.outcome != "completed"
                or receipt.sandbox is None
                or receipt.sandbox.exit_code != 0
                or cancel.is_set()
            ):
                raise DemoUnavailable("candidate_apply_not_confirmed")
            # No candidate .git or hooks: Git metadata is owned by the controller.
            if (
                set(p.name for p in workspace.iterdir()) != {"calculator.py"}
                or (workspace / "calculator.py").is_symlink()
            ):
                raise DemoUnavailable("candidate_path_mismatch")
            checked = CodeProposal(path="calculator.py", content=(workspace / "calculator.py").read_text())
            with tempfile.TemporaryDirectory(dir=self.root, prefix="git-candidate-") as directory:
                source = Path(directory)
                _git(source, "clone", str(self.bare), ".")
                base = _git(source, "rev-parse", "HEAD")
                _git(source, "config", "user.name", "Panestria synthetic demo")
                _git(source, "config", "user.email", "demo@panestria.invalid")
                (source / "calculator.py").write_text(checked.content)
                _git(source, "add", "calculator.py")
                _git(source, "commit", "-m", "fix(demo): propose Claude calculator repair")
                candidate = _git(source, "rev-parse", "HEAD")
                _git(source, "push", "origin", f"HEAD:refs/heads/candidate/{lease.attempt_id}")
            snapshot = materialize(self.bare, base, candidate, self.root / "snapshots" / lease.attempt_id)
            if cancel.is_set():
                raise DemoUnavailable("cancelled_before_verification")
            with self.connect() as c:
                policy = self._permit(c, contract.autonomy_profile_ref, "read", contract_sha256(contract))
                ids = dict(
                    c.execute(
                        "SELECT check_key,id::text FROM panestria.acceptance_check WHERE contract_id=%s", (cid,)
                    ).fetchall()
                )
            verified = verify_build(
                contract,
                cid,
                task,
                lease.attempt_id,
                lease.epoch,
                base,
                candidate,
                snapshot,
                ids,
                self.registry,
                policy=policy,
            )
            for report in verified.reports:
                self.store.write_report(report)
            if cancel.is_set():
                raise DemoUnavailable("cancelled_before_publication")
            # Stop renewal before verifier publication marks this lease succeeded.
            heartbeat_stop.set()
            heartbeat.join(timeout=5)
            with self.connect() as c:
                digest = self.evidence.publish(UnitOfWork(c), self.actor, verified.bundle)
            if verified.bundle.passed():
                with self.connect() as c:
                    self.evidence.request_merge(
                        UnitOfWork(c), self.actor, task, digest, "refs/heads/main", ttl_seconds=3600
                    )
            else:
                self._failed(goal, task, "independent_checks_failed")
        except Exception as exc:
            if pending:
                try:
                    with self.connect() as c:
                        InvocationService().finish(UnitOfWork(c), self.actor, pending[0], pending[1], None)
                except Exception:
                    pass  # PREPARED/CLAIMED stays fenced after any unknown failure.
            reason = (
                str(exc)
                if isinstance(exc, (DemoUnavailable, ProposalUnavailable, KernelDenied))
                else "demo_execution_failed"
            )
            self._failed(goal, task, reason)
        finally:
            heartbeat_stop.set()
            if heartbeat:
                heartbeat.join(timeout=5)

    def _failed(self, goal: str, task: str, reason: str) -> None:
        with self.connect() as c:
            # Match cancellation's goal -> task -> attempt order. The goal lock
            # permits FK key-share checks by workers recording historical events.
            current = c.execute(
                "SELECT status FROM panestria.goal WHERE id=%s AND owner_id=%s AND project_id=%s FOR NO KEY UPDATE",
                (goal, self.actor.owner_id, self.actor.project_id),
            ).fetchone()
            if current is None or current[0] == "COMPLETED":
                return
            if (
                c.execute(
                    "SELECT id FROM panestria.task WHERE id=%s AND goal_id=%s FOR UPDATE", (task, goal)
                ).fetchone()
                is None
            ):
                raise KernelDenied("not_found")
            c.execute(
                "UPDATE panestria.task_attempt SET "
                "status='FAILED',error_code=%s,finished_at=clock_timestamp() WHERE task_id=%s AND "
                "status='RUNNING'",
                (reason[:128], task),
            )
            c.execute(
                "UPDATE panestria.task SET state='FAILED',row_version=row_version+1 WHERE id=%s AND "
                "state NOT IN ('CANCELLED','CANCELLING','COMPLETED')",
                (task,),
            )
            c.execute(
                "UPDATE panestria.goal SET status='FAILED' WHERE id=%s AND status NOT IN ('CANCELLED','COMPLETED')",
                (goal,),
            )
            append_event(
                UnitOfWork(c),
                goal_id=goal,
                task_id=task,
                kind="demo.stopped",
                actor=self.actor.owner_id,
                payload={"reason": reason[:128]},
            )

    def decide(
        self,
        goal: str,
        approval_id: str,
        digest: str,
        version: int,
        decision: str,
        key: str,
        *,
        authorize: Callable[[psycopg.Connection[Any]], None] | None = None,
    ) -> None:
        with self.connect() as c:
            if authorize:
                authorize(c)
            self._goal(c, goal)
            view = ApprovalService().preview(UnitOfWork(c), self.actor, approval_id)
            task = str(view.preview["task_id"])
            found = c.execute("SELECT goal_id::text FROM panestria.task WHERE id=%s", (task,)).fetchone()
            if found != (goal,):
                raise KernelDenied("not_found")
            ApprovalService().decide(UnitOfWork(c), self.actor, approval_id, digest, version, decision, key)
        if decision == "deny":
            self._failed(goal, task, "owner_denied_merge")
            return
        with self.connect() as c:
            effect = prepare_merge(UnitOfWork(c), self.actor, approval_id)
        target = VerifiedGitTarget(
            self.protected, self.bare, self.connect, self.actor, self.evidence, self.registry, self.certificates
        )
        if effect.state == "PREPARED":
            EffectExecutor(self.connect, target).dispatch(self.actor, effect.effect_id)
        elif effect.state != "SUCCEEDED":
            raise DemoUnavailable("recorded_merge_requires_reconciliation")
        with self.connect() as c:
            self._completion_lock(c, goal)
            self.evidence.complete_confirmed(
                UnitOfWork(c), self.actor, task, str(view.preview["candidate_sha256"]), effect.effect_id
            )
            c.execute("UPDATE panestria.goal SET status='COMPLETED' WHERE id=%s", (goal,))
            append_event(
                UnitOfWork(c),
                goal_id=goal,
                task_id=task,
                kind="goal.completed",
                actor=self.actor.owner_id,
                payload={"effect_id": effect.effect_id},
            )

    def _goal(self, c: psycopg.Connection[Any], goal: str) -> None:
        GoalService().get(UnitOfWork(c), self.actor, goal)
        if goal == self.identity["setup_goal"]:
            raise KernelDenied("not_found")

    def _completion_lock(self, c: psycopg.Connection[Any], goal: str) -> None:
        row = c.execute(
            "SELECT id FROM panestria.goal WHERE id=%s AND owner_id=%s AND project_id=%s FOR NO KEY UPDATE",
            (goal, self.actor.owner_id, self.actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")

    def reconcile(self, goal: str) -> None:
        with self.connect() as c:
            self._goal(c, goal)
            row = c.execute(
                "SELECT e.id::text,e.task_id::text,a.preview,e.state FROM panestria.side_effect e "
                "JOIN panestria.approval_request a ON a.id=e.approval_request_id "
                "JOIN panestria.task t ON t.id=e.task_id WHERE t.goal_id=%s",
                (goal,),
            ).fetchone()
            if row is None:
                raise DemoUnavailable("no_recorded_merge")
            effect, task, preview, state = row
        target = VerifiedGitTarget(
            self.protected, self.bare, self.connect, self.actor, self.evidence, self.registry, self.certificates
        )
        executor = EffectExecutor(self.connect, target)
        if state != "SUCCEEDED":
            executor.reconcile(self.actor, str(effect))
        with self.connect() as c:
            self._completion_lock(c, goal)
            self.evidence.complete_confirmed(
                UnitOfWork(c), self.actor, str(task), str(preview["candidate_sha256"]), str(effect)
            )
            c.execute("UPDATE panestria.goal SET status='COMPLETED' WHERE id=%s", (goal,))
            append_event(
                UnitOfWork(c),
                goal_id=goal,
                task_id=str(task),
                kind="goal.completed",
                actor=self.actor.owner_id,
                payload={"effect_id": str(effect), "reconciled": True},
            )

    def cancel(
        self, goal: str, version: int, *, authorize: Callable[[psycopg.Connection[Any]], None] | None = None
    ) -> None:
        with self.connect() as c:
            if authorize:
                authorize(c)
            self._goal(c, goal)
            CancellationService().cancel(
                UnitOfWork(c), self.actor, goal, version, "owner-demo-cancel", correlation_id=str(uuid4())
            )
        with self._mutex:
            signal = self._cancels.get(goal)
            if signal:
                signal.set()

    def view(self, goal: str | None = None) -> dict[str, Any]:
        state = self.readiness()
        with self.connect() as c:
            if goal is None:
                row = c.execute(
                    "SELECT id::text FROM panestria.goal WHERE owner_id=%s AND project_id=%s AND id!=%s "
                    "ORDER BY created_at DESC LIMIT 1",
                    (self.actor.owner_id, self.actor.project_id, self.identity["setup_goal"]),
                ).fetchone()
                if row is None:
                    return {**state, "goal": None}
                goal = str(row[0])
            self._goal(c, goal)
            task = c.execute(
                "SELECT t.id::text,t.state,t.row_version,g.status FROM panestria.task t JOIN "
                "panestria.goal g ON g.id=t.goal_id WHERE t.goal_id=%s",
                (goal,),
            ).fetchone()
            assert task
            state["goal"] = {"id": goal, "task_id": task[0], "state": task[1], "version": task[2], "status": task[3]}
            state["events"] = [
                {"seq": seq, "kind": kind, "payload": body}
                for seq, kind, body in GoalService().events(UnitOfWork(c), self.actor, goal, 0, 200)
            ]
            bundle = c.execute(
                "SELECT sha256,body FROM panestria.build_evidence WHERE task_id=%s ORDER BY created_at DESC LIMIT 1",
                (task[0],),
            ).fetchone()
            state["evidence"] = None
            state["approval"] = None
            state["diff"] = ""
            if bundle:
                verified = self.store.read(str(bundle[0]).strip())
                state["evidence"] = {
                    "sha256": verified.sha256(),
                    "candidate_commit": verified.candidate_commit,
                    "base_commit": verified.base_commit,
                    "checks": [json.loads(self.store.read_blob(check.report_sha256)) for check in verified.checks],
                }
                candidate = _git(self.bare, "show", f"{verified.candidate_commit}:calculator.py") + "\n"
                state["diff"] = "".join(
                    difflib.unified_diff(
                        BASE_SOURCE.splitlines(True),
                        candidate.splitlines(True),
                        fromfile="base/calculator.py",
                        tofile="candidate/calculator.py",
                    )
                )
                pending = c.execute(
                    "SELECT id::text FROM panestria.approval_request a WHERE task_id=%s "
                    "AND state IN ('PENDING','APPROVED') AND expires_at>clock_timestamp() "
                    "AND NOT EXISTS (SELECT 1 FROM panestria.side_effect e WHERE e.approval_request_id=a.id)",
                    (task[0],),
                ).fetchone()
                if pending:
                    view = ApprovalService().preview(UnitOfWork(c), self.actor, str(pending[0]))
                    state["approval"] = {
                        "id": view.approval_id,
                        "effect_digest": view.effect_digest,
                        "version": view.expected_version,
                        "preview": view.preview,
                    }
            return state

    def recover(self) -> None:
        # A process restart records interruption; it never relaunches inference,
        # writes, or a possibly dispatched merge. Pending owner review survives.
        with self.connect() as c:
            rows = c.execute(
                "SELECT t.id::text,t.goal_id::text FROM panestria.task t JOIN panestria.goal g ON "
                "g.id=t.goal_id WHERE g.project_id=%s AND t.id!=%s "
                "AND (t.state IN ('READY','RUNNING','LEASED') OR (t.state='VERIFYING' "
                "AND NOT EXISTS (SELECT 1 FROM panestria.side_effect e WHERE e.task_id=t.id)))",
                (self.actor.project_id, self.identity["setup_task"]),
            ).fetchall()
        for task, goal in rows:
            self._failed(str(goal), str(task), "controller_interrupted_no_automatic_replay")

    def close(self) -> None:
        with self._mutex:
            for signal in self._cancels.values():
                signal.set()
            jobs = list(self._jobs.values())
        for job in jobs:
            job.join(timeout=5)
