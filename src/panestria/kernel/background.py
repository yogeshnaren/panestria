"""Bounded queue bindings in existing immutable PostgreSQL events, not task state.

Accepted tasks/attempts/claims remain canonical. Queue review cannot mint a lease,
provider permission, billing setting, spend reservation or model-training right.
"""

import json
from datetime import timedelta
from decimal import Decimal
from typing import Any

from panestria.contracts.background import BackgroundBinding, BackgroundEnqueue
from panestria.contracts.build import canonical_sha256
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.plan_scope import task_plan_scope
from panestria.kernel.plan_store import PlanStore
from panestria.kernel.quota import QuotaService
from panestria.kernel.repositories.policy import lock_project
from panestria.kernel.repositories.tasks import append_event
from panestria.kernel.scheduler import FLEET_LOCK
from panestria.kernel.uow import UnitOfWork


class BackgroundWorkService:
    def _rows(self, uow: UnitOfWork, actor: Actor) -> list[tuple[Any, ...]]:
        rows = uow.execute(
            "SELECT e.seq,e.payload,e.goal_id::text,e.task_id::text FROM panestria.task_event e "
            "JOIN panestria.goal g ON g.id=e.goal_id WHERE g.owner_id=%s AND g.project_id=%s "
            "AND e.kind='background.queued' ORDER BY e.seq LIMIT 257",
            (actor.owner_id, actor.project_id),
        ).fetchall()
        if len(rows) > 256:
            raise KernelDenied("background_queue_history_limit")
        return rows

    def _binding(self, row: tuple[Any, ...], actor: Actor) -> BackgroundBinding:
        binding = BackgroundBinding.model_validate_json(json.dumps(row[1]["binding"]))
        if (
            (binding.owner_id, binding.project_id, binding.goal_id, binding.task_id)
            != (actor.owner_id, actor.project_id, row[2], row[3])
            or binding.sha256() != row[1]["binding_sha256"]
            or binding.policy_sha256 != binding.request.policy.sha256()
        ):
            raise KernelDenied("background_queue_binding_corrupt")
        return binding

    def prepare(self, uow: UnitOfWork, actor: Actor, request: BackgroundEnqueue) -> BackgroundBinding:
        request = BackgroundEnqueue.model_validate(request)
        policy = request.policy
        if (policy.owner_id, policy.project_id) != (actor.owner_id, actor.project_id):
            raise KernelDenied("not_found")
        plan = PlanStore().get(uow, actor, request.plan_id)
        if plan.state != "ACCEPTED" or plan.proposal.sha256() != request.expected_plan_sha256:
            raise KernelDenied("background_current_accepted_plan_required")
        latest = uow.execute(
            "SELECT id::text FROM panestria.build_plan WHERE goal_id=%s ORDER BY version DESC LIMIT 1",
            (plan.proposal.goal_id,),
        ).fetchone()
        if latest != (request.plan_id,):
            raise KernelDenied("background_plan_superseded")
        scope = task_plan_scope(uow, actor, plan.proposal.nodes[0].task_id)
        assert scope is not None
        if request.category not in policy.categories or plan.proposal.privacy_class != "PUBLIC":
            raise KernelDenied("background_category_or_privacy_denied")
        wall = sum(n.attempts * n.wall_seconds_per_attempt for n in plan.proposal.nodes)
        if wall > policy.maximum_job_wall_seconds or any(n.api_microusd_per_attempt for n in plan.proposal.nodes):
            raise KernelDenied("background_original_budget_limit")
        if any(n.worker_ref not in {"claude-public-bash", "trusted-integrator"} for n in plan.proposal.nodes):
            raise KernelDenied("background_worker_not_supported")
        return BackgroundBinding(
            request=request,
            owner_id=actor.owner_id,
            project_id=actor.project_id,
            goal_id=plan.proposal.goal_id,
            task_id=scope.integration_task_id,
            contract_sha256=plan.proposal.contract_sha256,
            inventory_sha256=plan.inventory.sha256(),
            context_sha256=canonical_sha256(
                {
                    "contract_sha256": plan.proposal.contract_sha256,
                    "plan_sha256": plan.proposal.sha256(),
                    "inventory_sha256": plan.inventory.sha256(),
                }
            ),
            policy_sha256=policy.sha256(),
            upper_wall_seconds=wall,
        )

    def enqueue(
        self,
        uow: UnitOfWork,
        actor: Actor,
        request: BackgroundEnqueue,
        policy_sha256: str,
        *,
        accept_background_policy: bool = False,
    ) -> dict[str, Any]:
        PlanStore()._transaction(uow)
        uow.execute("SELECT pg_advisory_xact_lock(%s,%s)", FLEET_LOCK)
        lock_project(uow, actor)
        binding = self.prepare(uow, actor, request)
        if accept_background_policy is not True or policy_sha256 != binding.policy_sha256:
            raise KernelDenied("background_exact_owner_policy_review_required")
        rows = self._rows(uow, actor)
        for row in rows:
            old = self._binding(row, actor)
            if old.request.item_id == request.item_id:
                if old != binding:
                    raise KernelDenied("background_item_replay_conflict")
                return {
                    "status": "QUEUED",
                    "item_id": request.item_id,
                    "binding_sha256": old.sha256(),
                    "event_seq": row[0],
                    "replayed": True,
                    "execution_authority": "NONE",
                }
            if old.request.plan_id == request.plan_id:
                raise KernelDenied("background_plan_already_queued")
        if len(rows) >= 256:
            raise KernelDenied("background_queue_history_limit")
        clock = uow.execute("SELECT clock_timestamp()").fetchone()
        assert clock is not None
        now = clock[0]
        if request.policy.expires_at <= now:
            raise KernelDenied("background_policy_expired")
        goal = uow.execute("SELECT status FROM panestria.goal WHERE id=%s FOR UPDATE", (binding.goal_id,)).fetchone()
        if goal is None or goal[0] not in {"CREATED", "ACTIVE"}:
            raise KernelDenied("background_goal_not_active")
        attempts = uow.execute(
            "SELECT 1 FROM panestria.task_attempt a JOIN panestria.task t ON t.id=a.task_id WHERE t.goal_id=%s LIMIT 1",
            (binding.goal_id,),
        ).fetchone()
        if attempts:
            raise KernelDenied("background_fresh_unstarted_goal_required")
        # This event is the last write. Immutable binding plus canonical task
        # state supplies the queue; no separate QUEUED/RUNNING task store.
        seq = append_event(
            uow,
            goal_id=binding.goal_id,
            task_id=binding.task_id,
            actor=actor.owner_id,
            kind="background.queued",
            payload={"binding": binding.model_dump(mode="json"), "binding_sha256": binding.sha256()},
        )
        return {
            "status": "QUEUED",
            "item_id": request.item_id,
            "binding_sha256": binding.sha256(),
            "event_seq": seq,
            "replayed": False,
            "execution_authority": "NONE",
        }

    def inspect(self, uow: UnitOfWork, actor: Actor, binding: BackgroundBinding) -> dict[str, Any]:
        # Revalidate scope and immutable plan at every observation; this is still
        # not a dispatch permit. A later dispatcher must recheck actual runtime.
        current = self.prepare(uow, actor, binding.request)
        if current != binding:
            raise KernelDenied("background_binding_changed")
        clock = uow.execute("SELECT clock_timestamp()").fetchone()
        assert clock is not None
        now = clock[0]
        policy, reasons, observations, resets = binding.request.policy, [], [], []
        exhausted = []
        if policy.expires_at <= now:
            reasons.append("policy_expired")
        billing = policy.billing
        if billing is None or billing.usage_credits_enabled is not False:
            reasons.append("no_extra_spend_boundary_unconfirmed")
        elif not billing.observed_at <= now < billing.observed_at + timedelta(seconds=billing.fresh_for_seconds):
            reasons.append("billing_report_stale_or_future")
        goal = uow.execute("SELECT status FROM panestria.goal WHERE id=%s", (binding.goal_id,)).fetchone()
        if goal is None or goal[0] not in {"CREATED", "ACTIVE"}:
            reasons.append("goal_ended")
        states = uow.execute("SELECT state FROM panestria.task WHERE goal_id=%s", (binding.goal_id,)).fetchall()
        if any(r[0] not in {"CREATED", "READY"} for r in states):
            reasons.append("goal_already_started_or_requires_owner_inspection")
        foreground_row = uow.execute(
            "SELECT EXISTS(SELECT 1 FROM panestria.build_active_worker_claim) OR "
            "EXISTS(SELECT 1 FROM panestria.ask_request WHERE state IN ('PREPARED','RUNNING'))"
        ).fetchone()
        assert foreground_row is not None
        if foreground_row[0]:
            reasons.append("foreground_or_held_capacity_reserved")
        for window in policy.quota_windows:
            views = QuotaService().latest(uow, actor, window)
            # A later null/unknown report cannot erase an earlier observed zero.
            # A newer numeric report in that same lane, or its known reset,
            # can supersede the old exhaustion without inventing a new balance.
            numeric = uow.execute(
                "SELECT DISTINCT ON(source) id::text FROM panestria.quota_observation "
                "WHERE owner_id=%s AND project_id=%s AND scope_sha256=%s "
                "AND source IN ('OWNER_REPORTED','PROVIDER_REPORTED') "
                "AND body->>'remaining' IS NOT NULL "
                "ORDER BY source,observed_at DESC,created_at DESC,id DESC",
                (actor.owner_id, actor.project_id, window.sha256()),
            ).fetchall()
            for (identifier,) in numeric:
                prior = QuotaService().read(uow, actor, identifier)
                if Decimal(prior.observation.remaining or "0") == 0 and prior.freshness != "RESET_PASSED":
                    reasons.append("observed_exhaustion_wait_for_new_evidence_or_reset")
                    exhausted.append(
                        {
                            "observation_id": identifier,
                            "source": prior.observation.source,
                            "window_ref": window.window_ref,
                            "freshness": prior.freshness,
                        }
                    )
            # Preserve all lanes. A later owner unknown report cannot erase an
            # independent provider exhaustion reading in the same window.
            fresh_quantity = False
            for view in views:
                o = view.observation
                observations.append(
                    {
                        "observation_id": o.observation_id,
                        "source": o.source,
                        "freshness": view.freshness,
                        "effective_remaining": view.effective_remaining,
                        "unit": o.unit,
                        "window_ref": window.window_ref,
                    }
                )
                amount = Decimal(o.remaining) if o.remaining is not None else None
                if (
                    amount == 0
                    and o.source in {"OWNER_REPORTED", "PROVIDER_REPORTED"}
                    and view.freshness != "RESET_PASSED"
                ):
                    reasons.append("observed_exhaustion_wait_for_new_evidence_or_reset")
                if view.freshness == "FRESH" and view.effective_remaining is not None:
                    fresh_quantity |= (
                        o.source in {"OWNER_REPORTED", "PROVIDER_REPORTED"} or policy.allow_estimated_quota
                    )
                    reserve = {
                        "percent": policy.regular_use_reserve_percent,
                        "tokens": policy.regular_use_reserve_tokens,
                        "requests": policy.regular_use_reserve_requests,
                    }[str(o.unit)]
                    if Decimal(view.effective_remaining) <= reserve:
                        reasons.append("regular_use_reserve")
                    if o.resets_at is not None and o.source in {"OWNER_REPORTED", "PROVIDER_REPORTED"}:
                        resets.append(max(0, int((o.resets_at - now).total_seconds())))
            if not fresh_quantity and not policy.allow_unknown_quota:
                reasons.append("quota_unknown_requires_explicit_best_effort_policy")
        return {
            "item_id": binding.request.item_id,
            "goal_id": binding.goal_id,
            "plan_id": binding.request.plan_id,
            "binding_sha256": binding.sha256(),
            "policy_sha256": binding.policy_sha256,
            "scheduling_candidate": not reasons,
            "waiting_reasons": sorted(set(reasons)),
            "quota_observations": observations,
            "retained_exhaustion_observations": exhausted,
            "billing_source": billing.source if billing else "UNKNOWN",
            "billing_confidence": "OWNER_REPORTED_NOT_PROVIDER_VERIFIED" if billing else "UNKNOWN",
            "no_extra_spend_runtime_qualification": "NOT_ASSESSED",
            "seconds_to_reported_reset": min(resets) if resets else None,
            "value_priority": binding.request.value_priority,
            "model_identity": "UNKNOWN",
            "execution_authority": "NONE",
            "runtime_qualification": "NOT_ASSESSED",
        }

    def listing(self, uow: UnitOfWork, actor: Actor) -> dict[str, Any]:
        rows = self._rows(uow, actor)
        items: list[dict[str, Any]] = []
        for row in rows[-32:]:
            binding = self._binding(row, actor)
            withdrawn = uow.execute(
                "SELECT 1 FROM panestria.task_event WHERE goal_id=%s "
                "AND kind='background.withdrawn' AND payload->>'item_id'=%s LIMIT 1",
                (binding.goal_id, binding.request.item_id),
            ).fetchone()
            if withdrawn:
                items.append({"item_id": binding.request.item_id, "status": "WITHDRAWN", "execution_authority": "NONE"})
                continue
            try:
                items.append(self.inspect(uow, actor, binding))
            except KernelDenied as exc:
                items.append(
                    {
                        "item_id": binding.request.item_id,
                        "scheduling_candidate": False,
                        "waiting_reasons": [exc.code],
                        "execution_authority": "NONE",
                    }
                )
        return {"items": items, "history_count": len(rows), "visible_limit": 32, "execution_authority": "NONE"}

    def show(self, uow: UnitOfWork, actor: Actor, item_id: str) -> dict[str, Any]:
        for row in self._rows(uow, actor):
            binding = self._binding(row, actor)
            if binding.request.item_id == item_id:
                withdrawn = uow.execute(
                    "SELECT 1 FROM panestria.task_event WHERE goal_id=%s "
                    "AND kind='background.withdrawn' AND payload->>'item_id'=%s LIMIT 1",
                    (binding.goal_id, item_id),
                ).fetchone()
                if withdrawn:
                    return {"item_id": item_id, "status": "WITHDRAWN", "execution_authority": "NONE"}
                return self.inspect(uow, actor, binding)
        raise KernelDenied("not_found")

    def withdraw(self, uow: UnitOfWork, actor: Actor, item_id: str, binding_sha256: str) -> dict[str, Any]:
        PlanStore()._transaction(uow)
        uow.execute("SELECT pg_advisory_xact_lock(%s,%s)", FLEET_LOCK)
        rows = self._rows(uow, actor)
        for row in rows:
            binding = self._binding(row, actor)
            if binding.request.item_id != item_id:
                continue
            if binding.sha256() != binding_sha256:
                raise KernelDenied("background_item_changed")
            old = uow.execute(
                "SELECT seq FROM panestria.task_event WHERE goal_id=%s "
                "AND kind='background.withdrawn' AND payload->>'item_id'=%s LIMIT 1",
                (binding.goal_id, item_id),
            ).fetchone()
            if old:
                return {"status": "WITHDRAWN", "event_seq": old[0], "execution_authority": "NONE"}
            seq = append_event(
                uow,
                goal_id=binding.goal_id,
                task_id=binding.task_id,
                actor=actor.owner_id,
                kind="background.withdrawn",
                payload={"item_id": item_id, "binding_sha256": binding_sha256},
            )
            return {"status": "WITHDRAWN", "event_seq": seq, "execution_authority": "NONE"}
        raise KernelDenied("not_found")
