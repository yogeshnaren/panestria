"""Manual same-request navigation over existing canonical research stages."""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Literal

from pydantic import SecretStr

from panestria.config_research import ResearchSettings
from panestria.config_synthesis import SynthesisSettings
from panestria.contracts.research_plan import packet_bytes, plan_bytes
from panestria.contracts.research_synthesis import packet_json, synthesis_json
from panestria.execution.research_brief import RetainedBrief
from panestria.execution.research_collection import OwnerCollection
from panestria.execution.research_query_plan import OwnerQueryPlan
from panestria.execution.research_review import OwnerResearchReview
from panestria.inference.runtime import MODEL, MODEL_DIGEST
from panestria.kernel.errors import KernelDenied
from panestria.kernel.uow import UnitOfWork

Action = Literal["PLAN", "COLLECT", "DRAFT", "REVIEW", "STOP"]


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class GuideStep:
    action: Action
    digest: str
    lines: tuple[str, ...] = field(repr=False)
    input_sha256: str | None = None
    queries: tuple[SecretStr, ...] = field(default=(), repr=False)


class OwnerResearchGuide:
    def __init__(self, dsn: str, synthesis: SynthesisSettings, collection: ResearchSettings | None = None):
        if collection is not None and (
            collection.owner_id != synthesis.owner_id
            or collection.project_id != synthesis.project_id
            or collection.root != synthesis.root
        ):
            raise KernelDenied("research_guide_configuration_scope_mismatch")
        self.planner = OwnerQueryPlan(dsn, synthesis)
        self.review = OwnerResearchReview(dsn, synthesis)
        self.collection = OwnerCollection(dsn, collection) if collection is not None else None

    def prepare(self, request_id: str) -> GuideStep:
        """No model, search, fetch, lifecycle mutation, private export or new authority."""
        with self.planner.connect() as c:
            current = self.planner._current(c, request_id, unstarted=False)
            brief = RetainedBrief(self.review.settings.root, self.review.actor)._inspect(
                UnitOfWork(c), request_id, current.scope.task_id
            )
            lines = [
                f"Owner {current.scope.owner_id} | project {current.scope.project_id}",
                f"Request {request_id} | task {current.scope.task_id}",
                f"Canonical state {brief.task_state} | goal {brief.goal_status}",
                "PUBLIC question (escaped JSON data): " + json.dumps(brief.question.get_secret_value()),
                "No automatic semantic qualification, task PASS or training right is granted here.",
                "Each stage needs a separate exact decision. No automatic retry or provider fallback.",
            ]
            action: Action = "STOP"
            input_sha: str | None = None
            queries: tuple[SecretStr, ...] = ()
            if brief.task_state == "CREATED" and brief.goal_status == "CREATED":
                prior = self.planner._prior(c, current)
                if prior is None:
                    packet = self.planner._current(c, request_id)
                    input_sha = _sha(packet_bytes(packet))
                    action = "PLAN"
                    lines += [
                        "Next: retain ONE local CPU query proposal, not send anything to the web.",
                        f"Pinned local model {MODEL} | bundle {MODEL_DIGEST}",
                        "At most 3 proposed queries, each 256 UTF-8 bytes; quality NOT_ASSESSED.",
                        "At most 512 output tokens / 4096 context / 60s model request; startup is separate.",
                        "Exact model question excerpt (JSON): "
                        + json.dumps(packet.question_excerpt.get_secret_value()),
                        f"Question shortened: {packet.question_shortened}. Local input SHA256 {input_sha}",
                    ]
                else:
                    receipt = self.planner._receipt(c, current, prior)
                    if receipt["status"] != "QUERY_PLAN_RETAINED":
                        lines += [f"Query plan {receipt['status']}. Inspect original intent; no redispatch offered."]
                    else:
                        plan = self.planner._read(c, current, prior, receipt)
                        queries = plan.response.queries
                        lines += [f"Retained proposal SHA256 {_sha(plan_bytes(plan))}; quality NOT_ASSESSED."]
                        lines += [
                            f"Proposed query {i} (JSON): {json.dumps(q.get_secret_value())}"
                            for i, q in enumerate(queries, 1)
                        ]
                        if self.collection is None:
                            lines += ["Collection setup is not selected. Supply --collection-config when ready."]
                        else:
                            binding = self.collection.lifecycle.load(UnitOfWork(c), self.review.actor, request_id)
                            review = self.collection.review(binding, queries)
                            input_sha = self.collection.review_digest(review)
                            action = "COLLECT"
                            lines += [
                                "Next: disclose ONLY these queries to the configured local search service.",
                                "That service may forward them upstream; actual upstream disclosure is UNKNOWN.",
                                "Returned candidate URLs may be fetched from the public web and retained locally.",
                                "Search configuration: " + json.dumps(review["settings"]["search"], sort_keys=True),
                                "Selected fetch connection: "
                                + json.dumps(review["settings"]["fetch_connection"], sort_keys=True),
                                "Fetch/source limits: " + json.dumps(review["limits"], sort_keys=True),
                                "Original contract budget: " + json.dumps(review["contract_budget"], sort_keys=True),
                                f"Selected runtime certificate {self.collection.settings.certificate_sha256}",
                                "Current certificate, policy, connection grant, lease and budgets must permit.",
                                "This review grants no policy change. Missing setup stops before outward effects.",
                                f"Exact collection review SHA256 {input_sha}",
                            ]
            elif brief.task_state == "VERIFYING" and brief.goal_status == "ACTIVE":
                lines += [
                    f"Retained excerpt records {len(brief.claims)}; semantic support NOT_ASSESSED.",
                    "Collection stop: " + str(brief.collection.stop_reason if brief.collection else "NOT_OBSERVED"),
                ]
                prior = self.review._prior(c, current.scope.task_id, request_id)
                if prior is None:
                    if not brief.claims:
                        lines += ["No retained passages. Inspect collection errors; no repeat collection offered."]
                    else:
                        draft_packet = self.review._current(c, request_id)
                        input_sha = _sha(packet_json(draft_packet))
                        action = "DRAFT"
                        lines += [
                            "Next: retain ONE unverified local CPU draft from these exact PUBLIC inputs.",
                            f"Pinned local model {MODEL} | bundle {MODEL_DIGEST}",
                            "At most 768 output tokens / 4096 context / 60s model request; startup is separate.",
                            "No search/fetch/tools or automatic support check occurs in this stage.",
                            "Exact question excerpt (JSON): "
                            + json.dumps(draft_packet.question_excerpt.get_secret_value()),
                            f"Question shortened {draft_packet.question_shortened}; "
                            f"omitted passages {draft_packet.omitted_passages}.",
                        ]
                        for passage in draft_packet.passages:
                            lines += [
                                f"{passage.citation} | snapshot {passage.reference.snapshot_id} "
                                f"| shortened {passage.shortened}",
                                "Exact model passage (JSON): " + json.dumps(passage.quote.get_secret_value()),
                                "Source limitations (JSON): " + json.dumps(passage.limitations),
                            ]
                        lines += [f"Exact draft input SHA256 {input_sha}"]
                else:
                    draft_receipt = self.review._receipt(c, current.scope.task_id, request_id, prior["synthesis_id"])
                    if draft_receipt.status != "DRAFT_RETAINED":
                        lines += [f"Draft {draft_receipt.status}. Inspect original intent; no redispatch offered."]
                    else:
                        draft = self.review._inspect(c, request_id)
                        input_sha = _sha(synthesis_json(draft))
                        action = "REVIEW"
                        lines += [
                            f"Retained unverified draft {input_sha}; claims {len(draft.response.claims)}.",
                            "Next: open the existing claim/source review terminal. No inference or egress.",
                            "Owner judgments remain OWNER_REPORTED; automatic support NOT_QUALIFIED.",
                        ]
            else:
                lines += ["No safe next action here. Inspect canonical state; never reset or retry blindly."]
            lines += [f"Next action {action}", "END OF EXACT STAGE REVIEW"]
            # Include complete visible values and original input hash; terminal filtering
            # is display-only. Confirmation never authorizes a sanitized substitute.
            digest = _sha(json.dumps([action, input_sha, lines], ensure_ascii=False).encode())
            return GuideStep(action, digest, tuple(lines), input_sha, queries)

    def execute(self, request_id: str, reviewed: GuideStep) -> Action:
        current = self.prepare(request_id)
        if current.digest != reviewed.digest or current.action != reviewed.action:
            raise KernelDenied("research_guide_review_changed")
        key = "research-guide:" + request_id  # Existing per-stage canonical idempotency, no shadow queue.
        if current.action == "PLAN":
            self.planner.plan(request_id, key, retain_local_plan=True, expected_input_sha256=current.input_sha256)
        elif current.action == "COLLECT":
            assert self.collection is not None
            self.collection.collect(
                request_id, current.queries, public_web=True, expected_review_sha256=current.input_sha256
            )
        elif current.action == "DRAFT":
            self.review.synthesize(
                request_id, key, retain_local_draft=True, expected_input_sha256=current.input_sha256
            )
        elif current.action == "STOP":
            raise KernelDenied("research_guide_no_safe_action")
        return current.action  # REVIEW opens the separate original judgment view in the CLI.
