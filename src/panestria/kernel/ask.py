"""Caller-owned offline admission and receipts; only metadata survives a response."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from uuid import uuid4

from psycopg.types.json import Jsonb

from panestria.contracts.ask import AskSubmission
from panestria.contracts.inference import InferenceRequest, InferenceResult
from panestria.contracts.learning import ExposureObservation, Observation, RouteCandidate
from panestria.contracts.policy import PolicyRequest
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.repositories.policy import active_policy_ref, current_policy, require_current_policy
from panestria.kernel.uow import UnitOfWork
from panestria.learning.recorder import LearningRecorder
from panestria.memory.context import ContextCompiler, ContextPack
from panestria.policy.engine import PolicyEngine
from panestria.resources.catalog import STEWARD


@dataclass(frozen=True)
class PreparedAsk:
    submission: AskSubmission
    context: ContextPack
    inference: InferenceRequest
    policy_ref: str


class AskService:
    def __init__(self) -> None:
        self.compiler = ContextCompiler()

    def prepare(self, uow: UnitOfWork, actor: Actor, submission: AskSubmission) -> PreparedAsk:
        if submission.project_id != actor.project_id:
            raise KernelDenied("not_found")
        ref = active_policy_ref(uow, actor.owner_id, actor.project_id)
        if ref is None:
            raise KernelDenied("policy_unconfigured")
        require_current_policy(uow, actor, ref)
        prior = uow.execute(
            "SELECT request_sha256 FROM panestria.ask_request WHERE id=%s AND owner_id=%s AND project_id=%s",
            (submission.request_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if prior is not None:
            raise KernelDenied(
                "request_already_admitted" if prior[0] == submission.sha256() else "idempotency_conflict"
            )
        # Serialize matching request identities before insertion; other owner/projects use
        # different hashes. This is not the global event-order lock and involves no I/O.
        uow.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
            (f"ask:{actor.owner_id}:{actor.project_id}:{submission.request_id}",),
        )
        prior = uow.execute(
            "SELECT request_sha256 FROM panestria.ask_request WHERE id=%s AND owner_id=%s AND project_id=%s",
            (submission.request_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if prior is not None:
            raise KernelDenied(
                "request_already_admitted" if prior[0] == submission.sha256() else "idempotency_conflict"
            )
        pack = self.compiler.compose(
            uow,
            actor,
            submission.request_id,
            submission.question,
            submission.privacy_label,
            token_budget=submission.context_tokens - submission.max_output_tokens - 128,
        )
        decision = PolicyEngine().authorize(
            PolicyRequest(
                owner_id=actor.owner_id,
                project_id=actor.project_id,
                action="read",
                label=pack.label,
                destination="local",
                effect_digest=submission.sha256(),
            ),
            current_policy(uow, actor),
        )
        if decision.outcome != "PERMIT":
            raise KernelDenied("ask_policy_denied")
        trace = uuid4().hex
        inference = InferenceRequest(
            owner_id=actor.owner_id,
            project_id=actor.project_id,
            request_id=submission.request_id,
            model_ref=STEWARD.model_ref,
            prompt=pack.prompt,
            label=pack.label,
            offline=True,
            context_tokens=submission.context_tokens,
            max_output_tokens=submission.max_output_tokens,
            deadline_seconds=submission.deadline_seconds,
            trace_id=trace,
        )
        uow.execute(
            "INSERT INTO panestria.ask_request"
            " (id,owner_id,project_id,request_sha256,context_pack_id,model_ref,policy_ref,trace_id,deadline_at)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,clock_timestamp()+(%s * interval '1 second'))",
            (
                submission.request_id,
                actor.owner_id,
                actor.project_id,
                submission.sha256(),
                pack.id,
                STEWARD.model_ref,
                ref,
                trace,
                submission.deadline_seconds,
            ),
        )
        # Registry availability is a configured capability, not a prediction that
        # the model process will answer. The outcome records actual failure/success.
        candidates = tuple(
            RouteCandidate(
                provider=provider,
                model_ref=STEWARD.model_ref if provider == "local-ollama" else "not-enabled-for-ask",
                capability="chat",
                available=provider == "local-ollama",
                expected_cash=Observation(status="known", value=0, unit="cash_microusd")
                if provider == "local-ollama"
                else Observation(status="unknown", unit="cash_microusd"),
                quota_remaining=Observation(status="unknown", unit="requests"),
            )
            for provider in ("local-ollama", "openai-api", "claude-code")
        )
        LearningRecorder().route(
            uow,
            actor,
            submission.request_id,
            candidates,
            offline=True,
            label=pack.label,
            request_sha256=submission.sha256(),
        )
        evidence_prefix = {"authorized": "policy", "accessible": "context", "observed": "unobserved"}
        for dimension, value, source_kind, evidence in (
            ("authorized", "yes", "policy", current_policy(uow, actor).sha256()),
            ("accessible", "yes", "scope_manifest", pack.sha256),
            ("observed", "unknown", "os_network", pack.sha256),
        ):
            LearningRecorder().exposure(
                uow,
                actor,
                submission.request_id,
                ExposureObservation.model_validate(
                    {
                        "dimension": dimension,
                        "destination": "local",
                        "label": pack.label,
                        "payload_manifest_sha256": pack.sha256,
                        "value": value,
                        "source_kind": source_kind,
                        "content_visible": False,
                        "evidence_ref": f"{evidence_prefix[dimension]}:{evidence}",
                    }
                ),
            )
        return PreparedAsk(submission, pack, inference, ref)

    def claim(self, uow: UnitOfWork, actor: Actor, prepared: PreparedAsk) -> InferenceRequest:
        require_current_policy(uow, actor, prepared.policy_ref)
        row = uow.execute(
            "SELECT state,request_sha256,deadline_at>clock_timestamp(),context_pack_id::text,trace_id,"
            " EXTRACT(EPOCH FROM deadline_at-clock_timestamp())"
            " FROM panestria.ask_request"
            " WHERE id=%s AND owner_id=%s AND project_id=%s FOR UPDATE",
            (prepared.submission.request_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        if row[0] != "PREPARED" or row[1] != prepared.submission.sha256() or not row[2]:
            raise KernelDenied("ask_not_admissible")
        if row[3] != prepared.context.id or row[4] != prepared.inference.trace_id:
            raise KernelDenied("context_integrity_failed")
        if (
            prepared.inference.prompt,
            prepared.inference.label,
            prepared.inference.offline,
            prepared.inference.owner_id,
            prepared.inference.project_id,
            prepared.inference.request_id,
        ) != (
            prepared.context.prompt,
            prepared.context.label,
            True,
            actor.owner_id,
            actor.project_id,
            prepared.submission.request_id,
        ):
            raise KernelDenied("context_integrity_failed")
        self.compiler.revalidate(uow, actor, prepared.context)
        uow.execute(
            "UPDATE panestria.ask_request SET state='RUNNING' WHERE id=%s AND owner_id=%s AND project_id=%s",
            (prepared.submission.request_id, actor.owner_id, actor.project_id),
        )
        remaining = float(row[5])
        if remaining < 0.1:
            raise KernelDenied("ask_not_admissible")
        return prepared.inference.model_copy(
            update={
                "deadline_seconds": min(prepared.inference.deadline_seconds, remaining),
            }
        )

    def finish(self, uow: UnitOfWork, actor: Actor, request_id: str, result: InferenceResult) -> None:
        row = uow.execute(
            "SELECT state,model_ref,deadline_at>clock_timestamp() FROM panestria.ask_request"
            " WHERE id=%s AND owner_id=%s AND project_id=%s FOR UPDATE",
            (request_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        if row[0] != "RUNNING" or row[1] != result.model_ref or not row[2]:
            raise KernelDenied("ask_not_admissible")
        metadata = {
            "input_tokens": result.usage.input_tokens,
            "output_tokens": result.usage.output_tokens,
            "elapsed_seconds": result.elapsed_seconds,
            "first_token_seconds": result.first_token_seconds,
            "decode_tokens_per_second": result.decode_tokens_per_second,
            "finish_reason": result.finish_reason,
            "cash_actual_microusd": result.usage.cash_actual_microusd,
        }
        uow.execute(
            "UPDATE panestria.ask_request SET state='COMPLETED',response_sha256=%s,metadata=%s"
            " WHERE id=%s AND owner_id=%s AND project_id=%s",
            (
                hashlib.sha256(result.text.encode()).hexdigest(),
                Jsonb(metadata),
                request_id,
                actor.owner_id,
                actor.project_id,
            ),
        )

        LearningRecorder().outcome(uow, actor, request_id)

    def stop(self, uow: UnitOfWork, actor: Actor, request_id: str, *, cancelled: bool, code: str) -> str:
        if len(code) > 80 or not all(c.islower() or c.isdigit() or c == "_" for c in code):
            raise ValueError("diagnostic_code_invalid")
        row = uow.execute(
            "SELECT state FROM panestria.ask_request WHERE id=%s AND owner_id=%s AND project_id=%s FOR UPDATE",
            (request_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        if row[0] in {"COMPLETED", "UNAVAILABLE", "CANCELLED"}:
            return str(row[0])
        state = "CANCELLED" if cancelled else "UNAVAILABLE"
        uow.execute(
            "UPDATE panestria.ask_request SET state=%s,code=%s WHERE id=%s AND owner_id=%s AND project_id=%s",
            (state, code, request_id, actor.owner_id, actor.project_id),
        )
        LearningRecorder().outcome(uow, actor, request_id)
        return state

    def receipt(self, uow: UnitOfWork, actor: Actor, request_id: str) -> dict[str, object]:
        row = uow.execute(
            "SELECT a.state,a.model_ref,a.context_pack_id::text,a.trace_id,a.metadata,a.code,a.response_sha256,"
            " c.privacy_label,c.metadata FROM panestria.ask_request a"
            " JOIN panestria.context_pack c ON c.id=a.context_pack_id"
            " WHERE a.id=%s AND a.owner_id=%s AND a.project_id=%s",
            (request_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        return {
            "request_id": request_id,
            "state": row[0],
            "model_ref": row[1],
            "context_pack_id": row[2],
            "trace_id": row[3],
            "usage": row[4],
            "code": row[5],
            "response_sha256": row[6],
            "privacy_label": row[7],
            "sources": [s for s in row[8]["sources"] if s["included"]],
            "response_retained": False,
            "offline": True,
        }
