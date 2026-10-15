"""Evidence does not grant permission. Route eligibility is recomputed from policy."""

from __future__ import annotations

import hashlib
import json
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from panestria.contracts.learning import ExposureObservation, RouteCandidate, UserCorrection
from panestria.contracts.policy import Action, DataLabel, PolicyRequest
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.repositories.policy import active_policy_ref, current_policy, require_current_policy
from panestria.kernel.uow import UnitOfWork
from panestria.policy.engine import PolicyEngine
from panestria.policy.labels import LabelService


class LearningRecorder:
    def _append(
        self,
        uow: UnitOfWork,
        actor: Actor,
        request_id: str,
        kind: str,
        body: dict[str, object],
    ) -> str:
        row = uow.execute(
            "SELECT a.policy_ref,a.trace_id,c.privacy_label FROM panestria.ask_request a"
            " JOIN panestria.context_pack c ON c.id=a.context_pack_id"
            " WHERE a.id=%s AND a.owner_id=%s AND a.project_id=%s",
            (request_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        identity = str(uuid4())
        uow.execute(
            "INSERT INTO panestria.learning_record"
            " (id,owner_id,project_id,request_id,trace_id,schema_version,kind,policy_ref,privacy_label,body,sha256)"
            " VALUES (%s,%s,%s,%s,%s,1,%s,%s,%s,%s,%s)",
            (identity, actor.owner_id, actor.project_id, request_id, row[1], kind, row[0], row[2], Jsonb(body), digest),
        )
        return identity

    def route(
        self,
        uow: UnitOfWork,
        actor: Actor,
        request_id: str,
        candidates: tuple[RouteCandidate, ...],
        *,
        offline: bool,
        label: DataLabel,
        request_sha256: str,
    ) -> str:
        ref = active_policy_ref(uow, actor.owner_id, actor.project_id)
        if ref is None:
            raise KernelDenied("policy_unconfigured")
        require_current_policy(uow, actor, ref)
        admitted = uow.execute(
            "SELECT a.request_sha256,c.privacy_label,a.policy_ref FROM panestria.ask_request a"
            " JOIN panestria.context_pack c ON c.id=a.context_pack_id"
            " WHERE a.id=%s AND a.owner_id=%s AND a.project_id=%s",
            (request_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if admitted is None:
            raise KernelDenied("not_found")
        if admitted[:2] != (request_sha256, label) or not offline:
            raise KernelDenied("route_context_mismatch")
        if admitted[2] != ref:
            raise KernelDenied("policy_mismatch")
        policy, decisions = current_policy(uow, actor), []
        if len(candidates) > 8 or len({c.provider for c in candidates}) != len(candidates):
            raise KernelDenied("invalid_candidates")
        for candidate in candidates:
            cloud = candidate.provider != "local-ollama"
            destination = candidate.provider if cloud else "local"
            actions: list[Action] = ["read", "external-send", "spend"] if cloud else ["read"]
            evaluations = [
                PolicyEngine().authorize(
                    PolicyRequest(
                        owner_id=actor.owner_id,
                        project_id=actor.project_id,
                        action=action,
                        label=label,
                        destination=destination,
                        effect_digest=request_sha256,
                    ),
                    policy,
                )
                for action in actions
            ]
            reasons = sorted({reason for evaluation in evaluations for reason in evaluation.reasons})
            if cloud and offline:
                reasons.append("offline_cloud_denied")
            if not candidate.available:
                reasons.append("capability_unavailable")
            eligible = (
                candidate.available and not (cloud and offline) and all(e.outcome == "PERMIT" for e in evaluations)
            )
            decisions.append(
                {
                    **candidate.model_dump(),
                    "eligible": eligible,
                    "reasons": sorted(set(reasons)),
                    "policy_sha256": policy.sha256(),
                    "risk": "local_bounded" if not cloud else "cloud_disclosure",
                }
            )
        # R1 deterministic local-first selection; suggestions/corrections do not mutate it.
        eligible_candidates = [d for d in decisions if d["eligible"]]
        selected = next((d["provider"] for d in eligible_candidates if d["provider"] == "local-ollama"), None)
        if selected is None and eligible_candidates:
            selected = eligible_candidates[0]["provider"]
        return self._append(
            uow,
            actor,
            request_id,
            "route",
            {
                "candidates": decisions,
                "selected_route": selected,
                "offline": offline,
                "label": label,
                "policy_ref": ref,
            },
        )

    def exposure(self, uow: UnitOfWork, actor: Actor, request_id: str, observation: ExposureObservation) -> str:
        scope = uow.execute(
            "SELECT c.privacy_label FROM panestria.ask_request a"
            " JOIN panestria.context_pack c ON c.id=a.context_pack_id"
            " WHERE a.id=%s AND a.owner_id=%s AND a.project_id=%s",
            (request_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if scope is None:
            raise KernelDenied("not_found")
        label = LabelService().derive([scope[0], observation.label])
        if observation.dimension == "authorized":
            if observation.destination != "local" and observation.value == "yes":
                raise KernelDenied("offline_cloud_denied")
            policy = current_policy(uow, actor)
            decision = PolicyEngine().authorize(
                PolicyRequest(
                    owner_id=actor.owner_id,
                    project_id=actor.project_id,
                    action="read" if observation.destination == "local" else "external-send",
                    label=label,
                    destination=observation.destination,
                    effect_digest=observation.payload_manifest_sha256,
                ),
                policy,
            )
            if observation.value == "yes" and decision.outcome != "PERMIT":
                raise KernelDenied("exposure_not_authorized")
        return self._append(uow, actor, request_id, "exposure", {**observation.model_dump(), "label": label})

    def outcome(self, uow: UnitOfWork, actor: Actor, request_id: str) -> str:
        row = uow.execute(
            "SELECT state,response_sha256,metadata FROM panestria.ask_request"
            " WHERE id=%s AND owner_id=%s AND project_id=%s",
            (request_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        return self._append(
            uow,
            actor,
            request_id,
            "outcome",
            {
                "execution_state": row[0],
                "output_sha256": row[1],
                "usage": row[2],
                "verifier_acceptance": None,
                "owner_acceptance": None,
                "quality": "unknown",
            },
        )

    def capture_correction(self, uow: UnitOfWork, actor: Actor, document: UserCorrection, *, consent_ref: str) -> str:
        UUID(consent_ref)  # Minted by the authenticated owner entry point, never model output.
        row = uow.execute(
            "SELECT a.state,a.response_sha256,c.privacy_label FROM panestria.ask_request a"
            " JOIN panestria.context_pack c ON c.id=a.context_pack_id"
            " WHERE a.id=%s AND a.owner_id=%s AND a.project_id=%s FOR UPDATE OF a",
            (document.request_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        if row[0] != "COMPLETED" or row[1] != document.output_sha256:
            raise KernelDenied("output_version_mismatch")
        version = uow.execute(
            "SELECT COALESCE(max(version),0)+1 FROM panestria.user_correction"
            " WHERE request_id=%s AND owner_id=%s AND project_id=%s",
            (document.request_id, actor.owner_id, actor.project_id),
        ).fetchone()
        identity, label = str(uuid4()), LabelService().derive([row[2], document.label])
        uow.execute(
            "INSERT INTO panestria.user_correction"
            " (id,owner_id,project_id,request_id,version,output_sha256,kind,body,body_sha256,privacy_label,"
            " consent_ref,consented_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                identity,
                actor.owner_id,
                actor.project_id,
                document.request_id,
                version[0] if version else 1,
                document.output_sha256,
                document.kind,
                document.body,
                hashlib.sha256(document.body.encode()).hexdigest(),
                label,
                consent_ref,
                actor.owner_id,
            ),
        )
        return identity

    def export(self, uow: UnitOfWork, actor: Actor, request_id: str) -> list[dict[str, object]]:
        if (
            uow.execute(
                "SELECT 1 FROM panestria.ask_request WHERE id=%s AND owner_id=%s AND project_id=%s",
                (request_id, actor.owner_id, actor.project_id),
            ).fetchone()
            is None
        ):
            raise KernelDenied("not_found")
        return [
            dict(id=str(r[0]), kind=r[1], schema_version=r[2], body=r[3], sha256=r[4])
            for r in uow.execute(
                "SELECT id,kind,schema_version,body,sha256 FROM panestria.learning_record"
                " WHERE request_id=%s AND owner_id=%s AND project_id=%s ORDER BY created_at,id",
                (request_id, actor.owner_id, actor.project_id),
            )
        ]
