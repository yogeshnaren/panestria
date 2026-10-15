"""Trusted verifier publication and exact merge authorization in caller transactions.

No public endpoint accepts a worker-supplied verdict bundle. The execution
controller publishes only reports it obtained from the independent verifier.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from datetime import UTC
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from panestria.contracts.acceptance import ContractRejected
from panestria.contracts.approval import ActionPreview, effect_digest, load_preview
from panestria.contracts.build import BuildEvidenceBundle, canonical_sha256
from panestria.contracts.effects import EffectIntent
from panestria.contracts.goal import GoalContract, contract_sha256, load_contract
from panestria.kernel.approvals import ApprovalService, ApprovalView
from panestria.kernel.effects import DispatchClaim
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.leases import LeaseService
from panestria.kernel.repositories.approvals import required_verdicts
from panestria.kernel.repositories.policy import require_current_policy
from panestria.kernel.repositories.tasks import append_event, lock_task
from panestria.kernel.uow import UnitOfWork


class BuildEvidenceStore:
    def __init__(self, root: Path) -> None:
        if root.is_symlink():
            raise KernelDenied("unsafe_evidence_store")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root = root.resolve()
        if self.root.stat().st_uid != os.getuid() or self.root.stat().st_mode & 0o077:
            raise KernelDenied("unsafe_evidence_store")

    def write(self, bundle: BuildEvidenceBundle) -> None:
        self.check_reports(bundle)
        self._put(bundle.canonical_bytes())

    def write_report(self, raw: bytes) -> str:
        if len(raw) > 32768:
            raise KernelDenied("build_report_limit")
        return self._put(raw)

    def _put(self, raw: bytes) -> str:
        digest = hashlib.sha256(raw).hexdigest()
        target = self.root / digest
        if target.exists() or target.is_symlink():
            self.read_blob(digest)
            return digest
        fd, name = tempfile.mkstemp(prefix=".build-", dir=self.root)
        temporary = Path(name)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
                os.fchmod(stream.fileno(), 0o400)
            try:
                os.link(temporary, target)  # Publish without replacing a concurrent finalized blob.
            except FileExistsError:
                self.read_blob(digest)
            directory = os.open(self.root, os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            temporary.unlink(missing_ok=True)
        return digest

    def read_blob(self, digest: str) -> bytes:
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise KernelDenied("invalid_evidence_hash")
        path = self.root / digest
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise KernelDenied("unsafe_build_evidence")
                raw = stream.read(256 * 1024 + 1)
        except OSError:
            raise KernelDenied("missing_build_evidence") from None
        if len(raw) > 256 * 1024 or hashlib.sha256(raw).hexdigest() != digest:
            raise KernelDenied("corrupt_build_evidence")
        return raw

    def check_reports(self, bundle: BuildEvidenceBundle) -> None:
        for check in bundle.checks:
            try:
                report = json.loads(self.read_blob(check.report_sha256))
            except ValueError:
                raise KernelDenied("corrupt_build_report") from None
            expected = {
                "check_key": check.check_key,
                "verdict": check.verdict,
                "candidate_commit": bundle.candidate_commit,
                "candidate_tree": bundle.candidate_tree,
                "base_commit": bundle.base_commit,
                "snapshot_sha256": bundle.snapshot_sha256,
                "attempt_id": bundle.attempt_id,
                "lease_epoch": bundle.lease_epoch,
                "contract_sha256": bundle.contract_sha256,
                "spec_sha256": check.spec_sha256,
                "verifier_bundle_sha256": bundle.verifier_bundle_sha256,
                "schema_version": 1,
            }
            if not isinstance(report, dict) or any(report.get(key) != value for key, value in expected.items()):
                raise KernelDenied("build_report_mismatch")

    def read(self, digest: str) -> BuildEvidenceBundle:
        raw = self.read_blob(digest)
        try:
            bundle = BuildEvidenceBundle.model_validate_json(raw)
        except ValidationError:
            raise KernelDenied("corrupt_build_evidence") from None
        if bundle.sha256() != digest:
            raise KernelDenied("noncanonical_build_evidence")
        self.check_reports(bundle)
        return bundle


def _contract(uow: UnitOfWork, actor: Actor, task_id: str) -> tuple[str, GoalContract]:
    row = uow.execute(
        "SELECT c.id::text,c.body,c.sha256,c.version,t.goal_id::text FROM panestria.task t"
        " JOIN panestria.goal_contract c ON c.id=t.contract_id JOIN panestria.goal g ON g.id=t.goal_id"
        " WHERE t.id=%s AND g.owner_id=%s AND g.project_id=%s",
        (task_id, actor.owner_id, actor.project_id),
    ).fetchone()
    if row is None:
        raise KernelDenied("not_found")
    try:
        contract = load_contract(row[1])
    except ContractRejected:
        raise KernelDenied("invalid_build_contract") from None
    if (
        contract_sha256(contract) != str(row[2]).strip()
        or contract.contract_version != row[3]
        or contract.goal_id != row[4]
        or (contract.owner_id, contract.project_id)
        != (
            actor.owner_id,
            actor.project_id,
        )
    ):
        raise KernelDenied("invalid_build_contract")
    return str(row[0]), contract


def _check_set(uow: UnitOfWork, bundle: BuildEvidenceBundle, contract: GoalContract) -> None:
    rows = uow.execute(
        "SELECT id::text,check_key,required,verifier_spec FROM panestria.acceptance_check"
        " WHERE contract_id=%s ORDER BY check_key",
        (bundle.contract_id,),
    ).fetchall()
    declared = {check.id: check for check in contract.acceptance}
    expected = []
    for check_id, key, required, spec in rows:
        check = declared.get(str(key))
        if check is None or check.required != required or check.verifier.model_dump(mode="json") != spec:
            raise KernelDenied("build_check_set_mismatch")
        expected.append((str(check_id), str(key), bool(required), canonical_sha256(spec)))
    observed = [(check.check_id, check.check_key, check.required, check.spec_sha256) for check in bundle.checks]
    if expected != observed or len(rows) != len(declared):
        raise KernelDenied("build_check_set_mismatch")


class BuildEvidenceService:
    def __init__(self, store: BuildEvidenceStore) -> None:
        self.store = store

    def publish(self, uow: UnitOfWork, actor: Actor, bundle: BuildEvidenceBundle) -> str:
        if (bundle.owner_id, bundle.project_id) != (actor.owner_id, actor.project_id):
            raise KernelDenied("not_found")
        require_current_policy(uow, actor, bundle.policy_ref)
        existing = uow.execute(
            "SELECT 1 FROM panestria.build_evidence WHERE task_id=%s AND sha256=%s", (bundle.task_id, bundle.sha256())
        ).fetchone()
        if existing is not None:
            task = lock_task(uow, actor.owner_id, actor.project_id, bundle.task_id)
            if task is None:
                raise KernelDenied("not_found")
            self.current(uow, actor, bundle.task_id, bundle.sha256())
            return bundle.sha256()  # Lost publication reply: no second record/event or state change.
        task_id = LeaseService().require_current(uow, actor, bundle.attempt_id, bundle.lease_epoch)
        if task_id != bundle.task_id:
            raise KernelDenied("build_scope_mismatch")
        contract_id, contract = _contract(uow, actor, task_id)
        if (contract_id, contract_sha256(contract), contract.contract_version, contract.autonomy_profile_ref) != (
            bundle.contract_id,
            bundle.contract_sha256,
            bundle.contract_version,
            bundle.policy_ref,
        ):
            raise KernelDenied("build_contract_mismatch")
        _check_set(uow, bundle, contract)
        # The protected, hash-checked blob is finalized before its DB reference.
        # A rolled-back transaction can leave an orphan, never a published PASS.
        self.store.write(bundle)
        digest = bundle.sha256()
        artifact_id = str(uuid4())
        uow.execute(
            "INSERT INTO panestria.artifact(id,task_id,attempt_id,kind,store_key,sha256,privacy_class,size_bytes)"
            " VALUES (%s,%s,%s,'build-evidence',%s,%s,'RESTRICTED',%s)",
            (artifact_id, task_id, bundle.attempt_id, digest, digest, len(bundle.canonical_bytes())),
        )
        uow.execute(
            "INSERT INTO panestria.build_evidence(id,task_id,attempt_id,contract_id,artifact_id,sha256,body)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)",
            (
                str(uuid4()),
                task_id,
                bundle.attempt_id,
                bundle.contract_id,
                artifact_id,
                digest,
                bundle.canonical_bytes().decode(),
            ),
        )
        for check in bundle.checks:
            uow.execute(
                "INSERT INTO panestria.check_run(id,acceptance_check_id,contract_id,task_id,attempt_id,"
                "verdict,evidence_artifact_id,candidate_sha256) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    str(uuid4()),
                    check.check_id,
                    bundle.contract_id,
                    task_id,
                    bundle.attempt_id,
                    check.verdict,
                    artifact_id,
                    digest,
                ),
            )
        passed = bundle.passed()
        uow.execute(
            "UPDATE panestria.task_attempt SET status=%s,finished_at=clock_timestamp() WHERE id=%s",
            ("SUCCEEDED" if passed else "FAILED", bundle.attempt_id),
        )
        uow.execute(
            "UPDATE panestria.task SET state=%s,row_version=row_version+1 WHERE id=%s",
            ("VERIFYING" if passed else "FAILED", task_id),
        )
        append_event(
            uow,
            goal_id=contract.goal_id,
            task_id=task_id,
            actor=actor.owner_id,
            kind="build.verified",
            payload={
                "evidence_sha256": digest,
                "candidate_commit": bundle.candidate_commit,
                "epoch": bundle.lease_epoch,
                "verdict": "PASS" if passed else "FAIL",
            },
        )
        return digest

    def current(self, uow: UnitOfWork, actor: Actor, task_id: str, digest: str) -> BuildEvidenceBundle:
        row = uow.execute(
            "SELECT b.body,b.attempt_id::text,t.lease_epoch,a.lease_epoch,a.status"
            " FROM panestria.build_evidence b JOIN panestria.task t ON t.id=b.task_id"
            " JOIN panestria.goal g ON g.id=t.goal_id JOIN panestria.task_attempt a ON a.id=b.attempt_id"
            " WHERE b.task_id=%s AND b.sha256=%s AND g.owner_id=%s AND g.project_id=%s",
            (task_id, digest, actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        bundle = self.store.read(digest)
        if json.loads(bundle.canonical_bytes()) != row[0] or (bundle.owner_id, bundle.project_id, bundle.task_id) != (
            actor.owner_id,
            actor.project_id,
            task_id,
        ):
            raise KernelDenied("corrupt_build_evidence")
        if (
            row[1] != bundle.attempt_id
            or row[2] != bundle.lease_epoch
            or row[3] != bundle.lease_epoch
            or row[4] != "SUCCEEDED"
        ):
            raise KernelDenied("stale_build_evidence")
        contract_id, contract = _contract(uow, actor, task_id)
        if (contract_id, contract_sha256(contract), contract.autonomy_profile_ref) != (
            bundle.contract_id,
            bundle.contract_sha256,
            bundle.policy_ref,
        ):
            raise KernelDenied("build_contract_mismatch")
        _check_set(uow, bundle, contract)
        verdicts = required_verdicts(uow, task_id, digest)
        if (
            not bundle.passed()
            or [key for key, _ in verdicts] != [c.check_key for c in bundle.checks if c.required]
            or any(verdict != "PASS" for _, verdict in verdicts)
        ):
            raise KernelDenied("build_checks_not_passed")
        return bundle

    def request_merge(
        self, uow: UnitOfWork, actor: Actor, task_id: str, digest: str, destination: str, *, ttl_seconds: int = 600
    ) -> ApprovalView:
        bundle = self.store.read(digest)
        require_current_policy(uow, actor, bundle.policy_ref)
        task = lock_task(uow, actor.owner_id, actor.project_id, task_id)
        if task is None:
            raise KernelDenied("not_found")
        bundle = self.current(uow, actor, task_id, digest)
        if not re.fullmatch(r"refs/heads/[A-Za-z0-9_/-]+", destination) or ".." in destination or "//" in destination:
            raise KernelDenied("invalid_destination_ref")
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 3600:
            raise KernelDenied("invalid_approval_expiry")
        expiry = uow.execute("SELECT clock_timestamp()+make_interval(secs=>%s)", (ttl_seconds,)).fetchone()
        assert expiry is not None
        preview = ActionPreview(
            action_kind="merge",
            owner_id=actor.owner_id,
            project_id=actor.project_id,
            task_id=task_id,
            contract_sha256=bundle.contract_sha256,
            contract_version=bundle.contract_version,
            policy_version=bundle.policy_ref,
            destination=f"{destination}@{bundle.candidate_commit}",
            expected_base=bundle.base_commit,
            candidate_sha256=digest,
            required_checks=[c.check_key for c in bundle.checks if c.required],
            minimum_actor_id=actor.owner_id,
            expires_at=expiry[0].astimezone(UTC).isoformat(),
        )
        return ApprovalService().request(uow, actor, preview.model_dump(mode="json"))

    def authorize_dispatch(self, uow: UnitOfWork, actor: Actor, claim: DispatchClaim) -> BuildEvidenceBundle:
        row = uow.execute(
            "SELECT a.preview,a.effect_digest,a.state,a.expires_at>clock_timestamp(),e.effect_key,"
            "e.policy_version FROM (SELECT s.*,r.policy_version FROM panestria.side_effect s"
            " JOIN panestria.approval_request r ON r.id=s.approval_request_id) e"
            " JOIN panestria.approval_request a ON a.id=e.approval_request_id"
            " WHERE e.id=%s AND a.owner_id=%s AND a.project_id=%s",
            (claim.effect_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        require_current_policy(uow, actor, str(row[5]))
        task = lock_task(uow, actor.owner_id, actor.project_id, claim.task_id)
        if task is None or task[1] not in {"VERIFYING", "WAITING_APPROVAL"}:
            raise KernelDenied("merge_not_authorized")
        effect = uow.execute(
            "SELECT state,dispatch_epoch,task_id::text,target,request_ref,request_hash,classification"
            " FROM panestria.side_effect WHERE id=%s FOR UPDATE",
            (claim.effect_id,),
        ).fetchone()
        if effect != (
            "EXECUTING",
            claim.epoch,
            claim.task_id,
            claim.target,
            claim.request_ref,
            claim.fingerprint,
            "reconcile-by-query",
        ):
            raise KernelDenied("stale_dispatch")
        # Re-read after the project/task locks: an earlier hint is not an
        # authorization snapshot when a policy revision or decision races us.
        row = uow.execute(
            "SELECT a.preview,a.effect_digest,a.state,a.expires_at>clock_timestamp(),e.effect_key,"
            "a.policy_version FROM panestria.side_effect e"
            " JOIN panestria.approval_request a ON a.id=e.approval_request_id"
            " WHERE e.id=%s AND a.owner_id=%s AND a.project_id=%s FOR UPDATE OF a",
            (claim.effect_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        preview = load_preview(row[0])
        if (preview.owner_id, preview.project_id, preview.task_id) != (actor.owner_id, actor.project_id, claim.task_id):
            raise KernelDenied("not_found")
        if (
            row[2] != "APPROVED"
            or row[3] is not True
            or preview.action_kind != "merge"
            or effect_digest(preview) != str(row[1]).strip()
        ):
            raise KernelDenied("approval_mismatch")
        approval_id = claim.request_ref.removeprefix("approval:")
        consumed = uow.execute(
            "SELECT 1 FROM panestria.approval_consumption WHERE approval_request_id=%s"
            " AND side_effect_id=%s AND effect_digest=%s",
            (approval_id, claim.effect_id, row[1]),
        ).fetchone()
        intent = EffectIntent(
            task_id=claim.task_id,
            effect_key=str(row[4]),
            target=preview.destination,
            request_ref=claim.request_ref,
            classification="reconcile-by-query",
            policy_version=preview.policy_version,
            effect_digest=str(row[1]).strip(),
        )
        if consumed is None or intent.fingerprint() != claim.fingerprint or preview.destination != claim.target:
            raise KernelDenied("approval_mismatch")
        bundle = self.current(uow, actor, claim.task_id, preview.candidate_sha256)
        if (
            preview.contract_sha256,
            preview.contract_version,
            preview.policy_version,
            preview.required_checks,
            preview.minimum_actor_id,
        ) != (
            bundle.contract_sha256,
            bundle.contract_version,
            bundle.policy_ref,
            [c.check_key for c in bundle.checks if c.required],
            actor.owner_id,
        ):
            raise KernelDenied("approval_mismatch")
        if (
            preview.expected_base != bundle.base_commit
            or preview.destination != claim.target
            or not preview.destination.endswith("@" + bundle.candidate_commit)
        ):
            raise KernelDenied("approval_mismatch")
        return bundle

    def historical_effect(self, uow: UnitOfWork, actor: Actor, claim: DispatchClaim) -> BuildEvidenceBundle:
        # Reconciliation establishes a past effect. A later policy change,
        # expired approval or cancellation must not hide an already applied CAS.
        row = uow.execute(
            "SELECT a.preview,a.effect_digest,e.effect_key,e.request_hash,e.request_ref,e.target"
            " FROM panestria.side_effect e JOIN panestria.approval_request a ON a.id=e.approval_request_id"
            " WHERE e.id=%s AND e.task_id=%s AND a.owner_id=%s AND a.project_id=%s",
            (claim.effect_id, claim.task_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        preview = load_preview(row[0])
        intent = EffectIntent(
            task_id=claim.task_id,
            effect_key=str(row[2]),
            target=str(row[5]),
            request_ref=str(row[4]),
            classification="reconcile-by-query",
            policy_version=preview.policy_version,
            effect_digest=str(row[1]).strip(),
        )
        if (str(row[3]).strip(), str(row[4]), str(row[5])) != (claim.fingerprint, claim.request_ref, claim.target) or (
            effect_digest(preview) != str(row[1]).strip() or intent.fingerprint() != claim.fingerprint
        ):
            raise KernelDenied("effect_history_mismatch")
        bundle = self.store.read(preview.candidate_sha256)
        if (bundle.owner_id, bundle.project_id, bundle.task_id) != (actor.owner_id, actor.project_id, claim.task_id):
            raise KernelDenied("not_found")
        if (
            preview.expected_base != bundle.base_commit
            or preview.destination != claim.target
            or not claim.target.endswith("@" + bundle.candidate_commit)
        ):
            raise KernelDenied("effect_history_mismatch")
        return bundle

    def complete_confirmed(self, uow: UnitOfWork, actor: Actor, task_id: str, digest: str, effect_id: str) -> None:
        hint = uow.execute(
            "SELECT c.body->>'autonomy_profile_ref' FROM panestria.task t"
            " JOIN panestria.goal_contract c ON c.id=t.contract_id WHERE t.id=%s",
            (task_id,),
        ).fetchone()
        if hint is None:
            raise KernelDenied("not_found")
        require_current_policy(uow, actor, str(hint[0]))
        task = lock_task(uow, actor.owner_id, actor.project_id, task_id)
        if task is None:
            raise KernelDenied("not_found")
        bundle = self.current(uow, actor, task_id, digest)
        effect = uow.execute(
            "SELECT state,external_ref,task_id::text FROM panestria.side_effect WHERE id=%s FOR UPDATE", (effect_id,)
        ).fetchone()
        expected = f"git-effect:{effect_id}:{bundle.candidate_commit}:{digest}"
        if effect != ("SUCCEEDED", expected, task_id):
            raise KernelDenied("merge_not_confirmed")
        if task[1] == "COMPLETED":
            return
        if task[1] not in {"VERIFYING", "RECONCILING"}:
            raise KernelDenied("illegal_transition")
        outstanding = uow.execute(
            "SELECT count(*) FROM panestria.side_effect WHERE task_id=%s AND state!='SUCCEEDED'", (task_id,)
        ).fetchone()
        if outstanding is None or outstanding[0] != 0:
            raise KernelDenied("effects_unconfirmed")
        if task[1] == "RECONCILING":
            uow.execute("UPDATE panestria.task SET state='VERIFYING',row_version=row_version+1 WHERE id=%s", (task_id,))
        uow.execute("UPDATE panestria.task SET state='COMPLETED',row_version=row_version+1 WHERE id=%s", (task_id,))
        if task[1] == "RECONCILING":
            append_event(
                uow,
                goal_id=task[0],
                task_id=task_id,
                actor=actor.owner_id,
                kind="build.verification_resumed",
                payload={"from": "RECONCILING", "to": "VERIFYING", "evidence_sha256": digest, "effect_id": effect_id},
            )
        append_event(
            uow,
            goal_id=task[0],
            task_id=task_id,
            actor=actor.owner_id,
            kind="build.completed",
            payload={"evidence_sha256": digest, "effect_id": effect_id, "epoch": bundle.lease_epoch},
        )
