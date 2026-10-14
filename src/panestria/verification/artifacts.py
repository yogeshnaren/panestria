"""Bind a diff and the required check set. The worker's own done flag is not a verdict."""

from __future__ import annotations

from dataclasses import dataclass

from panestria.verification.diff import DiffReport
from panestria.verification.runner import CheckResult


@dataclass(frozen=True)
class VerificationDecision:
    verdict: str
    reason: str


def decide(
    diff: DiffReport,
    results: tuple[CheckResult, ...],
    required: tuple[str, ...],
    worker_claims_done: bool,
) -> VerificationDecision:
    if not diff.ok:
        return VerificationDecision("FAIL", "diff")
    observed = {result.ref: result.verdict for result in results}
    independent = bool(required) and set(observed) == set(required) and all(observed[ref] == "PASS" for ref in required)
    if worker_claims_done and not independent:
        return VerificationDecision("FAIL", "checks")
    if not independent:
        return VerificationDecision("FAIL", "checks")
    return VerificationDecision("PASS", "independent")
