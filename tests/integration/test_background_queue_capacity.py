"""F-D4 / ARCH-P1-4: withdrawal frees queue capacity; lookups use kind indexes."""

import json
from uuid import uuid4

from test_background_queue import request_for
from test_native_plan_execution import native_plan as native_plan  # noqa: F401
from test_native_plan_execution import prepared_plan as prepared_plan  # noqa: F401
from test_owner_build_cli import owner_cli as owner_cli  # noqa: F401

from panestria.contracts.background import BackgroundEnqueue
from panestria.kernel.background import BackgroundWorkService
from panestria.kernel.uow import UnitOfWork


def test_f_d4_three_hundred_enqueue_withdraw_cycles_never_wedge_the_queue(prepared_plan, native_plan):
    f, owner, _, plan = prepared_plan
    service, base = BackgroundWorkService(), request_for(owner, plan)
    first = None
    for _ in range(300):
        request = BackgroundEnqueue.model_validate_json(
            json.dumps({**base.model_dump(mode="json"), "item_id": str(uuid4())})
        )
        with owner.connect() as c:
            queued = service.enqueue(
                UnitOfWork(c), owner.actor, request, request.policy.sha256(), accept_background_policy=True
            )
            assert queued["status"] == "QUEUED" and not queued["replayed"]
            service.withdraw(UnitOfWork(c), owner.actor, request.item_id, queued["binding_sha256"])
        first = first or (request, queued)
    with owner.connect() as c:
        uow = UnitOfWork(c)
        assert service._rows(uow, owner.actor) == []
        listing = service.listing(uow, owner.actor)
        assert listing["history_count"] == 300 and len(listing["items"]) == 32
        assert {item["status"] for item in listing["items"]} == {"WITHDRAWN"}
        # The oldest item is still found by id, and its replay stays idempotent.
        request, queued = first
        assert service.show(uow, owner.actor, request.item_id)["status"] == "WITHDRAWN"
        replay = service.enqueue(uow, owner.actor, request, request.policy.sha256(), accept_background_policy=True)
        assert replay["replayed"] and replay["event_seq"] == queued["event_seq"]


def test_arch_p1_4_queue_lookups_can_use_the_kind_indexes(prepared_plan, native_plan):
    f, owner, _, plan = prepared_plan
    service = BackgroundWorkService()
    with owner.connect() as c:
        c.execute("SET LOCAL enable_seqscan=off")
        plan_text = "\n".join(
            row[0]
            for row in c.execute(
                "EXPLAIN " + service._QUEUED + service._LIVE + "ORDER BY e.seq LIMIT 257",
                (owner.actor.owner_id, owner.actor.project_id),
            ).fetchall()
        )
        assert "ix_task_event_kind_goal" in plan_text
        active = "\n".join(
            row[0]
            for row in c.execute(
                "EXPLAIN SELECT 1 FROM panestria.task_event s WHERE s.kind='background.run_started' AND NOT EXISTS "
                "(SELECT 1 FROM panestria.task_event r WHERE r.goal_id=s.goal_id "
                "AND r.kind='background.run_returned' AND r.payload->>'run_sha256'=s.payload->>'run_sha256') LIMIT 1"
            ).fetchall()
        )
        assert "ix_task_event_kind_goal" in active
