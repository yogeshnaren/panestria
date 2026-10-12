"""Evaluate each acceptance node from its own specification."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from panestria.contracts.acceptance import (
    ArtifactExists,
    GitDiffPathCheck,
    HumanReview,
    PolicyDecision,
    TrustedCommandRef,
)
from panestria.contracts.goal import GoalContract, contract_sha256
from panestria.verification.diff import inspect_diff
from panestria.verification.policy import decide_action
from panestria.verification.registry import CommandRegistry
from panestria.verification.runner import TrustedCheckRunner


@dataclass(frozen=True)
class ArtifactFact:
    artifact_ref: str
    sha256: str


@dataclass(frozen=True)
class ReviewFact:
    reviewer_ref: str
    evidence_requirements: tuple[str, ...]


@dataclass(frozen=True)
class NodeReport:
    check_id: str
    verifier_type: str
    required: bool
    verdict: str
    reason: str
    candidate_sha256: str
    base_sha: str
    attempt_id: str
    contract_sha256: str
    output_sha256: str = ""
    denied_paths: tuple[str, ...] = ()
    tree_sha: str = ""

    def canonical_bytes(self) -> bytes:
        payload = {
            "attempt_id": self.attempt_id,
            "base_sha": self.base_sha,
            "candidate_sha256": self.candidate_sha256,
            "check_id": self.check_id,
            "contract_sha256": self.contract_sha256,
            "denied_paths": list(self.denied_paths),
            "output_sha256": self.output_sha256,
            "reason": self.reason,
            "required": self.required,
            "tree_sha": self.tree_sha,
            "verdict": self.verdict,
            "verifier_type": self.verifier_type,
        }
        return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()


def evaluate_checks(
    contract: GoalContract,
    *,
    root: Path,
    worktree: Path,
    base_sha: str,
    registry: CommandRegistry,
    runner: TrustedCheckRunner,
    attempt_id: str,
    candidate_sha256: str,
    candidate_path: Path,
    artifacts: tuple[ArtifactFact, ...] = (),
    reviews: tuple[ReviewFact, ...] = (),
) -> tuple[NodeReport, ...]:
    digest = contract_sha256(contract)
    reports: list[NodeReport] = []
    for check in contract.acceptance:
        spec = check.verifier
        if isinstance(spec, TrustedCommandRef):
            report = _command(
                check.id,
                check.required,
                spec,
                runner,
                candidate_path,
                candidate_sha256,
                base_sha,
                attempt_id,
                digest,
            )
        elif isinstance(spec, GitDiffPathCheck):
            report = _diff(
                check.id,
                check.required,
                spec,
                contract,
                root,
                worktree,
                base_sha,
                candidate_sha256,
                attempt_id,
                digest,
            )
        elif isinstance(spec, PolicyDecision):
            report = _policy(
                check.id,
                check.required,
                spec,
                contract,
                candidate_sha256,
                base_sha,
                attempt_id,
                digest,
            )
        elif isinstance(spec, ArtifactExists):
            report = _artifact(
                check.id,
                check.required,
                spec,
                artifacts,
                candidate_sha256,
                base_sha,
                attempt_id,
                digest,
            )
        elif isinstance(spec, HumanReview):
            report = _review(
                check.id,
                check.required,
                spec,
                reviews,
                candidate_sha256,
                base_sha,
                attempt_id,
                digest,
            )
        else:
            report = _report(
                check.id,
                spec.type,
                check.required,
                "ERROR",
                "runner_not_admitted",
                candidate_sha256,
                base_sha,
                attempt_id,
                digest,
            )
        reports.append(report)
    return tuple(reports)


def required_passed(reports: tuple[NodeReport, ...]) -> bool:
    required = [item for item in reports if item.required]
    return bool(required) and all(item.verdict == "PASS" for item in required)


def _command(
    check_id: str,
    required: bool,
    spec: TrustedCommandRef,
    runner: TrustedCheckRunner,
    candidate_path: Path,
    candidate_sha256: str,
    base_sha: str,
    attempt_id: str,
    digest: str,
) -> NodeReport:
    try:
        runner.registry.resolve(spec.command_ref)
    except KeyError:
        return _report(
            check_id,
            spec.type,
            required,
            "FAIL",
            "unknown_command",
            candidate_sha256,
            base_sha,
            attempt_id,
            digest,
        )
    if spec.timeout_seconds > 3600:
        return _report(
            check_id,
            spec.type,
            required,
            "FAIL",
            "deadline",
            candidate_sha256,
            base_sha,
            attempt_id,
            digest,
        )
    result = runner.run(
        spec.command_ref,
        candidate_path,
        float(spec.timeout_seconds),
        expected_exit_code=spec.expected_exit_code,
    )
    return _report(
        check_id,
        spec.type,
        required,
        result.verdict,
        result.reason,
        candidate_sha256,
        base_sha,
        attempt_id,
        digest,
        result.output_sha256,
    )


def _diff(
    check_id: str,
    required: bool,
    spec: GitDiffPathCheck,
    contract: GoalContract,
    root: Path,
    worktree: Path,
    base_sha: str,
    candidate_sha256: str,
    attempt_id: str,
    digest: str,
) -> NodeReport:
    report = inspect_diff(
        root,
        worktree,
        frozenset(spec.allowed_paths),
        base_sha=base_sha,
        forbidden=frozenset([*spec.forbidden_paths, *contract.constraints.forbidden_paths]),
        also_allowed=frozenset(contract.constraints.allowed_paths),
    )
    verdict = "PASS" if report.ok else "FAIL"
    reason = "paths" if report.ok else "path_denied"
    return _report(
        check_id,
        spec.type,
        required,
        verdict,
        reason,
        candidate_sha256,
        report.base_sha or base_sha,
        attempt_id,
        digest,
        hashlib.sha256(report.candidate_tree.encode()).hexdigest() if report.candidate_tree else "",
        report.denied,
        report.candidate_tree,
    )


def _policy(
    check_id: str,
    required: bool,
    spec: PolicyDecision,
    contract: GoalContract,
    candidate_sha256: str,
    base_sha: str,
    attempt_id: str,
    digest: str,
) -> NodeReport:
    decision = decide_action(contract.autonomy_profile_ref, spec.action)
    if decision is None:
        verdict, reason = "FAIL", "unknown_action"
    elif decision != spec.expected:
        verdict, reason = "FAIL", "policy_mismatch"
    else:
        verdict, reason = "PASS", decision
    return _report(check_id, spec.type, required, verdict, reason, candidate_sha256, base_sha, attempt_id, digest)


def _artifact(
    check_id: str,
    required: bool,
    spec: ArtifactExists,
    artifacts: tuple[ArtifactFact, ...],
    candidate_sha256: str,
    base_sha: str,
    attempt_id: str,
    digest: str,
) -> NodeReport:
    found = any(item.artifact_ref == spec.artifact_ref and item.sha256 == spec.expected_sha256 for item in artifacts)
    verdict, reason = ("PASS", "present") if found else ("FAIL", "missing_artifact")
    return _report(check_id, spec.type, required, verdict, reason, candidate_sha256, base_sha, attempt_id, digest)


def _review(
    check_id: str,
    required: bool,
    spec: HumanReview,
    reviews: tuple[ReviewFact, ...],
    candidate_sha256: str,
    base_sha: str,
    attempt_id: str,
    digest: str,
) -> NodeReport:
    needed = set(spec.evidence_requirements)
    found = any(
        item.reviewer_ref == spec.reviewer_ref and needed.issubset(set(item.evidence_requirements)) for item in reviews
    )
    verdict, reason = ("PASS", "recorded") if found else ("FAIL", "missing_review")
    return _report(check_id, spec.type, required, verdict, reason, candidate_sha256, base_sha, attempt_id, digest)


def _report(
    check_id: str,
    verifier_type: str,
    required: bool,
    verdict: str,
    reason: str,
    candidate_sha256: str,
    base_sha: str,
    attempt_id: str,
    digest: str,
    output_sha256: str = "",
    denied_paths: tuple[str, ...] = (),
    tree_sha: str = "",
) -> NodeReport:
    return NodeReport(
        check_id,
        verifier_type,
        required,
        verdict,
        reason,
        candidate_sha256,
        base_sha,
        attempt_id,
        digest,
        output_sha256,
        denied_paths,
        tree_sha,
    )
