"""One explicitly requested local repair draft from canonical stopped work.

This is a proposal prefilter, not PlanRevisionService consent or admission. No
transaction spans generation. Publication rechecks the full observed basis;
unknown physical work and repeated unchanged failures stop before inference.
"""

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import psycopg

from panestria.config_local import read_private
from panestria.config_plan import PlanModelSettings
from panestria.contracts.build import canonical_sha256
from panestria.contracts.goal import GoalContract
from panestria.contracts.inference import InferenceRequest
from panestria.contracts.plan import PlanRevisionConsent, StoredPlan
from panestria.contracts.plan_draft import RepairDraftContext
from panestria.contracts.repair_intent import (
    DRAFT_FILES,
    FINISHED,
    STARTED,
    TURN_WALL_SECONDS,
    RepairIntent,
    RepairOutcome,
)
from panestria.execution.local_plan import LocalBuildPlanner, PlanGenerator
from panestria.execution.owner_build import OwnerBuild
from panestria.execution.proposal_demo import _atomic
from panestria.kernel.build import BuildEvidenceService
from panestria.kernel.build_progress import BuildProgressService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.plan_store import PlanStore
from panestria.kernel.repair_intents import begin_repair, finish_repair, repair_ledger
from panestria.kernel.repositories.policy import lock_project
from panestria.kernel.scheduler import FLEET_LOCK
from panestria.kernel.uow import UnitOfWork


