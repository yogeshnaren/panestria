"""Bounded private reference capture from confirmed canonical Build outcomes.

The archive copies verified inputs/diff/check reports, not arbitrary native logs.
It is derived evidence: no task state, memory promotion or training authority.
"""

import hashlib
import json
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

from panestria.contracts.goal import load_contract
from panestria.contracts.invocation import InvocationBinding
from panestria.contracts.offline_result import InvocationProvenance, OfflineBuildReference, RetainedPart
from panestria.execution.proposal_demo import _lock, _private
from panestria.kernel.build import BuildEvidenceService, BuildEvidenceStore
from panestria.kernel.build_progress import BuildProgressService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.plan_store import PlanStore
from panestria.kernel.uow import UnitOfWork
from panestria.verification.git_snapshot import protected_git

if TYPE_CHECKING:
    from panestria.execution.owner_build import OwnerBuild


def _bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def capture_reference(owner: "OwnerBuild", goal: str) -> dict[str, Any]:
    payloads: dict[str, bytes] = {}
    with owner.connect() as c:
        c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        uow = UnitOfWork(c)
        progress = BuildProgressService().inspect(uow, owner.actor, goal, BuildEvidenceService(owner.reports))
        if (
            progress.goal_status != "COMPLETED"
            or progress.owner_merge != "CONFIRMED"
            or not progress.final_evidence_sha256
        ):
            raise KernelDenied("offline_reference_requires_confirmed_final_merge")
        assert progress.current_plan_id is not None
        plan = PlanStore().get(uow, owner.actor, progress.current_plan_id)
        bundle = owner.reports.read(progress.final_evidence_sha256)
        row = c.execute("SELECT body FROM panestria.goal_contract WHERE id=%s", (bundle.contract_id,)).fetchone()
        assert row is not None
        contract = load_contract(row[0])
        if contract.privacy_class != "PUBLIC":
            raise KernelDenied("offline_reference_public_only")
        payloads["contract"] = _bytes(contract.model_dump(mode="json"))
        if hashlib.sha256(payloads["contract"]).hexdigest() != progress.contract_sha256:
            raise KernelDenied("offline_reference_contract_mismatch")
        payloads["final_evidence"] = owner.reports.read_blob(progress.final_evidence_sha256)
        for i, check in enumerate(bundle.checks):
            payloads[f"check-report-{i}"] = owner.reports.read_blob(check.report_sha256)
        effects = c.execute(
            "SELECT s.id::text,s.external_ref,a.approval_request_id::text,a.effect_digest,e.confirmed_at "
            "FROM panestria.side_effect s JOIN panestria.approval_consumption a ON a.side_effect_id=s.id "
            "JOIN LATERAL (SELECT min(occurred_at) AS confirmed_at FROM panestria.task_event "
            "WHERE task_id=s.task_id AND kind='owner_build.merge_confirmed' "
            "AND payload->>'effect_id'=s.id::text) e ON e.confirmed_at IS NOT NULL "
            "WHERE s.task_id=%s AND s.state='SUCCEEDED' AND a.consumed_by=%s",
            (bundle.task_id, owner.actor.owner_id),
        ).fetchall()
        exact = [
            r
            for r in effects
            if r[1] == f"git-effect:{r[0]}:{bundle.candidate_commit}:{progress.final_evidence_sha256}"
        ]
        if len(exact) != 1:
            raise KernelDenied("offline_reference_effect_unconfirmed")
        effect = exact[0]
        rows = c.execute(
            "SELECT i.id,i.binding,i.binding_sha256,i.receipt_sha256,i.task_id::text,i.attempt_id::text "
            "FROM panestria.worker_invocation i "
            "JOIN panestria.task t ON t.id=i.task_id WHERE t.goal_id=%s ORDER BY i.created_at,i.id LIMIT 65",
            (goal,),
        ).fetchall()
        if len(rows) > 64:
            raise KernelDenied("offline_reference_provenance_limit")
        provenance = []
        for identity, document, binding_hash, receipt, task, attempt in rows:
            binding = InvocationBinding.model_validate_json(json.dumps(document))
            if binding.sha256() != str(binding_hash).strip() or (
                str(binding.scope.owner_id),
                str(binding.scope.project_id),
                binding.scope.contract_sha256,
                str(binding.scope.task_id),
                str(binding.scope.attempt_id),
            ) != (owner.actor.owner_id, owner.actor.project_id, progress.contract_sha256, task, attempt):
                raise KernelDenied("offline_reference_binding_mismatch")
            source = None
            if receipt:
                body = json.loads(owner.reports.read_blob(str(receipt).strip()))
                versions = body.get("runtime_versions", {}) if isinstance(body, dict) else {}
                candidate = versions.get("source_sha256") if isinstance(versions, dict) else None
                if isinstance(candidate, str) and re.fullmatch(r"[a-f0-9]{64}", candidate):
                    source = candidate
            provenance.append(
                InvocationProvenance(
                    invocation_id=identity,
                    binding_sha256=binding.sha256(),
                    receipt_sha256=str(receipt).strip() if receipt else None,
                    kind=binding.kind,
                    controller_source_sha256=source,
                )
            )
    payloads["diff"] = protected_git(
        owner.settings.repository,
        (
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--no-renames",
            bundle.base_commit,
            bundle.candidate_commit,
        ),
        limit=64 * 1024,
    )
    if any(len(raw) > 256 * 1024 for raw in payloads.values()) or sum(map(len, payloads.values())) > 1024 * 1024:
        raise KernelDenied("offline_reference_payload_limit")
    # Prepare all identities before writing any payload. Partial bytes after a
    # filesystem interruption remain bounded; only a complete manifest is a ref.
    chunks: dict[str, bytes] = {}
    parts = {}
    for name, raw in payloads.items():
        pieces = [raw[i : i + 32768] for i in range(0, len(raw), 32768)] or [b""]
        refs = []
        for piece in pieces:
            digest = hashlib.sha256(piece).hexdigest()
            chunks[digest] = piece
            refs.append(digest)
        parts[name] = RetainedPart(sha256=hashlib.sha256(raw).hexdigest(), size_bytes=len(raw), chunks=tuple(refs))
    manifest = OfflineBuildReference(
        owner_id=UUID(owner.actor.owner_id),
        project_id=UUID(owner.actor.project_id),
        goal_id=UUID(goal),
        task_id=UUID(bundle.task_id),
        plan_id=UUID(progress.current_plan_id),
        plan_sha256=plan.proposal.sha256(),
        contract_sha256=progress.contract_sha256,
        evidence_sha256=progress.final_evidence_sha256,
        base_commit=bundle.base_commit,
        candidate_commit=bundle.candidate_commit,
        approval_id=UUID(effect[2]),
        effect_id=UUID(effect[0]),
        effect_digest=str(effect[3]).strip(),
        confirmed_at=effect[4],
        captured_under_policy_ref=contract.autonomy_profile_ref,
        parts=parts,
        invocations=tuple(provenance),
    )
    raw_manifest = manifest.model_dump_json().encode()
    if len(raw_manifest) > 32768:
        raise KernelDenied("offline_reference_manifest_limit")
    directory = _private(owner.settings.root / "offline-results")
    store = BuildEvidenceStore(_private(directory / "blobs"))
    lock = directory / "capture.lock"
    fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    os.close(fd)
    with _lock(lock):
        existing = list(store.root.iterdir())
        new_chunks = {sha: raw for sha, raw in chunks.items() if not (store.root / sha).exists()}
        new_manifest = not (store.root / hashlib.sha256(raw_manifest).hexdigest()).exists()
        needed = sum(map(len, new_chunks.values())) + (len(raw_manifest) if new_manifest else 0)
        added_count = len(new_chunks) + int(new_manifest)
        if added_count and (
            len(existing) + added_count > 4096 or sum(p.lstat().st_size for p in existing) + needed > 8 * 1024 * 1024
        ):
            raise KernelDenied("offline_reference_history_budget_reached")
        for raw in chunks.values():
            store.write_report(raw)
        # Last publication is the only reference accepted by the offline reader.
        digest = store.write_report(raw_manifest)
    return {
        "status": "SAVED",
        "reference_sha256": digest,
        "permitted_purpose": manifest.permitted_purpose,
        "training_eligibility": manifest.training_eligibility,
        "training_export": manifest.training_export,
    }


