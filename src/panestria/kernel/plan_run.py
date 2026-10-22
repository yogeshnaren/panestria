"""Immutable foreground request/claim/return facts on the canonical event ledger.

No second task store, process inference, timeout release or automatic resumption.
The caller commits a request and a claim separately before any native dispatch.
"""

import json
from datetime import datetime

from panestria.contracts.goal import contract_sha256, load_contract
from panestria.contracts.plan import StoredPlan
from panestria.contracts.plan_run import PlanRunIntent, PlanRunRecord, PlanRunReturn, PlanRunStorage, PlanRunView
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.plan_store import PlanStore
from panestria.kernel.repositories.policy import lock_project
from panestria.kernel.repositories.tasks import append_event
from panestria.kernel.uow import UnitOfWork

PREFIX = "mission.build_run."


class PlanRunStore:
    def _scope(self, uow: UnitOfWork, actor: Actor, plan_id: str) -> tuple[StoredPlan, str]:
        PlanStore()._transaction(uow)
        # Historical metadata and withdrawal stay available after policy expiry.
        plan = PlanStore()._read(uow, actor, plan_id)
        row = uow.execute(
            "SELECT g.status,c.body FROM panestria.goal g JOIN panestria.goal_contract c ON c.goal_id=g.id"
            " WHERE g.id=%s AND g.owner_id=%s AND g.project_id=%s ORDER BY c.version DESC LIMIT 1",
            (plan.proposal.goal_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        contract = load_contract(row[1])
        if contract.privacy_class != "PUBLIC" or contract_sha256(contract) != plan.proposal.contract_sha256:
            raise KernelDenied("public_run_scope_unconfirmed")
        return plan, str(row[0])

    def inspect(self, uow: UnitOfWork, actor: Actor, plan_id: str, configuration: str) -> PlanRunView:
        plan, status = self._scope(uow, actor, plan_id)
        rows = uow.execute(
            "SELECT kind,payload FROM panestria.task_event WHERE goal_id=%s AND kind IN (%s,%s,%s)"
            " AND payload->>'plan_id'=%s ORDER BY seq LIMIT 4",
            (plan.proposal.goal_id, PREFIX + "requested", PREFIX + "claimed", PREFIX + "returned", plan_id),
        ).fetchall()
        record, returned, state = None, None, "NOT_REQUESTED"
        for kind, payload in rows:
            if kind == PREFIX + "requested" and state == "NOT_REQUESTED":
                record = PlanRunRecord.model_validate_json(json.dumps(payload["record"]))
                if (
                    (record.owner_id, record.project_id, record.goal_id, record.plan_id)
                    != (actor.owner_id, actor.project_id, plan.proposal.goal_id, plan_id)
                    or record.intent.plan_sha256 != plan.proposal.sha256()
                    or payload.get("record_sha256") != record.sha256()
                ):
                    raise KernelDenied("run_record_unconfirmed")
                state = "REQUESTED"
            elif record is not None and payload.get("record_sha256") == record.sha256():
                if kind == PREFIX + "claimed" and state == "REQUESTED":
                    state = "CLAIMED_UNCONFIRMED"
                elif kind == PREFIX + "returned" and state == "CLAIMED_UNCONFIRMED":
                    returned = PlanRunReturn.model_validate_json(json.dumps(payload["result"]))
                    if returned.request_id != record.intent.request_id or returned.record_sha256 != record.sha256():
                        raise KernelDenied("run_return_unconfirmed")
                    state = "RETURN_RECORDED"
                else:
                    raise KernelDenied("run_history_unconfirmed")
            else:
                raise KernelDenied("run_history_unconfirmed")
        now = uow.execute("SELECT clock_timestamp()").fetchone()
        assert now is not None
        storage = None
        if record is not None:
            notice = uow.execute(
                "SELECT payload FROM panestria.task_event WHERE goal_id=%s AND kind=%s"
                " AND payload->>'record_sha256'=%s ORDER BY seq DESC LIMIT 1",
                (record.goal_id, PREFIX + "storage", record.sha256()),
            ).fetchone()
            if notice is not None:
                storage = PlanRunStorage.model_validate_json(json.dumps(notice[0]))
        return PlanRunView.model_validate(
            {
                "owner_id": actor.owner_id,
                "project_id": actor.project_id,
                "goal_id": plan.proposal.goal_id,
                "plan_id": plan_id,
                "plan_sha256": plan.proposal.sha256(),
                "record": record,
                "state": state,
                "result": returned,
                "goal_status": status,
                "configuration_current": record is None or record.configuration_sha256 == configuration,
                "observed_at": now[0].isoformat(),
                "expired": record is not None and now[0] >= datetime.fromisoformat(record.expires_at),
                "storage": storage,
            }
        )

    def _ready(self, uow: UnitOfWork, actor: Actor, plan_id: str, digest: str) -> StoredPlan:
        plan = PlanStore().get(uow, actor, plan_id)  # Current policy and protected canonical scope.
        if plan.state != "ACCEPTED" or plan.proposal.sha256() != digest:
            raise KernelDenied("accepted_exact_plan_required")
        latest = uow.execute(
            "SELECT p.id::text FROM panestria.build_plan p JOIN panestria.build_plan_acceptance a ON a.plan_id=p.id"
            " WHERE p.goal_id=%s ORDER BY p.version DESC LIMIT 1",
            (plan.proposal.goal_id,),
        ).fetchone()
        tasks = uow.execute(
            "SELECT t.state,EXISTS(SELECT 1 FROM panestria.task_attempt a WHERE a.task_id=t.id)"
            " FROM panestria.build_plan_task p JOIN panestria.task t ON t.id=p.task_id WHERE p.plan_id=%s",
            (plan_id,),
        ).fetchall()
        status = uow.execute("SELECT status FROM panestria.goal WHERE id=%s", (plan.proposal.goal_id,)).fetchone()
        if (
            latest != (plan_id,)
            or status not in {("CREATED",), ("ACTIVE",)}
            or (len(tasks) != len(plan.proposal.nodes) or any(s != "CREATED" or attempted for s, attempted in tasks))
        ):
            raise KernelDenied("only_unstarted_plan_supported")
        return plan

    def request(
        self, uow: UnitOfWork, actor: Actor, plan_id: str, intent: PlanRunIntent, configuration: str
    ) -> PlanRunView:
        lock_project(uow, actor)
        view = self.inspect(uow, actor, plan_id, configuration)
        if view.record is not None:
            if view.record.intent != intent or not view.configuration_current:
                raise KernelDenied("original_run_request_required")
            return view  # Exact replay cannot create a second invocation or renew expiry.
        plan = self._ready(uow, actor, plan_id, intent.plan_sha256)
        deadline = uow.execute("SELECT clock_timestamp()+interval '90 seconds'").fetchone()
        assert deadline is not None
        record = PlanRunRecord(
            owner_id=actor.owner_id,
            project_id=actor.project_id,
            goal_id=plan.proposal.goal_id,
            plan_id=plan_id,
            intent=intent,
            configuration_sha256=configuration,
            expires_at=deadline[0].isoformat(),
        )
        append_event(
            uow,
            goal_id=record.goal_id,
            task_id=None,
            actor=actor.owner_id,
            kind=PREFIX + "requested",
            payload={"plan_id": plan_id, "record": record.model_dump(mode="json"), "record_sha256": record.sha256()},
        )
        return self.inspect(uow, actor, plan_id, configuration)

    def claim(self, uow: UnitOfWork, actor: Actor, plan_id: str, request_id: str, configuration: str) -> PlanRunRecord:
        lock_project(uow, actor)
        view = self.inspect(uow, actor, plan_id, configuration)
        if (
            view.state != "REQUESTED"
            or view.record is None
            or view.record.intent.request_id != request_id
            or not view.configuration_current
            or view.expired
        ):
            raise KernelDenied("run_not_claimable")
        self._ready(uow, actor, plan_id, view.plan_sha256)
        # An unreturned claim blocks other browser controllers in this project,
        # even if the old process died before acquiring any native task claim.
        held = uow.execute(
            "SELECT 1 FROM panestria.task_event e JOIN panestria.goal g ON g.id=e.goal_id"
            " WHERE g.owner_id=%s AND g.project_id=%s AND e.kind=%s AND NOT EXISTS"
            " (SELECT 1 FROM panestria.task_event r WHERE r.goal_id=e.goal_id AND r.kind=%s"
            " AND r.payload->>'record_sha256'=e.payload->>'record_sha256') LIMIT 1",
            (actor.owner_id, actor.project_id, PREFIX + "claimed", PREFIX + "returned"),
        ).fetchone()
        if held:
            raise KernelDenied("browser_controller_unconfirmed")
        append_event(
            uow,
            goal_id=view.goal_id,
            task_id=None,
            actor=actor.owner_id,
            kind=PREFIX + "claimed",
            payload={"plan_id": plan_id, "record_sha256": view.record.sha256()},
        )
        return view.record

    def finish(self, uow: UnitOfWork, actor: Actor, plan_id: str, result: PlanRunReturn, configuration: str) -> None:
        lock_project(uow, actor)
        view = self.inspect(uow, actor, plan_id, configuration)
        if view.state == "RETURN_RECORDED" and view.result == result:
            return
        if (
            view.state != "CLAIMED_UNCONFIRMED"
            or view.record is None
            or result.record_sha256 != view.record.sha256()
            or result.request_id != view.record.intent.request_id
        ):
            raise KernelDenied("run_return_binding_changed")
        append_event(
            uow,
            goal_id=view.goal_id,
            task_id=None,
            actor=actor.owner_id,
            kind=PREFIX + "returned",
            payload={
                "plan_id": plan_id,
                "record_sha256": result.record_sha256,
                "result": result.model_dump(mode="json"),
            },
        )

    def storage(self, uow: UnitOfWork, actor: Actor, record: PlanRunRecord, notice: PlanRunStorage) -> None:
        lock_project(uow, actor)
        view = self.inspect(uow, actor, record.plan_id, record.configuration_sha256)
        if view.state != "CLAIMED_UNCONFIRMED" or view.record != record or notice.record_sha256 != record.sha256():
            raise KernelDenied("run_storage_binding_changed")
        append_event(
            uow,
            goal_id=record.goal_id,
            task_id=None,
            actor=actor.owner_id,
            kind=PREFIX + "storage",
            payload=notice.model_dump(mode="json"),
        )
