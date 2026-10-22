"""Reuse canonical policy, protected evidence/Git and exact approval decisions.

No worker, certificate, native profile or effect executor is loaded here.
"""

import json
import os
import re
import time
from functools import partial
from pathlib import Path

from panestria.contracts.approval import effect_digest, load_preview
from panestria.contracts.build import canonical_sha256
from panestria.contracts.build_review import BuildReview, ReviewCheck
from panestria.contracts.goal import contract_sha256
from panestria.kernel.build import BuildEvidenceService, BuildEvidenceStore
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.plan_scope import require_final_task, task_plan_scope
from panestria.kernel.plan_store import PlanStore
from panestria.kernel.uow import UnitOfWork
from panestria.verification.git_snapshot import protected_git


class BuildReviewService:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._private_root()
        self.evidence = BuildEvidenceService(BuildEvidenceStore(root / "reports", read_only=True))

    def _private_root(self) -> None:
        if (
            not self.root.is_absolute()
            or self.root.resolve() != self.root
            or not self.root.is_dir()
            or self.root.stat().st_uid != os.getuid()
            or self.root.stat().st_mode & 0o077
        ):
            raise KernelDenied("existing_private_build_review_root_required")

    def inspect(self, uow: UnitOfWork, actor: Actor, goal: str, *, locked: bool = False) -> BuildReview:
        status, contract_id, contract = PlanStore()._goal(uow, actor, goal, read_only=not locked)
        if contract.privacy_class != "PUBLIC":
            raise KernelDenied("public_build_review_required")
        # Scope/policy/privacy are established before reading protected bytes.
        row = uow.execute(
            "SELECT a.id::text,a.state,a.effect_digest,a.preview,t.id::text,t.state,t.row_version,"
            "a.expires_at>clock_timestamp() FROM panestria.approval_request a "
            "JOIN panestria.task t ON t.id=a.task_id WHERE a.goal_id=%s AND a.owner_id=%s AND a.project_id=%s "
            "AND a.action_kind='merge' ORDER BY a.expires_at DESC,a.id DESC LIMIT 1",
            (goal, actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        approval, state, digest, body, task, task_state, version, unexpired = row
        if locked:
            # Same project->task->approval order as canonical approval decisions.
            uow.execute("SELECT 1 FROM panestria.task WHERE id=%s FOR UPDATE", (task,))
            uow.execute("SELECT 1 FROM panestria.approval_request WHERE id=%s FOR UPDATE", (approval,))
        preview = load_preview(body)
        if effect_digest(preview) != str(digest).strip() or preview.action_kind != "merge":
            raise KernelDenied("invalid_preview")
        require_final_task(uow, actor, task)
        scope = task_plan_scope(uow, actor, task)
        if scope is not None:
            current = uow.execute(
                "SELECT p.id::text FROM panestria.build_plan p "
                "JOIN panestria.build_plan_acceptance a ON a.plan_id=p.id "
                "WHERE p.goal_id=%s ORDER BY p.version DESC LIMIT 1",
                (goal,),
            ).fetchone()
            if current != (scope.plan_id,):
                raise KernelDenied("stale_build_review")
        bundle = self.evidence.current(uow, actor, task, preview.candidate_sha256)
        if (
            (preview.owner_id, preview.project_id, preview.task_id, preview.minimum_actor_id)
            != (actor.owner_id, actor.project_id, task, actor.owner_id)
            or preview.contract_sha256 != bundle.contract_sha256
            or bundle.contract_id != contract_id
            or bundle.contract_sha256 != contract_sha256(contract)
            or preview.contract_version != bundle.contract_version
            or preview.policy_version != bundle.policy_ref
            or preview.expected_base != bundle.base_commit
            or re.fullmatch(r"refs/heads/[A-Za-z0-9_/-]+@" + bundle.candidate_commit, preview.destination) is None
            or preview.required_checks != sorted(c.check_key for c in bundle.checks if c.required)
        ):
            raise KernelDenied("build_review_preview_mismatch")
        self._private_root()
        repository = self.root / "protected" / actor.owner_id / actor.project_id / "destination.git"
        if repository.resolve() != repository or not repository.is_dir():
            raise KernelDenied("build_review_repository_unavailable")
        git = partial(protected_git, repository, limit=65536, deadline=time.monotonic() + 3)
        if git(("rev-parse", "--is-bare-repository")).strip() != b"true":
            raise KernelDenied("build_review_repository_unavailable")
        if (
            git(("rev-parse", "--verify", bundle.candidate_commit + "^{tree}")).decode().strip()
            != bundle.candidate_tree
        ):
            raise KernelDenied("build_review_tree_mismatch")
        destination = preview.destination.rsplit("@", 1)[0]
        # Existing protected-merge CAS remains the final authority. This current
        # observation is an additional UI fence, never authorization to dispatch.
        base_current = git(("rev-parse", "--verify", destination)).decode().strip() == bundle.base_commit
        diff = git(
            ("diff", "--no-ext-diff", "--no-textconv", "--no-renames", bundle.base_commit, bundle.candidate_commit)
        ).decode()
        checks = tuple(
            ReviewCheck(check=c, report=self.evidence.store.read_blob(c.report_sha256).decode()) for c in bundle.checks
        )
        if sum(len(c.report.encode()) for c in checks) > 65536:
            raise KernelDenied("build_review_report_limit")
        content = {
            "owner_id": actor.owner_id,
            "project_id": actor.project_id,
            "goal_id": goal,
            "approval_id": approval,
            "effect_digest": str(digest).strip(),
            "preview": preview.model_dump(mode="json"),
            "base_commit": bundle.base_commit,
            "candidate_commit": bundle.candidate_commit,
            "candidate_tree": bundle.candidate_tree,
            "diff": diff,
            "checks": [c.model_dump(mode="json") for c in checks],
        }
        observed = uow.execute("SELECT clock_timestamp()").fetchone()
        assert observed is not None
        review = BuildReview.model_validate_json(
            json.dumps(
                {
                    **content,
                    "goal_status": status,
                    "task_state": task_state,
                    "approval_state": state,
                    "expected_version": version,
                    "observed_at": observed[0].isoformat(),
                    "review_sha256": canonical_sha256(content),
                    "decision_available": state == "PENDING"
                    and bool(unexpired)
                    and base_current
                    and status == "ACTIVE"
                    and task_state == "WAITING_APPROVAL",
                }
            )
        )
        if len(review.model_dump_json().encode()) > 240000:
            raise KernelDenied("build_review_limit")
        return review
