"""The controller, not a worker report, invokes an independent verifier on a frozen tree."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from panestria.contracts.acceptance import GitDiffPathCheck, PolicyDecision, TrustedCommandRef
from panestria.contracts.build import BuildCheck, BuildEvidenceBundle, canonical_sha256
from panestria.contracts.goal import GoalContract, contract_sha256
from panestria.contracts.plan import PlanTaskScope
from panestria.contracts.policy import Action, PolicyContext, PolicyRequest
from panestria.policy.engine import PolicyEngine
from panestria.verification.git_snapshot import GitSnapshot, verify_snapshot
from panestria.verification.paths import path_permitted
from panestria.verification.registry import CommandRegistry
from panestria.verification.sandboxed import SandboxedCheckRunner


@dataclass(frozen=True)
class VerifiedBuild:
    bundle: BuildEvidenceBundle
    reports: tuple[bytes, ...]


def verify_build(
    contract: GoalContract,
    contract_id: str,
    task_id: str,
    attempt_id: str,
    epoch: int,
    base: str,
    candidate: str,
    snapshot: GitSnapshot,
    check_ids: dict[str, str],
    registry: CommandRegistry,
    *,
    policy: PolicyContext | None = None,
    deadline: float | None = None,
    plan_scope: PlanTaskScope | None = None,
    before_check: Callable[[], None] | None = None,
) -> VerifiedBuild:
    verify_snapshot(snapshot)
    runner = SandboxedCheckRunner(registry, snapshot.directory.parent)
    verdict: Literal["PASS", "FAIL", "UNKNOWN", "ERROR"]
    observed = []
    reports = []
    bundle_digest = verifier_bundle_digest(contract, registry)
    if plan_scope is not None:
        plan_scope = PlanTaskScope.model_validate(plan_scope)
        if plan_scope.node.task_id != task_id or set(plan_scope.node.acceptance_keys) - {
            c.id for c in contract.acceptance
        }:
            raise ValueError("plan_verification_scope_invalid")
    denied_paths = plan_scope is not None and any(path not in plan_scope.node.paths for path in snapshot.changed_paths)
    for check in sorted(contract.acceptance, key=lambda check: check.id):
        if plan_scope is not None and check.id not in plan_scope.node.acceptance_keys:
            continue
        if before_check is not None:
            before_check()
        spec = check.verifier
        if denied_paths:
            verdict, reason, output_digest = "FAIL", "plan_path_denied", ""
        elif isinstance(spec, TrustedCommandRef):
            try:
                registry.resolve(spec.command_ref)
            except KeyError:
                verdict, reason, output_digest = "FAIL", "unregistered_command", hashlib.sha256(b"").hexdigest()
            else:
                remaining = float(spec.timeout_seconds)
                if deadline is not None:
                    remaining = min(remaining, max(0.0, deadline - time.monotonic()))
                result = runner.run(
                    spec.command_ref,
                    snapshot.directory,
                    remaining,
                    expected_exit_code=spec.expected_exit_code,
                )
                verdict, reason, output_digest = (
                    "PASS" if result.verdict == "PASS" else "FAIL",
                    result.reason,
                    result.output_sha256 or hashlib.sha256(b"").hexdigest(),
                )
        elif isinstance(spec, GitDiffPathCheck):
            denied = any(
                not path_permitted(
                    path,
                    frozenset(spec.allowed_paths),
                    frozenset([*spec.forbidden_paths, *contract.constraints.forbidden_paths]),
                    also_allowed=frozenset(contract.constraints.allowed_paths),
                )
                for path in snapshot.changed_paths
            )
            passed = bool(snapshot.changed_paths) and not denied
            verdict, reason, output_digest = ("PASS", "paths", "") if passed else ("FAIL", "path_denied", "")
        elif isinstance(spec, PolicyDecision):
            aliases: dict[str, Action] = {"protected-merge": "merge", "scoped-file-edit": "edit", "read-local": "read"}
            action = aliases.get(spec.action)
            ref = None if policy is None else f"project-policy:{policy.version}:{policy.sha256()}"
            if policy is None or action is None or ref != contract.autonomy_profile_ref:
                verdict, reason, output_digest = "UNKNOWN", "policy_unavailable", ""
            else:
                request = PolicyRequest(
                    owner_id=contract.owner_id,
                    project_id=contract.project_id,
                    action=action,
                    label="RESTRICTED",
                    destination="local",
                    effect_digest=contract_sha256(contract),
                )
                decision = PolicyEngine().authorize(request, policy)
                outcome = {"PERMIT": "allow", "DENY": "deny", "APPROVAL_NEEDED": "approval-required"}[decision.outcome]
                verdict = "PASS" if outcome == spec.expected else "FAIL"
                reason, output_digest = "policy_" + outcome, decision.request_sha256
        else:
            # Unsupported checks remain explicit failures, never silently omitted.
            verdict, reason, output_digest = "UNKNOWN", "runner_not_available", ""
        report = json.dumps(
            {
                "schema_version": 1,
                "contract_sha256": contract_sha256(contract),
                "spec_sha256": canonical_sha256(spec.model_dump(mode="json")),
                "verifier_bundle_sha256": bundle_digest,
                "check_key": check.id,
                "verdict": verdict,
                "reason": reason,
                "candidate_commit": candidate,
                "candidate_tree": snapshot.tree,
                "base_commit": base,
                "snapshot_sha256": snapshot.manifest_sha256,
                "output_sha256": output_digest,
                "attempt_id": attempt_id,
                "lease_epoch": epoch,
                **({"plan_scope_sha256": plan_scope.sha256()} if plan_scope else {}),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        reports.append(report)
        observed.append(
            BuildCheck(
                check_id=check_ids[check.id],
                check_key=check.id,
                required=check.required,
                spec_sha256=canonical_sha256(spec.model_dump(mode="json")),
                verdict=verdict,
                report_sha256=hashlib.sha256(report).hexdigest(),
            )
        )
    bundle = BuildEvidenceBundle(
        owner_id=contract.owner_id,
        project_id=contract.project_id,
        task_id=task_id,
        attempt_id=attempt_id,
        lease_epoch=epoch,
        contract_id=contract_id,
        contract_sha256=contract_sha256(contract),
        contract_version=contract.contract_version,
        policy_ref=contract.autonomy_profile_ref,
        base_commit=base,
        candidate_commit=candidate,
        candidate_tree=snapshot.tree,
        snapshot_sha256=snapshot.manifest_sha256,
        verifier_bundle_sha256=bundle_digest,
        checks=tuple(observed),
    )
    verify_snapshot(snapshot)
    return VerifiedBuild(bundle, tuple(reports))


def verifier_bundle_digest(contract: GoalContract, registry: CommandRegistry, *, recheck: bool = False) -> str:
    commands = []
    for check in sorted(contract.acceptance, key=lambda check: check.id):
        if not isinstance(check.verifier, TrustedCommandRef):
            continue
        try:
            command = registry.resolve(check.verifier.command_ref)
        except KeyError:
            continue
        if recheck:
            from pathlib import Path

            path = Path(command.argv[-1])
            if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != command.script_sha256:
                raise ValueError("verifier_bundle_changed")
        commands.append({"ref": command.ref, "script_sha256": command.script_sha256})
    return canonical_sha256(commands)
