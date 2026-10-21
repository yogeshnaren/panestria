"""Consistent progress projection over canonical plans, tasks and protected evidence.

No second task store, worker narrative, heartbeat-based success or state mutation.
The caller supplies a repeatable-read transaction and privately retains exports.
"""

from collections import Counter
from datetime import UTC
from typing import Literal

from panestria.contracts.build import canonical_sha256
from panestria.contracts.goal import contract_sha256
from panestria.contracts.plan import PlanRevisionConsent
from panestria.contracts.progress import (
    BuildProgress,
    MilestoneProgress,
    NonGoalProgress,
    PlanProgress,
    RepairProgress,
    RequirementProgress,
)
from panestria.kernel.build import BuildEvidenceService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.plan_store import PlanStore
from panestria.kernel.repair_intents import repair_ledger
from panestria.kernel.uow import UnitOfWork


class BuildProgressService:
    def inspect(
        self, uow: UnitOfWork, actor: Actor, goal_id: str, evidence: BuildEvidenceService, *, public_only: bool = False
    ) -> BuildProgress:
        if uow.execute("SHOW transaction_isolation").fetchone() != ("repeatable read",):
            raise KernelDenied("progress_consistent_transaction_required")
        store = PlanStore()
        status, _, contract = store._goal(uow, actor, goal_id, read_only=True)
        if public_only and contract.privacy_class != "PUBLIC":
            raise KernelDenied("public_build_progress_required")
        observed = uow.execute("SELECT transaction_timestamp()").fetchone()
        event = uow.execute(
            "SELECT COALESCE(max(seq),0) FROM panestria.task_event WHERE goal_id=%s", (goal_id,)
        ).fetchone()
        assert observed is not None and event is not None
        rows = uow.execute(
            "SELECT id::text FROM panestria.build_plan WHERE goal_id=%s ORDER BY version", (goal_id,)
        ).fetchall()
        if not rows:
            raise KernelDenied("plan_not_found")
        # Revalidate immutable plan/consent/membership against current authority.
        plans = [store.get(uow, actor, row[0]) for row in rows]
        accepted = [p for p in plans if p.state == "ACCEPTED"]
        current = accepted[-1] if accepted else None
        final_bundle = None
        final_digest = None
        final_unconfirmed = False
        summaries = []
        fingerprints: Counter[str] = Counter()
        for plan in plans:
            milestones = []
            dependencies = {d for n in plan.proposal.nodes for d in n.depends_on}
            finals = {n.task_id for n in plan.proposal.nodes} - dependencies
            for node in plan.proposal.nodes:
                if plan.state != "ACCEPTED":
                    continue
                task = uow.execute(
                    "SELECT state,lease_epoch FROM panestria.task WHERE id=%s", (node.task_id,)
                ).fetchone()
                assert task is not None
                result = uow.execute(
                    "SELECT b.sha256 FROM panestria.build_evidence b WHERE b.task_id=%s "
                    "ORDER BY b.created_at DESC,b.sha256 LIMIT 1",
                    (node.task_id,),
                ).fetchone()
                digest = str(result[0]).strip() if result else None
                bundle = None
                reason = None
                if digest:
                    try:
                        bundle = evidence.observed(uow, actor, node.task_id, digest)
                    except KernelDenied as error:
                        reason = error.code
                handoff = uow.execute(
                    "SELECT id::text FROM panestria.build_handoff WHERE task_id=%s ORDER BY created_at DESC LIMIT 1",
                    (node.task_id,),
                ).fetchone()
                handoff_digest = None
                if handoff and bundle and bundle.passed():
                    # Handoff byte refs, current source and task version are
                    # independently rechecked; an old note cannot imply progress.
                    try:
                        retained = store.read_handoff(uow, actor, handoff[0], evidence)
                        handoff_digest = retained.sha256()
                    except KernelDenied:
                        pass
                fingerprint = None
                if bundle and not bundle.passed():
                    fingerprint = canonical_sha256(
                        {
                            "contract_sha256": bundle.contract_sha256,
                            "candidate_tree": bundle.candidate_tree,
                            "verifier_bundle_sha256": bundle.verifier_bundle_sha256,
                            "failed_checks": [
                                (c.check_key, c.spec_sha256, c.verdict)
                                for c in bundle.checks
                                if c.required and c.verdict != "PASS"
                            ],
                        }
                    )
                    fingerprints[fingerprint] += 1
                milestone = MilestoneProgress(
                    task_id=node.task_id,
                    state=task[0],
                    lease_epoch=task[1],
                    evidence_sha256=digest,
                    evidence_status="CONFIRMED" if bundle else ("UNCONFIRMED" if digest else "NOT_RUN"),
                    evidence_reason=reason,
                    candidate_commit=bundle.candidate_commit if bundle else None,
                    checks=tuple((c.check_key, c.verdict) for c in bundle.checks) if bundle else (),
                    handoff_sha256=handoff_digest,
                    failure_fingerprint=fingerprint,
                )
                milestones.append(milestone)
                if current and plan.proposal.plan_id == current.proposal.plan_id and node.task_id in finals:
                    if len(finals) == 1:
                        final_bundle, final_digest = bundle, digest if bundle else None
                        final_unconfirmed = bool(digest and not bundle)
            summaries.append(
                PlanProgress(
                    plan_id=plan.proposal.plan_id,
                    version=plan.version,
                    proposal_sha256=plan.proposal.sha256(),
                    parent_sha256=plan.parent_sha256,
                    inventory_sha256=plan.inventory.sha256(),
                    state=plan.state,
                    milestones=tuple(milestones),
                )
            )
        checks = {c.check_key: c for c in final_bundle.checks} if final_bundle else {}
        requirements = tuple(
            RequirementProgress(
                key=c.id,
                description=c.description,
                required=c.required,
                verifier_type=c.verifier.type,
                verdict=checks[c.id].verdict if c.id in checks else ("UNCONFIRMED" if final_unconfirmed else "NOT_RUN"),
                report_sha256=checks[c.id].report_sha256 if c.id in checks else None,
            )
            for c in contract.acceptance
        )
        claims = uow.execute(
            "SELECT count(*),count(*) FILTER(WHERE a.lease_expires_at<=transaction_timestamp()) "
            "FROM panestria.build_active_worker_claim c JOIN panestria.task t ON t.id=c.task_id "
            "JOIN panestria.task_attempt a ON a.id=c.attempt_id WHERE t.goal_id=%s",
            (goal_id,),
        ).fetchone()
        invocations = uow.execute(
            "SELECT count(*),count(*) FILTER(WHERE i.state='UNKNOWN') "
            "FROM panestria.worker_invocation i JOIN panestria.task t ON t.id=i.task_id "
            "WHERE t.goal_id=%s AND i.state IN ('CLAIMED','UNKNOWN')",
            (goal_id,),
        ).fetchone()
        assert claims is not None and invocations is not None
        planning = repair_ledger(uow, actor, goal_id)
        charged = sum(p.validation.upper_wall_seconds for p in plans) + planning.charged_wall_seconds
        repeated = max(fingerprints.values(), default=0)
        repair = RepairProgress(
            planning_turns_used=len(planning.intents),
            planning_wall_charged_seconds=planning.charged_wall_seconds,
            unconfirmed_planning_turns=planning.unresolved,
            versions_used=plans[-1].version,
            maximum_versions=plans[-1].consent.maximum_versions
            if isinstance(plans[-1].consent, PlanRevisionConsent)
            else None,
            wall_envelope_charged_seconds=charged,
            wall_envelope_remaining_seconds=max(0, contract.budget.max_wall_seconds - charged),
            repeated_failure_count=repeated,
            held_claims=claims[0],
            expired_held_claims=claims[1],
            unconfirmed_invocations=invocations[0],
            unknown_invocations=invocations[1],
        )
        current_milestones = next(
            (p.milestones for p in summaries if current and p.plan_id == current.proposal.plan_id), ()
        )
        states = {m.state for m in current_milestones}
        merge: Literal["NOT_REQUESTED", "PENDING", "CONFIRMED"] = "NOT_REQUESTED"
        reason, action = "NO_VERIFIED_MILESTONE", "inspect_current_plan_and_required_checks"
        confirmed_merge = False
        if final_bundle and final_digest:
            effects = uow.execute(
                "SELECT id::text,external_ref FROM panestria.side_effect WHERE task_id=%s AND state='SUCCEEDED'",
                (final_bundle.task_id,),
            ).fetchall()
            confirmed_merge = any(
                ref == f"git-effect:{identity}:{final_bundle.candidate_commit}:{final_digest}"
                for identity, ref in effects
            )
        if status == "COMPLETED" and final_bundle and final_bundle.passed() and confirmed_merge:
            reason, action, merge = (
                "VERIFIED_BUILD_COMPLETED",
                "review_goal_result_release_acceptance_separate",
                "CONFIRMED",
            )
        elif (
            repair.unconfirmed_planning_turns
            or repair.unknown_invocations
            or repair.expired_held_claims
            or "RECONCILING" in states
        ):
            reason, action = "RECONCILIATION_REQUIRED", "inspect_receipts_keep_uncertain_capacity_held"
        elif status == "COMPLETED":
            reason, action = "COMPLETION_UNCONFIRMED", "inspect_final_evidence_and_exact_confirmed_effect"
        elif plans[-1].state == "PROPOSED":
            reason, action = "OWNER_PLAN_REVIEW_REQUIRED", "inspect_exact_latest_plan_digest"
        elif "FAILED" in states or "CANCELLED" in states or status in {"FAILED", "CANCELLED"}:
            reason, action = "BUILD_STOPPED", "inspect_failure_and_return_proofs_before_any_repair"
            if repeated >= 2:
                reason, action = "REPEATED_UNCHANGED_FAILURE", "stop_and_review_scope_or_approach_no_automatic_retry"
        elif "WAITING_APPROVAL" in states:
            reason, action, merge = (
                "OWNER_MERGE_REVIEW_REQUIRED",
                "review_exact_integrated_candidate_and_checks",
                "PENDING",
            )
        elif "RUNNING" in states or "VERIFYING" in states:
            reason, action = "EXECUTION_ACTIVE", "wait_for_source_bound_verification_activity_is_not_success"
        return BuildProgress(
            owner_id=actor.owner_id,
            project_id=actor.project_id,
            goal_id=goal_id,
            contract_sha256=contract_sha256(contract),
            contract_version=contract.contract_version,
            goal_status=status,
            observed_at=observed[0].astimezone(UTC).isoformat(),
            as_of_event_seq=event[0],
            current_plan_id=current.proposal.plan_id if current else None,
            plans=tuple(summaries),
            requirements=requirements,
            non_goals=tuple(
                NonGoalProgress(key=f"non-goal-{i + 1}", description=text) for i, text in enumerate(contract.non_goals)
            ),
            required_checks_passed=sum(c.required and c.verdict == "PASS" for c in requirements),
            required_checks_total=sum(c.required for c in requirements),
            final_evidence_sha256=final_digest,
            repair=repair,
            attention_reason=reason,
            next_action=action,
            owner_merge=merge,
        )
