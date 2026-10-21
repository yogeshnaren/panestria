"""Exact owner account links in the existing event ledger, never a dispatch grant."""

import json
from datetime import timedelta
from typing import Any

from panestria.contracts.background import BackgroundBinding
from panestria.contracts.native_account import BackgroundAccountLink, NativeAccountObservation
from panestria.kernel.background import BackgroundWorkService
from panestria.kernel.build import BuildEvidenceStore
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.plan_store import PlanStore
from panestria.kernel.repositories.policy import lock_project
from panestria.kernel.repositories.tasks import append_event
from panestria.kernel.scheduler import FLEET_LOCK
from panestria.kernel.uow import UnitOfWork


class BackgroundAccountService:
    def __init__(self, reports: BuildEvidenceStore) -> None:
        self.reports = reports

    def binding(self, uow: UnitOfWork, actor: Actor, item_id: str) -> BackgroundBinding:
        service = BackgroundWorkService()
        for row in service._rows(uow, actor):
            binding = service._binding(row, actor)
            if binding.request.item_id == item_id:
                return binding
        raise KernelDenied("not_found")

    def observation(self, digest: str) -> NativeAccountObservation:
        raw = self.reports.read_blob(digest)
        try:
            result = NativeAccountObservation.model_validate_json(raw)
        except ValueError:
            raise KernelDenied("background_account_observation_invalid") from None
        if result.sha256() != digest:
            raise KernelDenied("background_account_observation_noncanonical")
        return result

    def prepare(self, uow: UnitOfWork, actor: Actor, item_id: str, observation_sha256: str) -> BackgroundAccountLink:
        binding = self.binding(uow, actor, item_id)
        observed = self.observation(observation_sha256)
        if (observed.owner_id, observed.project_id) != (actor.owner_id, actor.project_id) or any(
            w.account_ref != observed.account_ref for w in binding.request.policy.quota_windows
        ):
            raise KernelDenied("background_account_scope_mismatch")
        if BackgroundWorkService().prepare(uow, actor, binding.request) != binding:
            raise KernelDenied("background_binding_changed")
        return BackgroundAccountLink(
            owner_id=actor.owner_id,
            project_id=actor.project_id,
            item_id=item_id,
            binding_sha256=binding.sha256(),
            observation_sha256=observation_sha256,
            identity_sha256=observed.identity_sha256,
            profile_sha256=observed.profile_sha256,
            account_ref=observed.account_ref,
            binary_sha256=observed.binary_sha256,
        )

    def _links(self, uow: UnitOfWork, binding: BackgroundBinding) -> list[tuple[Any, ...]]:
        rows = uow.execute(
            "SELECT seq,payload FROM panestria.task_event WHERE goal_id=%s AND task_id=%s "
            "AND kind='background.account_linked' AND payload->'link'->>'item_id'=%s ORDER BY seq LIMIT 65",
            (binding.goal_id, binding.task_id, binding.request.item_id),
        ).fetchall()
        if len(rows) > 64:
            raise KernelDenied("background_account_history_limit")
        return rows

    def _link(self, row: tuple[Any, ...], binding: BackgroundBinding) -> BackgroundAccountLink:
        try:
            result = BackgroundAccountLink.model_validate_json(json.dumps(row[1]["link"]))
            if (
                result.sha256() != row[1]["link_sha256"]
                or result.binding_sha256 != binding.sha256()
                or (result.owner_id, result.project_id, result.item_id)
                != (binding.owner_id, binding.project_id, binding.request.item_id)
            ):
                raise ValueError
            return result
        except (ValueError, KeyError, TypeError):
            raise KernelDenied("background_account_link_invalid") from None

    def confirm(
        self,
        uow: UnitOfWork,
        actor: Actor,
        item_id: str,
        observation_sha256: str,
        link_sha256: str,
        *,
        accept_account_link: bool = False,
    ) -> dict[str, Any]:
        PlanStore()._transaction(uow)
        uow.execute("SELECT pg_advisory_xact_lock(%s,%s)", FLEET_LOCK)
        lock_project(uow, actor)
        link = self.prepare(uow, actor, item_id, observation_sha256)
        if accept_account_link is not True or link.sha256() != link_sha256:
            raise KernelDenied("background_exact_account_review_required")
        binding = self.binding(uow, actor, item_id)
        rows = self._links(uow, binding)
        for row in rows:
            prior = self._link(row, binding)
            if prior == link:
                return {"status": "LINKED", "event_seq": row[0], "replayed": True, "execution_authority": "NONE"}
            if (prior.identity_sha256, prior.profile_sha256, prior.binary_sha256) != (
                link.identity_sha256,
                link.profile_sha256,
                link.binary_sha256,
            ):
                raise KernelDenied("background_account_changed_requires_new_reviewed_item")
        if len(rows) >= 64:
            raise KernelDenied("background_account_history_limit")
        clock = uow.execute("SELECT clock_timestamp()").fetchone()
        assert clock is not None
        observed = self.observation(observation_sha256)
        if not observed.observed_at <= clock[0] < observed.observed_at + timedelta(seconds=300):
            raise KernelDenied("background_account_observation_stale_or_future")
        if binding.request.policy.expires_at <= clock[0]:
            raise KernelDenied("background_policy_expired")
        if uow.execute(
            "SELECT 1 FROM panestria.task_event WHERE goal_id=%s AND kind='background.withdrawn' "
            "AND payload->>'item_id'=%s LIMIT 1",
            (binding.goal_id, item_id),
        ).fetchone():
            raise KernelDenied("background_item_withdrawn")
        goal = uow.execute("SELECT status FROM panestria.goal WHERE id=%s FOR UPDATE", (binding.goal_id,)).fetchone()
        if goal is None or goal[0] not in {"CREATED", "ACTIVE"}:
            raise KernelDenied("background_goal_not_active")
        if uow.execute(
            "SELECT 1 FROM panestria.task_attempt a JOIN panestria.task t ON t.id=a.task_id WHERE t.goal_id=%s LIMIT 1",
            (binding.goal_id,),
        ).fetchone():
            raise KernelDenied("background_fresh_unstarted_goal_required")
        seq = append_event(
            uow,
            goal_id=binding.goal_id,
            task_id=binding.task_id,
            actor=actor.owner_id,
            kind="background.account_linked",
            payload={"link": link.model_dump(mode="json"), "link_sha256": link.sha256()},
        )
        return {"status": "LINKED", "event_seq": seq, "replayed": False, "execution_authority": "NONE"}

    def inspect(self, uow: UnitOfWork, actor: Actor, item_id: str) -> dict[str, Any]:
        binding = self.binding(uow, actor, item_id)
        rows = self._links(uow, binding)
        if not rows:
            return {"status": "NOT_LINKED", "execution_authority": "NONE"}
        link = self._link(rows[-1], binding)
        expected = self.prepare(uow, actor, item_id, link.observation_sha256)
        if link != expected:
            raise KernelDenied("background_account_link_invalid")
        observed = self.observation(link.observation_sha256)
        clock = uow.execute("SELECT clock_timestamp()").fetchone()
        assert clock is not None
        return {
            "status": "LINKED_METADATA_ONLY",
            "event_seq": rows[-1][0],
            "link": link.model_dump(mode="json"),
            "link_sha256": link.sha256(),
            "observed_at": observed.observed_at.isoformat(),
            "freshness": "FRESH"
            if observed.observed_at <= clock[0] < observed.observed_at + timedelta(seconds=300)
            else "STALE_OR_FUTURE",
            "subscription_type": observed.subscription_type,
            "billing_verified": False,
            "runtime_qualification": "NOT_ASSESSED",
            "execution_authority": "NONE",
        }
