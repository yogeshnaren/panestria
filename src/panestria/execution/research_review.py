"""Private immutable owner reviews; no model call, task PASS or training grant."""

import hashlib
from typing import Any
from uuid import uuid4

from panestria.contracts.research import ResearchArtifactRef
from panestria.contracts.research_review import OwnerDraftReview, review_json, review_template
from panestria.execution.research_synthesis import OwnerSynthesis
from panestria.kernel.errors import KernelDenied
from panestria.kernel.research_blobs import ResearchBlobStore

RECORDED = "research.synthesis.owner_review_recorded"


class OwnerResearchReview(OwnerSynthesis):
    def prepare_review(self, request_id: str) -> OwnerDraftReview:
        return review_template(self.inspect(request_id))

    def _validate_review(self, c: Any, request: str, raw: bytes) -> OwnerDraftReview:
        if type(raw) is not bytes or len(raw) > 16384:
            raise KernelDenied("owner_review_size_limit")
        review = OwnerDraftReview.model_validate_json(raw)
        draft = self._inspect(c, request)
        review.bind(draft, complete=True)
        return review

    def check_review(self, request_id: str, raw: bytes) -> str:
        with self.connect() as c:
            review = self._validate_review(c, request_id, raw)
            return hashlib.sha256(review_json(review)).hexdigest()

    def record_review(self, request_id: str, raw: bytes, digest: str, *, accept_owner_review: bool) -> dict[str, Any]:
        if accept_owner_review is not True:
            raise KernelDenied("explicit_owner_review_required")
        with self.connect() as c:
            review = self._validate_review(c, request_id, raw)
            body = review_json(review)
            if hashlib.sha256(body).hexdigest() != digest:
                raise KernelDenied("owner_review_digest_mismatch")
            draft = self._inspect(c, request_id)
            rows = c.execute(
                "SELECT payload FROM panestria.task_event WHERE task_id=%s AND kind=%s "
                "AND payload->>'request_id'=%s ORDER BY seq LIMIT 65",
                (draft.packet.scope.task_id, RECORDED, request_id),
            ).fetchall()
            for row in rows:
                if row[0]["review_sha256"] == digest:
                    self._read_review(c, request_id, row[0])
                    return {**row[0], "status": "OWNER_REVIEW_RECORDED", "replayed": True}
            if len(rows) >= 64:
                raise KernelDenied("owner_review_count_limit")
            with ResearchBlobStore(self.settings.root, self.actor) as blobs:
                stored = blobs.put(body)
            ref = ResearchArtifactRef(
                artifact_id=str(uuid4()),
                task_id=draft.packet.scope.task_id,
                sha256=stored.sha256,
                size_bytes=stored.size_bytes,
                privacy_label="RESTRICTED",  # Owner notes are never assumed to be PUBLIC source data.
            )
            c.execute(
                "INSERT INTO panestria.artifact(id,task_id,kind,store_key,sha256,privacy_class,size_bytes) "
                "VALUES(%s,%s,'research.owner-review',%s,%s,'RESTRICTED',%s)",
                (ref.artifact_id, ref.task_id, ref.sha256, ref.sha256, ref.size_bytes),
            )
            payload = {
                "request_id": request_id,
                "review_sha256": digest,
                "draft_sha256": review.draft_sha256,
                "artifact": ref.model_dump(mode="json"),
                "assessment_source": "OWNER_REPORTED",
                "automatic_semantic_support": "NOT_QUALIFIED",
                "task_completion_authority": "NONE",
                "training_authority": "NONE",
            }
            self._event(c, draft.packet, RECORDED, payload)
            return {**payload, "status": "OWNER_REVIEW_RECORDED", "replayed": False}

    def _read_review(self, c: Any, request: str, payload: dict[str, Any]) -> OwnerDraftReview:
        ref = ResearchArtifactRef.model_validate(payload["artifact"])
        draft = self._inspect(c, request)
        expected = (ref.task_id, ref.sha256, ref.size_bytes, "RESTRICTED", "research.owner-review", ref.sha256)
        row = c.execute(
            "SELECT task_id::text,sha256,size_bytes,privacy_class,kind,store_key FROM panestria.artifact WHERE id=%s",
            (ref.artifact_id,),
        ).fetchone()
        if (
            row != expected
            or ref.task_id != draft.packet.scope.task_id
            or ref.privacy_label != "RESTRICTED"
            or ref.sha256 != payload["review_sha256"]
        ):
            raise KernelDenied("owner_review_artifact_unconfirmed")
        with ResearchBlobStore(self.settings.root, self.actor) as blobs:
            raw = blobs.read(ref.sha256, expected_size=ref.size_bytes)
        review = self._validate_review(c, request, raw)
        if review_json(review) != raw or review.draft_sha256 != payload["draft_sha256"]:
            raise KernelDenied("owner_review_binding_changed")
        return review

    def inspect_review(self, request_id: str) -> OwnerDraftReview:
        with self.connect() as c:
            draft = self._inspect(c, request_id)
            row = c.execute(
                "SELECT payload FROM panestria.task_event WHERE task_id=%s AND kind=%s "
                "AND payload->>'request_id'=%s ORDER BY seq DESC LIMIT 1",
                (draft.packet.scope.task_id, RECORDED, request_id),
            ).fetchone()
            if row is None:
                raise KernelDenied("owner_review_not_recorded")
            return self._read_review(c, request_id, row[0])
