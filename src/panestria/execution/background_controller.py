"""Finite opt-in queue admission; no installed scheduler, implicit resume or merge."""

import threading
from collections.abc import Callable
from typing import Any

from panestria.execution.background_run import BackgroundPlanRunner, select_next
from panestria.execution.owner_build import OwnerBuild
from panestria.kernel.errors import KernelDenied


def work_queue(
    owner: OwnerBuild,
    *,
    allow_background_subscription_run: bool,
    maximum_ticks: int = 12,
    poll_seconds: int = 5,
    maximum_jobs: int = 1,
    cancel: threading.Event | None = None,
    on_observation: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    if allow_background_subscription_run is not True:
        raise KernelDenied("explicit_background_subscription_run_required")
    if any(type(v) is not int or not 1 <= v <= cap for v, cap in ((maximum_ticks, 64), (maximum_jobs, 8))) or (
        type(poll_seconds) is not int or not 5 <= poll_seconds <= 60
    ):
        raise KernelDenied("invalid_background_controller_bounds")
    stop = cancel if cancel is not None else threading.Event()
    runs: list[dict[str, Any]] = []
    ticks = 0

    def receipt(status: str, reason: str) -> dict[str, Any]:
        return {
            "status": status,
            "reason": reason,
            "ticks": ticks,
            "items": runs,
            "implicit_resume": False,
            "automatic_merge": False,
        }

    try:
        for _ in range(maximum_ticks):
            if stop.is_set():
                return receipt("CANCELLED", "controller_stopped")
            selection = select_next(owner)  # No provider probe, claim or event on idle ticks.
            ticks += 1
            selected = selection["selected"]
            if on_observation:
                on_observation(
                    {
                        "kind": "QUEUE_TICK",
                        "tick": ticks,
                        "status": selection["status"],
                        "candidate_count": selection["candidate_count"],
                        "item_id": selected["item_id"] if selected else None,
                    }
                )
            if stop.is_set():
                return receipt("CANCELLED", "controller_stopped")
            if selected is not None:
                # Selection reserves nothing. A competing controller, changed
                # grant/report/foreground/storage state or withdrawn binding is
                # rechecked by this exact item's existing serial runner.
                runner = BackgroundPlanRunner(owner, selected["item_id"])
                runner.cancel = stop
                result = runner.run_item(allow_background_subscription_run=True)
                runs.append({"item_id": selected["item_id"], "result": result})
                if on_observation:
                    on_observation(
                        {
                            "kind": "QUEUE_JOB_RETURNED",
                            "item_id": selected["item_id"],
                            "status": result["status"],
                            "run_sha256": result.get("background_run_sha256"),
                        }
                    )
                if result["status"] != "WAITING_APPROVAL":
                    # Even a race before claim ends this controller. Never try a
                    # different item as fallback or re-adopt a started job.
                    return receipt("STOPPED", "selected_job_requires_owner_inspection")
                if len(runs) >= maximum_jobs:
                    return receipt("FINISHED", "job_limit_reached")
            if ticks < maximum_ticks and stop.wait(poll_seconds):
                return receipt("CANCELLED", "controller_stopped")
        return receipt("FINISHED", "tick_limit_reached")
    except BaseException:
        stop.set()  # The active runner's existing cancellation/reconciliation rules apply.
        raise