def read_reference(root: Path, owner: str, project: str, digest: str) -> OfflineBuildReference:
    # No database, certificate, network, model or current task authority is needed
    # to check the integrity of an explicitly retained historical local reference.
    from panestria.config_build import _directory

    _directory(root / "offline-results/blobs")
    store = BuildEvidenceStore(root / "offline-results/blobs")
    manifest = OfflineBuildReference.model_validate_json(store.read_blob(digest))
    if (str(manifest.owner_id), str(manifest.project_id)) != (owner, project):
        raise KernelDenied("not_found")
    if not {"contract", "diff", "final_evidence"} <= manifest.parts.keys():
        raise KernelDenied("offline_reference_missing_parts")
    total = 0
    contents = {}
    for name, part in manifest.parts.items():
        raw = b"".join(store.read_blob(sha) for sha in part.chunks)
        total += len(raw)
        if len(raw) != part.size_bytes or hashlib.sha256(raw).hexdigest() != part.sha256 or total > 1024 * 1024:
            raise KernelDenied("offline_reference_parts_mismatch")
        contents[name] = raw
    from panestria.contracts.build import BuildEvidenceBundle

    contract = load_contract(json.loads(contents["contract"]))
    bundle = BuildEvidenceBundle.model_validate_json(contents["final_evidence"])
    if (
        manifest.parts["contract"].sha256 != manifest.contract_sha256
        or manifest.parts["final_evidence"].sha256 != manifest.evidence_sha256
        or (
            str(manifest.owner_id),
            str(manifest.project_id),
            str(manifest.goal_id),
            str(manifest.task_id),
            manifest.contract_sha256,
            manifest.base_commit,
            manifest.candidate_commit,
        )
        != (
            bundle.owner_id,
            bundle.project_id,
            contract.goal_id,
            bundle.task_id,
            bundle.contract_sha256,
            bundle.base_commit,
            bundle.candidate_commit,
        )
        or (contract.owner_id, contract.project_id, contract.privacy_class, contract.contract_version)
        != (str(manifest.owner_id), str(manifest.project_id), "PUBLIC", bundle.contract_version)
        or not bundle.passed()
        or set(contents)
        != {"contract", "diff", "final_evidence"} | {f"check-report-{i}" for i in range(len(bundle.checks))}
        or any(
            manifest.parts[f"check-report-{i}"].sha256 != check.report_sha256 for i, check in enumerate(bundle.checks)
        )
    ):
        raise KernelDenied("offline_reference_lineage_mismatch")
    return manifest
