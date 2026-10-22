"""Explicit PUBLIC review mode; consent records only, with no dispatcher."""

from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from panestria.api.auth import LoopbackDenied, authorize, error_body, read_capped_body, reauthorize_mutation
from panestria.api.db import open_database, run_database
from panestria.api.routes.goals import _api
from panestria.contracts.build_review import BuildReview, BuildReviewDecision, BuildReviewReceipt, MissionCapabilities
from panestria.execution.build_review import BuildReviewService
from panestria.kernel.approvals import ApprovalService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.uow import UnitOfWork

router = APIRouter()
capabilities = APIRouter()


@capabilities.get("/v1/mission/capabilities", responses={200: {"model": MissionCapabilities}})
def capability(request: Request) -> JSONResponse:
    try:
        authorize(request, _api(request))
        body = MissionCapabilities(
            build_review_enabled=isinstance(getattr(request.app.state, "build_review", None), BuildReviewService)
        )
        return JSONResponse(body.model_dump(mode="json"), headers={"Cache-Control": "no-store"})
    except LoopbackDenied as exc:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code))


@router.get("/v1/mission/goals/{goal_id}/build-review", responses={200: {"model": BuildReview}})
async def read_review(goal_id: str, request: Request) -> JSONResponse:
    return await run_database(_review, request, goal_id, None)


@router.post("/v1/mission/goals/{goal_id}/build-review/decision", responses={200: {"model": BuildReviewReceipt}})
async def decide_review(goal_id: str, request: Request) -> JSONResponse:
    raw = await read_capped_body(request)
    if isinstance(raw, JSONResponse):
        return raw
    try:
        document = BuildReviewDecision.model_validate_json(raw)
        if (
            str(UUID(document.approval_id)) != document.approval_id
            or str(UUID(document.idempotency_key)) != document.idempotency_key
        ):
            raise ValueError
    except (ValueError, ValidationError):
        return JSONResponse(status_code=422, content=error_body("invalid_build_review_decision"))
    return await run_database(_review, request, goal_id, document)


def _review(request: Request, goal: str, document: BuildReviewDecision | None) -> JSONResponse:
    try:
        api = _api(request)
        actor = authorize(request, api)
        if str(UUID(goal)) != goal:
            raise KernelDenied("not_found")
        service = getattr(request.app.state, "build_review", None)
        if not isinstance(service, BuildReviewService):
            raise KernelDenied("not_found")
        with open_database(api.database_url) as c:
            c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            if document:
                reauthorize_mutation(request, api, c)
            view = service.inspect(UnitOfWork(c), actor, goal, locked=document is not None)
            if document is None:
                c.rollback()
                authorize(request, api)
                return JSONResponse(view.model_dump(mode="json"), headers={"Cache-Control": "no-store"})
            if (document.approval_id, document.effect_digest, document.review_sha256) != (
                view.approval_id,
                view.effect_digest,
                view.review_sha256,
            ):
                raise KernelDenied("build_review_changed")
            if not view.decision_available and view.approval_state == "PENDING":
                raise KernelDenied("build_review_not_current")
            # Recheck the same session inside the committing transaction after
            # protected I/O, not only when the HTTP request arrived.
            reauthorize_mutation(request, api, c)
            receipt = ApprovalService().decide(
                UnitOfWork(c),
                actor,
                document.approval_id,
                document.effect_digest,
                document.expected_version,
                document.decision,
                document.idempotency_key,
            )
            body = BuildReviewReceipt(**vars(receipt))
        return JSONResponse(body.model_dump(mode="json"), headers={"Cache-Control": "no-store"})
    except LoopbackDenied as exc:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code))
    except KernelDenied as exc:
        denied = exc.code in {"not_found", "public_build_review_required", "plan_local_read_denied"}
        auth = exc.code in {"unauthorized", "csrf_denied", "origin_denied", "origin_required"}
        return JSONResponse(
            status_code=404 if denied else (403 if auth else 409), content=error_body("build_review_unconfirmed")
        )
    except Exception:
        # Never echo a diff, path, credential, input document or Git stderr.
        return JSONResponse(status_code=503, content=error_body("build_review_unavailable"))
