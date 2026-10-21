"""Optional existing protected store, current PUBLIC contract, owner-scoped closed view."""

import json
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from panestria.api.auth import GoalApi, LoopbackDenied, authorize, error_body
from panestria.api.db import open_database, run_database
from panestria.api.routes.goals import _api
from panestria.contracts.build_observation import BuildObservation
from panestria.kernel.build import BuildEvidenceService
from panestria.kernel.build_progress import BuildProgressService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.uow import UnitOfWork

router = APIRouter()


@router.get("/v1/activity/goals/{goal_id}/build-progress", responses={200: {"model": BuildObservation}})
async def build_progress(goal_id: str, request: Request) -> JSONResponse:
    try:
        if str(UUID(goal_id)) != goal_id:
            raise ValueError
        api = _api(request)
        actor = authorize(request, api)
        evidence = getattr(request.app.state, "build_evidence_reader", None)
        if not isinstance(evidence, BuildEvidenceService) or not evidence.store.read_only:
            return JSONResponse(status_code=409, content=error_body("build_evidence_not_configured"))
        return await run_database(_observe, request, api, actor, goal_id, evidence)
    except LoopbackDenied as exc:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code))
    except ValueError:
        return JSONResponse(status_code=422, content=error_body("invalid_goal_id"))


def _observe(
    request: Request, api: GoalApi, actor: Actor, goal_id: str, evidence: BuildEvidenceService
) -> JSONResponse:
    try:
        with open_database(api.database_url) as c:
            c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            view = BuildProgressService().inspect(UnitOfWork(c), actor, goal_id, evidence, public_only=True)
            # Read-only projection even on exception: never commit writes from this request.
            c.rollback()
        authorize(request, api)
        current = next((p for p in view.plans if p.plan_id == view.current_plan_id), None)
        body = BuildObservation.model_validate_json(
            json.dumps(
                {
                    "owner_id": view.owner_id,
                    "project_id": view.project_id,
                    "goal_id": view.goal_id,
                    "goal_status": view.goal_status,
                    "observed_at": view.observed_at,
                    "as_of_event_seq": str(view.as_of_event_seq),
                    "contract_sha256": view.contract_sha256,
                    "required_checks_passed": view.required_checks_passed,
                    "required_checks_total": view.required_checks_total,
                    "checks": [
                        {"key": r.key, "required": r.required, "verdict": r.verdict, "report_sha256": r.report_sha256}
                        for r in view.requirements
                    ],
                    "milestones": [
                        {
                            "task_id": m.task_id,
                            "state": m.state,
                            "evidence_status": m.evidence_status,
                            "evidence_sha256": m.evidence_sha256,
                            "candidate_commit": m.candidate_commit,
                            "handoff_sha256": m.handoff_sha256,
                        }
                        for m in (current.milestones if current else ())
                    ],
                    "final_evidence_sha256": view.final_evidence_sha256,
                    "attention_reason": view.attention_reason,
                    "next_action": view.next_action,
                    "held_claims": view.repair.held_claims,
                    "unknown_invocations": view.repair.unknown_invocations,
                    "owner_merge": view.owner_merge,
                }
            )
        )
        return JSONResponse(content=body.model_dump(mode="json"), headers={"Cache-Control": "no-store"})
    except LoopbackDenied as exc:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code))
    except KernelDenied as exc:
        status = 404 if exc.code in {"not_found", "public_build_progress_required", "plan_local_read_denied"} else 409
        return JSONResponse(status_code=status, content=error_body("build_progress_unconfirmed"))
    except Exception:
        return JSONResponse(status_code=503, content=error_body("build_progress_unavailable"))