class LocalBuildRepair:
    def __init__(self, owner: OwnerBuild, settings: PlanModelSettings, model: PlanGenerator | None = None):
        if (str(settings.owner_id), str(settings.project_id)) != (owner.actor.owner_id, owner.actor.project_id):
            raise KernelDenied("local_repair_scope_mismatch")
        self.owner = owner
        self.planner = LocalBuildPlanner(settings, model)

    def _basis(
        self, plan_id: str, parent_sha256: str, proof_sha256: str, maximum_versions: int
    ) -> tuple[StoredPlan, GoalContract, RepairDraftContext]:
        with self.owner.connect() as c:
            c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            return self._basis_in(c, plan_id, parent_sha256, proof_sha256, maximum_versions)

    def _basis_in(
        self,
        c: psycopg.Connection[Any],
        plan_id: str,
        parent_sha256: str,
        proof_sha256: str,
        maximum_versions: int,
        *,
        reserve: bool = True,
        own_intent: str | None = None,
    ) -> tuple[StoredPlan, GoalContract, RepairDraftContext]:
        if type(maximum_versions) is not int or not 2 <= maximum_versions <= 3:
            raise KernelDenied("plan_repair_limit_invalid")
        owner = self.owner
        uow, store = UnitOfWork(c), PlanStore()
        parent = store.get(uow, owner.actor, plan_id)
        _, _, contract = store._goal(uow, owner.actor, parent.proposal.goal_id, read_only=True)
        planning = repair_ledger(uow, owner.actor, parent.proposal.goal_id)
        unresolved = [
            i for i in planning.intents if (outcome := planning.outcome(i)) is None or outcome.status == "UNCONFIRMED"
        ]
        if any(i.draft_id != own_intent for i in unresolved):
            raise KernelDenied("repair_draft_prior_unconfirmed")
        if reserve and len(planning.intents) >= maximum_versions - 1:
            raise KernelDenied("repair_model_turn_limit_exhausted")
        progress = BuildProgressService().inspect(
            uow, owner.actor, parent.proposal.goal_id, BuildEvidenceService(owner.reports)
        )
        latest = c.execute(
            "SELECT id::text FROM panestria.build_plan WHERE goal_id=%s ORDER BY version DESC LIMIT 1",
            (parent.proposal.goal_id,),
        ).fetchone()
        if (
            parent.proposal.sha256() != parent_sha256
            or parent.state != "ACCEPTED"
            or latest != (plan_id,)
            or progress.current_plan_id != plan_id
            or progress.goal_status not in {"CREATED", "ACTIVE"}
        ):
            raise KernelDenied("local_repair_parent_not_current_stopped_plan")
        if contract.privacy_class != "PUBLIC" or contract.budget.max_api_usd != "0":
            raise KernelDenied("local_repair_public_zero_cash_required")
        if isinstance(parent.consent, PlanRevisionConsent) and parent.consent.maximum_versions != maximum_versions:
            raise KernelDenied("plan_repair_limit_change_requires_authorization")
        if progress.repair.versions_used >= maximum_versions:
            raise KernelDenied("plan_repair_limit_exhausted")
        remaining = progress.repair.wall_envelope_remaining_seconds - (TURN_WALL_SECONDS if reserve else 0)
        if progress.repair.repeated_failure_count >= 2:
            raise KernelDenied("local_repair_repeated_failure_owner_review_required")
        if remaining < 2:
            raise KernelDenied("plan_repair_budget_exhausted")
        if progress.repair.held_claims or progress.repair.unconfirmed_invocations:
            raise KernelDenied("plan_previous_work_unconfirmed")
        tasks = c.execute("SELECT state FROM panestria.task WHERE goal_id=%s", (parent.proposal.goal_id,)).fetchall()
        safe = {"CREATED", "READY", "RETRY_WAIT", "COMPLETED", "FAILED", "CANCELLED", "REJECTED"}
        if (
            any(r[0] not in safe for r in tasks)
            or c.execute(
                "SELECT 1 FROM panestria.side_effect s JOIN panestria.task t ON t.id=s.task_id "
                "WHERE t.goal_id=%s AND s.state!='PREPARED' LIMIT 1",
                (parent.proposal.goal_id,),
            ).fetchone()
        ):
            raise KernelDenied("plan_previous_work_unconfirmed")
        current = next(p for p in progress.plans if p.plan_id == plan_id)
        if any(m.evidence_status == "UNCONFIRMED" for m in current.milestones):
            raise KernelDenied("local_repair_evidence_unconfirmed")
        failures = tuple(
            (m.task_id, m.state, m.checks, m.failure_fingerprint)
            for m in current.milestones
            if m.state in {"FAILED", "REJECTED", "CANCELLED"}
        )
        if not failures:
            raise KernelDenied("local_repair_stopped_failure_required")
        proof = c.execute(
            "SELECT r.proof,r.proof_sha256,c.plan_id::text FROM panestria.build_claim_release r "
            "JOIN panestria.build_worker_claim c ON c.attempt_id=r.attempt_id "
            "WHERE c.plan_id=%s AND r.reason='VERIFIED_RETURN' AND r.proof_sha256=%s",
            (plan_id, proof_sha256),
        ).fetchone()
        if (
            proof is None
            or canonical_sha256(proof[0]) != str(proof[1]).strip()
            or proof[0].get("plan_id") != plan_id
            or proof[2] != plan_id
        ):
            raise KernelDenied("plan_return_proof_unconfirmed")
        source_seq = c.execute(
            "SELECT COALESCE(max(seq),0) FROM panestria.task_event WHERE goal_id=%s AND kind NOT IN (%s,%s)",
            (parent.proposal.goal_id, STARTED, FINISHED),
        ).fetchone()
        assert source_seq is not None
        context = RepairDraftContext(
            parent_plan_id=plan_id,
            parent_proposal_sha256=parent_sha256,
            return_proof_sha256=proof_sha256,
            parent_version=parent.version,
            maximum_versions=maximum_versions,
            remaining_wall_seconds=remaining,
            as_of_event_seq=source_seq[0],
            failure_states=failures,
        )
        return parent, contract, context

    def propose(
        self,
        plan_id: str,
        parent_sha256: str,
        proof_sha256: str,
        directory: Path,
        *,
        maximum_versions: int = 3,
        local_model_run: bool = False,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        if local_model_run is not True:
            raise KernelDenied("explicit_local_plan_model_intent_required")
        if not directory.is_absolute() or directory.resolve() != directory:
            raise KernelDenied("fresh_private_plan_output_required")
        key = idempotency_key if idempotency_key is not None else "output:" + str(directory)
        if type(key) is not str or not 1 <= len(key.encode()) <= (128 if idempotency_key is not None else 1280):
            raise KernelDenied("repair_draft_key_invalid")
        key_sha, directory_sha = _sha(key.encode()), _sha(str(directory).encode())
        with self.owner.connect() as c:
            parent = PlanStore().get(UnitOfWork(c), self.owner.actor, plan_id)
            ledger = repair_ledger(UnitOfWork(c), self.owner.actor, parent.proposal.goal_id)
            prior = next((i for i in ledger.intents if i.key_sha256 == key_sha), None)
            if prior is not None:
                if (
                    prior.parent_plan_id != plan_id
                    or prior.parent_sha256 != parent_sha256
                    or prior.return_proof_sha256 != proof_sha256
                    or prior.directory_sha256 != directory_sha
                    or prior.maximum_turns != maximum_versions - 1
                ):
                    raise KernelDenied("repair_draft_replay_conflict")
                return self._replay(directory, prior, ledger.outcome(prior))
        parent, contract, context = self._basis(plan_id, parent_sha256, proof_sha256, maximum_versions)
        intent: RepairIntent | None = None
        acknowledged = False
        started_at = 0.0

        def observe(c: psycopg.Connection[Any], *, reserve: bool) -> None:
            now, current_contract, current = self._basis_in(
                c,
                plan_id,
                parent_sha256,
                proof_sha256,
                maximum_versions,
                reserve=reserve,
                own_intent=intent.draft_id if acknowledged and intent else None,
            )
            if now != parent or current_contract != contract or current != context:
                raise KernelDenied("local_repair_source_changed")

        def locked_source(c: psycopg.Connection[Any], *, reserve: bool) -> None:
            # Mutation boundaries use READ COMMITTED. Acquire the canonical
            # writer locks before reading; a snapshot taken while waiting for
            # a lock must not miss a newly committed revision or cancellation.
            uow = UnitOfWork(c)
            c.execute("SELECT pg_advisory_xact_lock(%s,%s)", FLEET_LOCK)
            lock_project(uow, self.owner.actor)
            state = c.execute(
                "SELECT status FROM panestria.goal WHERE id=%s FOR NO KEY UPDATE",
                (parent.proposal.goal_id,),
            ).fetchone()
            c.execute(
                "SELECT id FROM panestria.task WHERE goal_id=%s ORDER BY id FOR UPDATE", (parent.proposal.goal_id,)
            ).fetchall()
            store = PlanStore()
            current = store.get(uow, self.owner.actor, plan_id)
            _, _, bound = store._goal(uow, self.owner.actor, parent.proposal.goal_id, read_only=True)
            ids = c.execute(
                "SELECT id::text FROM panestria.build_plan WHERE goal_id=%s ORDER BY version",
                (parent.proposal.goal_id,),
            ).fetchall()
            seq = c.execute(
                "SELECT COALESCE(max(seq),0) FROM panestria.task_event WHERE goal_id=%s AND kind NOT IN (%s,%s)",
                (parent.proposal.goal_id, STARTED, FINISHED),
            ).fetchone()
            ledger = repair_ledger(uow, self.owner.actor, parent.proposal.goal_id)
            if reserve and ledger.unresolved:
                raise KernelDenied("repair_draft_prior_unconfirmed")
            wall = sum(store.get(uow, self.owner.actor, row[0]).validation.upper_wall_seconds for row in ids)
            available = bound.budget.max_wall_seconds - wall - ledger.charged_wall_seconds
            if reserve:
                available -= TURN_WALL_SECONDS
            if (
                current != parent
                or bound != contract
                or not ids
                or ids[-1] != (plan_id,)
                or state not in [("CREATED",), ("ACTIVE",)]
                or seq != (context.as_of_event_seq,)
                or available != context.remaining_wall_seconds
            ):
                raise KernelDenied("local_repair_source_changed")

        def start(request: InferenceRequest) -> None:
            nonlocal intent, acknowledged, started_at
            with self.owner.connect() as c:
                locked_source(c, reserve=True)
                ledger = repair_ledger(UnitOfWork(c), self.owner.actor, parent.proposal.goal_id)
                intent = RepairIntent(
                    draft_id=request.request_id,
                    parent_plan_id=plan_id,
                    parent_sha256=parent_sha256,
                    return_proof_sha256=proof_sha256,
                    contract_sha256=parent.proposal.contract_sha256,
                    key_sha256=key_sha,
                    directory_sha256=directory_sha,
                    context_sha256=context.sha256(),
                    request_sha256=request.sha256(),
                    turn=len(ledger.intents) + 1,
                    maximum_turns=maximum_versions - 1,
                )
                begin_repair(UnitOfWork(c), self.owner.actor, parent.proposal.goal_id, intent)
            # Generation is downstream of an acknowledged database commit. A
            # lost commit acknowledgment must not call the model or auto-repeat.
            acknowledged, started_at = True, time.monotonic()

        def still_current() -> None:
            if time.monotonic() - started_at > TURN_WALL_SECONDS:
                raise KernelDenied("repair_wall_reservation_exceeded")
            with self.owner.connect() as c:
                c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                observe(c, reserve=False)

        try:
            receipt = self.planner.propose(
                contract,
                parent.inventory,
                directory,
                local_model_run=True,
                repair=context,
                publication_guard=still_current,
                before_dispatch=start,
            )
            assert acknowledged and intent is not None
            files = self._files(directory)
            outcome = RepairOutcome(
                draft_id=intent.draft_id,
                intent_sha256=intent.sha256(),
                status="RETAINED",
                physical_return="CONFIRMED",
                receipt_sha256=files["result.json"],
                files=files,
                reason="ok",
            )
            with self.owner.connect() as c:
                locked_source(c, reserve=False)
                if time.monotonic() - started_at > TURN_WALL_SECONDS:
                    raise KernelDenied("repair_wall_reservation_exceeded")
                finish_repair(UnitOfWork(c), self.owner.actor, parent.proposal.goal_id, outcome)
            return {**receipt, "draft_id": intent.draft_id, "replayed": False}
        except BaseException:
            if acknowledged and intent is not None:
                try:
                    self._record_failure(parent.proposal.goal_id, intent, directory, started_at)
                except Exception:
                    pass  # Unacknowledged outcome stays visible; never redispatch.
            raise

    def _record_failure(self, goal_id: str, intent: RepairIntent, directory: Path, started_at: float) -> None:
        with self.owner.connect() as c:
            known = repair_ledger(UnitOfWork(c), self.owner.actor, goal_id).outcome(intent)
        if known is not None:
            return
        # A response is created only after the trusted model call
        # returned through its cleanup. Absence means UNKNOWN, not
        # proof that it never ran. Charges are never refunded.
        returned = (directory / "response.txt").is_file()
        over = time.monotonic() - started_at > TURN_WALL_SECONDS
        _atomic(
            directory / "result.json",
            {
                "status": "UNAVAILABLE",
                "draft_id": intent.draft_id,
                "execution_authority": "NONE",
                "automatic_retry": False,
            },
        )
        outcome = RepairOutcome(
            draft_id=intent.draft_id,
            intent_sha256=intent.sha256(),
            status="NOT_PUBLISHED" if returned and not over else "UNCONFIRMED",
            physical_return="CONFIRMED" if returned else "UNCONFIRMED",
            files=self._files(directory),
            reason="wall_reservation_exceeded" if over else "draft_not_published" if returned else "return_unconfirmed",
        )
        with self.owner.connect() as c:
            finish_repair(UnitOfWork(c), self.owner.actor, goal_id, outcome)

    def _files(self, directory: Path) -> dict[str, str]:
        result = {}
        for name in DRAFT_FILES:
            path = directory / name
            if path.exists():
                result[name] = self.owner.reports.write_report(read_private(path, 32768))
        return result

    def _replay(self, directory: Path, intent: RepairIntent, outcome: RepairOutcome | None) -> dict[str, Any]:
        if outcome is None or outcome.status != "RETAINED":
            return {
                "status": outcome.status if outcome else "UNCONFIRMED",
                "draft_id": intent.draft_id,
                "physical_return": outcome.physical_return if outcome else "UNCONFIRMED",
                "replayed": True,
                "execution_authority": "NONE",
            }
        if set(outcome.files) != set(DRAFT_FILES) or outcome.receipt_sha256 != outcome.files["result.json"]:
            raise KernelDenied("repair_draft_receipt_unconfirmed")
        for name, digest in outcome.files.items():
            raw = self.owner.reports.read_blob(digest)
            if name not in DRAFT_FILES or read_private(directory / name, 32768) != raw:
                raise KernelDenied("repair_draft_files_unconfirmed")
        result = json.loads(self.owner.reports.read_blob(outcome.receipt_sha256))
        if not isinstance(result, dict) or result.get("repair_context_sha256") != intent.context_sha256:
            raise KernelDenied("repair_draft_receipt_unconfirmed")
        return {**result, "draft_id": intent.draft_id, "replayed": True, "acknowledgment": "HISTORICAL_NO_AUTHORITY"}


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()
