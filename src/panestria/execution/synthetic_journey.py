"""Synthetic R0 journey. Consent dispatches once; merge approval finalizes without another worker."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
from psycopg.errors import UniqueViolation

from panestria.brokers.harness.mock import Candidate, MockWorkerAdapter
from panestria.contracts.approval import load_preview
from panestria.contracts.goal import load_contract
from panestria.execution.crash_gate import crash_gate
from panestria.kernel.approvals import ApprovalService
from panestria.kernel.cancellation import CancellationService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.repositories.approvals import request_expired, required_verdicts
from panestria.kernel.repositories.tasks import append_event
from panestria.kernel.tasks import TaskService
from panestria.kernel.uow import UnitOfWork
from panestria.sandbox.artifact_ingress import ArtifactIngress, ArtifactRef
from panestria.sandbox.gitcmd import allow_git
from panestria.sandbox.worktree import WorkspaceManifest, WorktreeManager
from panestria.verification.nodes import NodeReport, evaluate_checks, report_output_consistent, required_passed
from panestria.verification.policy import decide_action
from panestria.verification.registry import CommandRegistry
from panestria.verification.runner import TrustedCheckRunner

Conn = psycopg.Connection[Any]
_EDIT = "tests/synthetic.txt"
_GIT = {
    "GIT_AUTHOR_NAME": "panestria-synthetic",
    "GIT_AUTHOR_EMAIL": "synthetic@panestria.invalid",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z",
    "GIT_COMMITTER_NAME": "panestria-synthetic",
    "GIT_COMMITTER_EMAIL": "synthetic@panestria.invalid",
    "GIT_COMMITTER_DATE": "2026-01-02T00:00:00Z",
}
_SCRIPT = """import os
from pathlib import Path

if os.environ.get("PANESTRIA_SECRET"):
    raise SystemExit(3)
data = Path(os.environ["PANESTRIA_CANDIDATE"]).read_bytes()
if data.startswith(b"edit:") and data.endswith(b"\\n"):
    raise SystemExit(0)
raise SystemExit(1)
"""


@dataclass(frozen=True)
class JourneySnapshot:
    goal_status: str
    task_state: str
    continuation_kind: str | None
    approval_id: str | None
    effect_digest: str | None
    expected_version: int | None
    attempts: int
    artifact_sha256: str | None
    effect_state: str | None


class SyntheticJourney:
    def __init__(self) -> None:
        self.approvals = ApprovalService()
        self.tasks = TaskService()

    def open_contract_wait(self, connection: Conn, actor: Actor, goal_id: str, sandbox: Path) -> JourneySnapshot:
        """Create the consent wait. This does not start a worker."""
        self._require_connection(connection)
        existing = self._task(connection, actor, goal_id)
        if existing is None:
            contract = self._contract(connection, actor, goal_id)
            task_id = str(uuid4())
            connection.execute(
                "INSERT INTO panestria.task (id, goal_id, contract_id, name, state)"
                " VALUES (%s, %s, %s, 'synthetic', 'CREATED')",
                (task_id, goal_id, contract[0]),
            )
            connection.commit()
            self._advance(connection, actor, task_id, "VALIDATING", "admit")
            self._checks(connection, contract)
            self._request(connection, actor, goal_id, task_id, contract, "contract_consent", "0" * 64, "contract")
        elif self._approval(connection, existing[0], "contract_consent") is None:
            contract = self._contract(connection, actor, goal_id)
            self._checks(connection, contract)
            self._request(connection, actor, goal_id, existing[0], contract, "contract_consent", "0" * 64, "contract")
        return self._snapshot(connection, actor, goal_id)

    def resume(self, connection: Conn, actor: Actor, goal_id: str, sandbox: Path) -> JourneySnapshot:
        """Continue from the durable wait. A merge wait never launches another worker."""
        self._require_connection(connection)
        snapshot = self._snapshot(connection, actor, goal_id)
        if snapshot.task_state in {"CANCELLING", "CANCELLED", "FAILED", "REJECTED", "COMPLETED"}:
            return snapshot
        if snapshot.effect_state in {"SUCCEEDED", "FAILED"}:
            return snapshot
        if snapshot.effect_state == "PREPARED":
            self._confirm(connection, actor, goal_id, sandbox, snapshot)
            return self._snapshot(connection, actor, goal_id)
        if snapshot.task_state == "WAITING_APPROVAL" and snapshot.continuation_kind == "DISPATCH":
            if self._decision(connection, snapshot) == "DENIED":
                self._close_denied(connection, actor, goal_id, snapshot)
                return self._snapshot(connection, actor, goal_id)
            if not self._approved(connection, snapshot, "contract_consent"):
                return snapshot
            self._dispatch(connection, actor, goal_id, sandbox)
            return self._snapshot(connection, actor, goal_id)
        if snapshot.continuation_kind == "MERGE" and snapshot.task_state == "WAITING_APPROVAL":
            if self._decision(connection, snapshot) == "DENIED":
                self._close_denied(connection, actor, goal_id, snapshot)
                return self._snapshot(connection, actor, goal_id)
            if not self._approved(connection, snapshot, "merge"):
                return snapshot
            self._finalize(connection, actor, goal_id, sandbox)
            return self._snapshot(connection, actor, goal_id)
        if snapshot.task_state in {"READY", "LEASED", "RUNNING", "VERIFYING"} and snapshot.attempts >= 1:
            if os.environ.get("PANESTRIA_DEFER_CONSUME") == "1":
                return snapshot
            workflow_id = self._linked_workflow(connection, actor, goal_id)
            if workflow_id is not None:
                self._consume(_database_url(connection), workflow_id)
            return self._snapshot(connection, actor, goal_id)
        return snapshot

    def _admit_attempt(self, connection: Conn, actor: Actor, goal_id: str, sandbox: Path) -> str:
        from panestria.execution.admission import DurableAdmission, SqlUnitOfWork
        from panestria.execution.dbos_runtime import open_client

        task_id, _version = self._identity(connection, actor, goal_id)
        attempt_id = self._pending_attempt(connection, task_id, sandbox)
        contract = self._contract(connection, actor, goal_id)
        connection.commit()
        workflow_id = f"admit-{attempt_id}"
        database_url = _database_url(connection)
        engine, client = open_client(database_url)
        try:
            with engine.connect() as admitted:
                DurableAdmission(client).submit(
                    SqlUnitOfWork(admitted),
                    actor,
                    task_id,
                    workflow_id,
                    attempt_id=attempt_id,
                    idempotency_key=workflow_id,
                    contract_sha256=str(contract[1]).strip(),
                )
                admitted.commit()
        finally:
            client.destroy()
            engine.dispose()
        return workflow_id

    def _pending_attempt(self, connection: Conn, task_id: str, sandbox: Path) -> str:
        epoch = _task_epoch(connection, task_id)
        found = _matching_attempt(connection, task_id, epoch)
        if found is not None:
            return found
        return _insert_attempt(
            connection,
            str(uuid4()),
            task_id,
            epoch,
            "PENDING",
            str(sandbox.resolve()),
        )

    def _linked_workflow(self, connection: Conn, actor: Actor, goal_id: str) -> str | None:
        row = connection.execute(
            "SELECT link.dbos_workflow_id FROM panestria.workflow_link AS link"
            " JOIN panestria.task AS task ON task.id = link.task_id"
            " JOIN panestria.task_attempt AS attempt ON attempt.id = link.attempt_id"
            " AND attempt.task_id = task.id AND attempt.lease_epoch = task.lease_epoch"
            " JOIN panestria.goal AS goal ON goal.id = task.goal_id"
            " WHERE goal.id = %s AND goal.owner_id = %s AND goal.project_id = %s",
            (goal_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            return None
        return str(row[0])

    def _consume(self, database_url: str, workflow_id: str) -> None:
        env = os.environ.copy()
        env["PANESTRIA_DATABASE_URL"] = database_url
        env["PANESTRIA_MODE"] = "consume"
        env["PANESTRIA_WORKFLOW_ID"] = workflow_id
        env.pop("PANESTRIA_CRASH_AT", None)
        env.pop("PANESTRIA_READY_FILE", None)
        root = Path(__file__).resolve().parents[3]
        completed = subprocess.run(
            [sys.executable, "-m", "panestria.execution.task_workflow"],
            cwd=root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise RuntimeError(detail or f"workflow consumer exited {completed.returncode}")

    def _dispatch(self, connection: Conn, actor: Actor, goal_id: str, sandbox: Path) -> None:
        task_id, version = self._identity(connection, actor, goal_id)
        approval = self._approval(connection, task_id, "contract_consent")
        if approval is None or approval[1] != "APPROVED":
            return
        self.approvals.continue_after_approval(connection_uow(connection), actor, approval[0], approval[2], version)
        connection.commit()
        workflow_id = self._admit_attempt(connection, actor, goal_id, sandbox)
        if os.environ.get("PANESTRIA_DEFER_CONSUME") == "1":
            return
        self._consume(_database_url(connection), workflow_id)

    def _finish_dispatch(self, connection: Conn, actor: Actor, goal_id: str, sandbox: Path) -> None:
        if self._approval(connection, self._identity(connection, actor, goal_id)[0], "merge") is not None:
            return
        task_id, _version = self._identity(connection, actor, goal_id)
        attempt_id = self._attempt(connection, task_id)
        manifest = self._workspace(sandbox, attempt_id, goal_id, actor.owner_id)
        candidate = self._worker(manifest, goal_id)
        if candidate.status != "CANDIDATE":
            raise KernelDenied("candidate_rejected")
        committed = self._commit_candidate(manifest)
        crash_gate("before-verify")
        file_hash = hashlib.sha256((Path(manifest.worktree) / _EDIT).read_bytes()).hexdigest()
        if snapshot_artifact(connection, task_id) is None:
            proved = self._prove(connection, actor, task_id, attempt_id, manifest, file_hash, committed)
            if not proved:
                return
        elif not _checks_passed(connection, task_id, file_hash):
            return
        self._walk(connection, actor, task_id)
        contract = self._contract(connection, actor, goal_id)
        destination = f"refs/heads/main@{committed}"
        self._request(connection, actor, goal_id, task_id, contract, "merge", file_hash, manifest.base_sha, destination)

    def _finalize(self, connection: Conn, actor: Actor, goal_id: str, sandbox: Path) -> None:
        task_id, version = self._identity(connection, actor, goal_id)
        approval = self._approval(connection, task_id, "merge")
        if approval is None or approval[1] != "APPROVED":
            return
        if not _evidence_files_match(connection, task_id, sandbox / "store"):
            return
        receipt = self.approvals.continue_after_approval(
            connection_uow(connection),
            actor,
            approval[0],
            approval[2],
            version,
        )
        connection.commit()
        current = self._snapshot(connection, actor, goal_id)
        self._confirm(connection, actor, goal_id, sandbox, current, receipt.effect_id)

    def _confirm(
        self,
        connection: Conn,
        actor: Actor,
        goal_id: str,
        sandbox: Path,
        snapshot: JourneySnapshot,
        effect_id: str | None = None,
    ) -> None:
        task_id, _version = self._identity(connection, actor, goal_id)
        approval = self._approval(connection, task_id, "merge")
        if approval is None:
            return
        preview = load_preview(self._preview_body(connection, approval[0]))
        if "@" not in preview.destination:
            self._reject_effect(connection, actor, goal_id, task_id, approval[0], approval[2], "cas-rejected")
            return
        ref, candidate = preview.destination.split("@", 1)
        current = _read_ref(sandbox, ref)
        if current != candidate and not self._effect_allowed(
            connection, actor, task_id, approval[0], preview, sandbox / "store"
        ):
            self._reject_effect(
                connection, actor, goal_id, task_id, approval[0], approval[2], "authorization-stale"
            )
            return
        crash_gate("before-effect-dispatch")
        confirmed = current == candidate or _apply_ref(sandbox, preview.expected_base, ref, candidate)
        if not confirmed or (effect_id is None and snapshot.effect_state != "PREPARED"):
            self._reject_effect(connection, actor, goal_id, task_id, approval[0], approval[2], "cas-rejected")
            return
        crash_gate("before-effect-commit")
        self._effect_state(connection, task_id, approval[0], "SUCCEEDED", "cas-confirmed")
        connection.execute(
            "UPDATE panestria.goal SET status = 'COMPLETED', updated_at = now() WHERE id = %s",
            (goal_id,),
        )
        self.tasks.transition(
            connection_uow(connection),
            actor,
            task_id,
            self._version(connection, task_id),
            _task_epoch(connection, task_id),
            "COMPLETED",
            "cas-confirmed",
            policy_version=self._policy(connection, task_id),
            correlation_id=str(uuid4()),
        )
        connection.commit()

    def _reject_effect(
        self,
        connection: Conn,
        actor: Actor,
        goal_id: str,
        task_id: str,
        approval_id: str,
        digest: str,
        note: str,
    ) -> None:
        self._effect_state(connection, task_id, approval_id, "FAILED", note)
        append_event(
            connection_uow(connection),
            goal_id=goal_id,
            task_id=task_id,
            kind="effect.rejected",
            actor=actor.owner_id,
            payload={"effect_digest": digest, "note": note},
        )
        connection.commit()

    def _effect_allowed(
        self,
        connection: Conn,
        actor: Actor,
        task_id: str,
        approval_id: str,
        preview: Any,
        store: Path,
    ) -> bool:
        if request_expired(connection_uow(connection), approval_id):
            return False
        contract = self._contract(connection, actor, self._goal_of(connection, task_id))
        if str(contract[1]).strip() != preview.contract_sha256:
            return False
        if preview.owner_id != actor.owner_id or preview.project_id != actor.project_id:
            return False
        loaded = load_contract(contract[3])
        for item in loaded.acceptance:
            verifier = item.verifier
            if verifier.type != "policy-decision" or not item.required:
                continue
            if decide_action(loaded.autonomy_profile_ref, verifier.action) != verifier.expected:
                return False
        epoch = connection.execute(
            "SELECT task.lease_epoch, attempt.lease_epoch FROM panestria.task AS task"
            " JOIN panestria.task_attempt AS attempt ON attempt.task_id = task.id"
            " WHERE task.id = %s ORDER BY attempt.attempt_number DESC LIMIT 1",
            (task_id,),
        ).fetchone()
        if epoch is None or int(epoch[0]) != int(epoch[1]):
            return False
        verdicts = required_verdicts(connection_uow(connection), task_id, preview.candidate_sha256)
        if not verdicts or any(verdict != "PASS" for _check, verdict in verdicts):
            return False
        return _evidence_files_match(connection, task_id, store)

    def _prove(
        self,
        connection: Conn,
        actor: Actor,
        task_id: str,
        attempt_id: str,
        manifest: WorkspaceManifest,
        file_hash: str,
        committed: str,
    ) -> bool:
        root = Path(manifest.root)
        source = Path(manifest.worktree) / _EDIT
        bundle = root / "protected" / "bundle"
        bundle.mkdir(parents=True, exist_ok=True)
        script = bundle / "required_check.py"
        if not script.exists():
            script.write_text(_SCRIPT)
        registry = CommandRegistry.load(bundle, _interpreter())
        contract = self._contract(connection, actor, self._goal_of(connection, task_id))
        loaded = load_contract(contract[3])
        reports = evaluate_checks(
            loaded,
            root=root,
            worktree=Path(manifest.worktree),
            base_sha=manifest.base_sha,
            registry=registry,
            runner=TrustedCheckRunner(registry),
            attempt_id=attempt_id,
            candidate_sha256=file_hash,
            candidate_path=source,
            candidate_commit=committed,
        )
        passed = required_passed(reports)
        epoch = _current_attempt_epoch(connection, task_id, attempt_id)
        published = ArtifactIngress(root / "store", Path(manifest.worktree)).finalize(source, actor.owner_id, epoch)
        if published.digest != file_hash:
            raise KernelDenied("unknown_check")
        candidate_id = str(uuid4())
        ingress = ArtifactIngress(root / "store", Path(manifest.worktree))
        ingress.insert_authorized(
            connection,
            published,
            artifact_id=candidate_id,
            task_id=task_id,
            attempt_id=attempt_id,
            owner_id=actor.owner_id,
            project_id=actor.project_id,
            kind="candidate",
        )
        for report in reports:
            evidence_id = _record_report(connection, ingress, report, task_id, attempt_id, actor)
            check_id = _check_id(connection, contract[0], report.check_id)
            connection.execute(
                "INSERT INTO panestria.check_run"
                " (id, acceptance_check_id, attempt_id, task_id, contract_id, verdict,"
                " evidence_artifact_id, candidate_sha256)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    str(uuid4()),
                    check_id,
                    attempt_id,
                    task_id,
                    contract[0],
                    report.verdict,
                    evidence_id,
                    report.candidate_sha256,
                ),
            )
        connection.execute(
            "UPDATE panestria.task_attempt SET status = %s, finished_at = now()"
            " WHERE id = %s AND status = 'RUNNING'",
            ("SUCCEEDED" if passed else "FAILED", attempt_id),
        )
        append_event(
            connection_uow(connection),
            goal_id=self._goal_of(connection, task_id),
            task_id=task_id,
            kind="evidence.recorded",
            actor=actor.owner_id,
            payload={
                "artifact_id": candidate_id,
                "artifact_sha256": published.digest,
                "verdict": "PASS" if passed else "FAIL",
            },
        )
        connection.commit()
        return passed

    def _workspace(self, sandbox: Path, attempt_id: str, seed: str, owner: str) -> WorkspaceManifest:
        sandbox.mkdir(parents=True, exist_ok=True)
        worktree = sandbox / "attempts" / attempt_id
        base_file = sandbox / "protected" / "base.txt"
        if worktree.exists() and base_file.exists():
            return WorkspaceManifest(
                str(sandbox.resolve()),
                str((sandbox / "repo").resolve()),
                str(worktree.resolve()),
                base_file.read_text().strip(),
                attempt_id,
            )
        manifest = WorktreeManager().create(sandbox, attempt_id, seed, owner=owner)
        bare = sandbox / "protected" / "dest.git"
        bare.parent.mkdir(parents=True, exist_ok=True)
        _run(["git", "clone", "--bare", manifest.repo, str(bare)])
        base_file.write_text(manifest.base_sha)
        return manifest

    def _worker(self, manifest: WorkspaceManifest, seed: str) -> Candidate | _Existing:
        target = Path(manifest.worktree) / _EDIT
        adapter = MockWorkerAdapter(manifest, "success", seed, relative=_EDIT)
        if target.is_file():
            return _Existing(target)
        adapter.start()
        return adapter.collect(timeout=10)

    def _commit_candidate(self, manifest: WorkspaceManifest) -> str:
        repo = Path(manifest.repo)
        existing = _run(["git", "-C", manifest.worktree, "rev-parse", "--verify", "synthetic-candidate"], check=False)
        if existing.returncode == 0:
            return existing.stdout.strip()
        _run(["git", "-C", manifest.worktree, "add", _EDIT])
        _run(["git", "-C", manifest.worktree, "-c", "core.hooksPath=/dev/null", "commit", "-m", "synthetic-candidate"])
        head = _run(["git", "-C", manifest.worktree, "rev-parse", "HEAD"]).stdout.strip()
        _run(["git", "-C", str(repo), "branch", "-f", "synthetic-candidate", head])
        return head

    def _cas(self, sandbox: Path, expected_base: str, destination: str) -> bool:
        if "@" not in destination:
            return False
        ref, candidate = destination.split("@", 1)
        bare = sandbox / "protected" / "dest.git"
        fetched = _run(
            [
                "git",
                "--git-dir",
                str(bare),
                "fetch",
                str(sandbox / "repo"),
                "synthetic-candidate:refs/panestria/candidate",
            ],
            check=False,
        )
        if fetched.returncode != 0:
            return False
        updated = _run(
            ["git", "--git-dir", str(bare), "update-ref", ref, candidate, expected_base],
            check=False,
        )
        return updated.returncode == 0

    def _request(
        self,
        connection: Conn,
        actor: Actor,
        goal_id: str,
        task_id: str,
        contract: tuple[str, str, int, object],
        action: str,
        candidate: str,
        expected_base: str,
        destination: str = "refs/heads/main",
    ) -> None:
        loaded = load_contract(contract[3])
        preview = {
            "action_kind": action,
            "owner_id": actor.owner_id,
            "project_id": actor.project_id,
            "task_id": task_id,
            "contract_sha256": contract[1],
            "contract_version": contract[2],
            "policy_version": loaded.autonomy_profile_ref,
            "destination": destination,
            "expected_base": expected_base,
            "candidate_sha256": candidate,
            "required_checks": sorted(item.id for item in loaded.acceptance),
            "minimum_actor_id": actor.owner_id,
            "expires_at": _stamp(timedelta(seconds=_approval_ttl())),
        }
        self.approvals.request(connection_uow(connection), actor, preview)
        connection.commit()

    def _checks(self, connection: Conn, contract: tuple[str, str, int, object]) -> None:
        loaded = load_contract(contract[3])
        for item in loaded.acceptance:
            connection.execute(
                "INSERT INTO panestria.acceptance_check"
                " (id, contract_id, check_key, description, verifier_type, verifier_spec, required)"
                " VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)"
                " ON CONFLICT (contract_id, check_key) DO NOTHING",
                (
                    str(uuid4()),
                    contract[0],
                    item.id,
                    item.description,
                    item.verifier.type,
                    _json(item.verifier.model_dump()),
                    item.required,
                ),
            )
        connection.commit()

    def _advance(self, connection: Conn, actor: Actor, task_id: str, target: str, cause: str) -> None:
        current = self._version(connection, task_id)
        self.tasks.transition(
            connection_uow(connection),
            actor,
            task_id,
            current,
            _task_epoch(connection, task_id),
            target,
            cause,
            policy_version=self._policy(connection, task_id),
            correlation_id=str(uuid4()),
        )
        connection.commit()

    def _policy(self, connection: Conn, task_id: str) -> str:
        row = connection.execute(
            "SELECT contract.body->>'autonomy_profile_ref'"
            " FROM panestria.task AS task"
            " JOIN panestria.goal_contract AS contract ON contract.id = task.contract_id"
            " WHERE task.id = %s",
            (task_id,),
        ).fetchone()
        if row is None or not isinstance(row[0], str):
            raise KernelDenied("invalid_policy")
        return row[0]

    def _walk(self, connection: Conn, actor: Actor, task_id: str) -> None:
        order = ("READY", "LEASED", "RUNNING", "VERIFYING")
        state = self._state(connection, task_id)
        if state not in order:
            return
        for target in order[order.index(state) + 1 :]:
            self._advance(connection, actor, task_id, target, "worker")

    def _attempt(self, connection: Conn, task_id: str) -> str:
        epoch = _task_epoch(connection, task_id)
        found = _matching_attempt(connection, task_id, epoch)
        if found is not None:
            return found
        return _insert_attempt(connection, str(uuid4()), task_id, epoch, "RUNNING", None)

    def _effect_state(self, connection: Conn, task_id: str, approval_id: str, state: str, note: str) -> None:
        connection.execute(
            "UPDATE panestria.side_effect SET state = %s, reconciliation_note = %s"
            " WHERE task_id = %s AND state = 'PREPARED' AND effect_key = %s",
            (state, note, task_id, f"approval:{approval_id}"),
        )

    def _snapshot(self, connection: Conn, actor: Actor, goal_id: str) -> JourneySnapshot:
        task = self._task(connection, actor, goal_id)
        if task is None:
            raise KernelDenied("not_found")
        task_id, state, version, continuation = task
        kind = "merge" if continuation == "MERGE" else "contract_consent"
        approval = self._approval(connection, task_id, kind)
        attempts = connection.execute(
            "SELECT count(*) FROM panestria.task_attempt WHERE task_id = %s",
            (task_id,),
        ).fetchone()
        artifact_sha = snapshot_artifact(connection, task_id)
        effect = None
        if approval is not None:
            effect = connection.execute(
                "SELECT state FROM panestria.side_effect"
                " WHERE task_id = %s AND effect_key = %s",
                (task_id, f"approval:{approval[0]}"),
            ).fetchone()
        goal = connection.execute("SELECT status FROM panestria.goal WHERE id = %s", (goal_id,)).fetchone()
        return JourneySnapshot(
            "" if goal is None else str(goal[0]),
            state,
            continuation,
            None if approval is None else approval[0],
            None if approval is None else approval[2],
            version,
            0 if attempts is None else int(attempts[0]),
            artifact_sha,
            None if effect is None else str(effect[0]),
        )

    def _decision(self, connection: Conn, snapshot: JourneySnapshot) -> str | None:
        if snapshot.approval_id is None:
            return None
        row = connection.execute(
            "SELECT state FROM panestria.approval_request WHERE id = %s",
            (snapshot.approval_id,),
        ).fetchone()
        if row is None:
            return None
        return str(row[0])

    def _close_denied(self, connection: Conn, actor: Actor, goal_id: str, snapshot: JourneySnapshot) -> None:
        """A denied wait is terminal. It does not start a worker or a Git effect."""
        if snapshot.expected_version is None:
            raise KernelDenied("version_conflict")
        CancellationService().cancel(
            connection_uow(connection),
            actor,
            goal_id,
            snapshot.expected_version,
            "approval-denied",
            correlation_id=str(uuid4()),
        )
        connection.commit()

    def _approved(self, connection: Conn, snapshot: JourneySnapshot, action: str) -> bool:
        if snapshot.approval_id is None:
            return False
        row = connection.execute(
            "SELECT state FROM panestria.approval_request WHERE id = %s",
            (snapshot.approval_id,),
        ).fetchone()
        return row is not None and str(row[0]) == "APPROVED" and action in {"contract_consent", "merge"}

    def _task(self, connection: Conn, actor: Actor, goal_id: str) -> tuple[str, str, int, str | None] | None:
        row = connection.execute(
            "SELECT task.id::text, task.state, task.row_version, task.continuation_kind"
            " FROM panestria.task AS task"
            " JOIN panestria.goal AS goal ON goal.id = task.goal_id"
            " WHERE task.goal_id = %s AND goal.owner_id = %s AND goal.project_id = %s",
            (goal_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            return None
        return str(row[0]), str(row[1]), int(row[2]), None if row[3] is None else str(row[3])

    def _contract(self, connection: Conn, actor: Actor, goal_id: str) -> tuple[str, str, int, object]:
        row = connection.execute(
            "SELECT contract.id::text, contract.sha256, contract.version, contract.body"
            " FROM panestria.goal_contract AS contract"
            " JOIN panestria.goal AS goal ON goal.id = contract.goal_id"
            " WHERE contract.goal_id = %s AND goal.owner_id = %s AND goal.project_id = %s",
            (goal_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        return str(row[0]), str(row[1]), int(row[2]), row[3]

    def _approval(self, connection: Conn, task_id: str, action: str) -> tuple[str, str, str] | None:
        row = connection.execute(
            "SELECT request.id::text, request.state, request.effect_digest"
            " FROM panestria.approval_request AS request"
            " LEFT JOIN panestria.task_event AS event ON event.task_id = request.task_id"
            " AND event.kind = 'approval.requested'"
            " AND event.payload->>'approval_id' = request.id::text"
            " WHERE request.task_id = %s AND request.action_kind = %s"
            " ORDER BY event.seq DESC NULLS LAST LIMIT 1",
            (task_id, action),
        ).fetchone()
        if row is None:
            return None
        return str(row[0]), str(row[1]), str(row[2])

    def _identity(self, connection: Conn, actor: Actor, goal_id: str) -> tuple[str, int]:
        task = self._task(connection, actor, goal_id)
        if task is None:
            raise KernelDenied("not_found")
        return task[0], task[2]

    def _version(self, connection: Conn, task_id: str) -> int:
        row = connection.execute("SELECT row_version FROM panestria.task WHERE id = %s", (task_id,)).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        return int(row[0])

    def _state(self, connection: Conn, task_id: str) -> str:
        row = connection.execute("SELECT state FROM panestria.task WHERE id = %s", (task_id,)).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        return str(row[0])

    def _goal_of(self, connection: Conn, task_id: str) -> str:
        row = connection.execute("SELECT goal_id::text FROM panestria.task WHERE id = %s", (task_id,)).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        return str(row[0])

    def _preview_body(self, connection: Conn, approval_id: str) -> object:
        row = connection.execute(
            "SELECT preview FROM panestria.approval_request WHERE id = %s",
            (approval_id,),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        return row[0]

    def _require_connection(self, connection: Conn) -> None:
        if not hasattr(connection, "execute") or not hasattr(connection, "commit"):
            raise KernelDenied("not_found")


def _read_ref(sandbox: Path, ref: str) -> str | None:
    bare = sandbox / "protected" / "dest.git"
    completed = _run(["git", "--git-dir", str(bare), "rev-parse", "--verify", ref], check=False)
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def _apply_ref(sandbox: Path, expected_base: str, ref: str, candidate: str) -> bool:
    current = _read_ref(sandbox, ref)
    if current == candidate:
        return True
    if current != expected_base:
        return False
    return SyntheticJourney()._cas(sandbox, expected_base, f"{ref}@{candidate}")


class _Existing:
    def __init__(self, path: Path) -> None:
        self.status = "CANDIDATE"
        self.artifact_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()


def connection_uow(connection: Conn) -> UnitOfWork:
    return UnitOfWork(connection)


def _database_url(connection: Conn) -> str:
    configured = os.environ.get("PANESTRIA_DATABASE_URL")
    if configured:
        return configured
    info = connection.info.get_parameters()
    return (
        f"postgresql://{info['user']}:{info.get('password', '')}@{info['host']}:{info['port']}/{info['dbname']}"
    )


def _checks_passed(connection: Conn, task_id: str, candidate_sha256: str) -> bool:
    verdicts = required_verdicts(connection_uow(connection), task_id, candidate_sha256)
    return bool(verdicts) and all(verdict == "PASS" for _check, verdict in verdicts)


def _approval_ttl() -> int:
    raw = os.environ.get("PANESTRIA_APPROVAL_TTL_SECONDS", "3600")
    try:
        seconds = int(raw)
    except ValueError:
        return 3600
    return seconds if seconds > 0 else 3600


def _stamp(delta: timedelta) -> str:
    return (datetime.now(timezone.utc) + delta).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")


def _json(document: object) -> str:
    import json

    return json.dumps(document, separators=(",", ":"), sort_keys=True)


def _interpreter() -> str:
    import sys

    return sys.executable


def _run(argv: list[str], check: bool = True, extra: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    allow_git(argv)
    env = os.environ.copy()
    env.update(_GIT)
    if extra:
        env.update(extra)
    completed = subprocess.run(argv, env=env, text=True, capture_output=True, check=False, timeout=30)
    if check and completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    return completed


def _evidence_files_match(connection: Conn, task_id: str, store: Path) -> bool:
    """A PASS row counts only when its report file matches the stored hash and output."""
    root = store.resolve()
    if not root.is_dir():
        return False
    rows = connection.execute(
        "SELECT artifact.sha256, artifact.size_bytes, artifact.kind"
        " FROM panestria.acceptance_check AS check_row"
        " JOIN panestria.task AS task ON task.contract_id = check_row.contract_id"
        " JOIN LATERAL ("
        " SELECT attempt.id FROM panestria.task_attempt AS attempt"
        " WHERE attempt.task_id = task.id AND attempt.lease_epoch = task.lease_epoch"
        " ORDER BY attempt.attempt_number DESC LIMIT 1"
        " ) AS current_attempt ON true"
        " JOIN LATERAL ("
        " SELECT run.evidence_artifact_id FROM panestria.check_run AS run"
        " WHERE run.acceptance_check_id = check_row.id"
        " AND run.attempt_id = current_attempt.id AND run.verdict = 'PASS'"
        " ORDER BY run.checked_at DESC LIMIT 1"
        " ) AS latest ON true"
        " JOIN panestria.artifact AS artifact ON artifact.id = latest.evidence_artifact_id"
        " WHERE task.id = %s AND check_row.required",
        (task_id,),
    ).fetchall()
    if not rows:
        return False
    for digest, size, kind in rows:
        name = str(digest).strip()
        path = (root / name).resolve()
        if path.parent != root or not path.is_file():
            return False
        data = path.read_bytes()
        if len(data) != int(size) or hashlib.sha256(data).hexdigest() != name:
            return False
        if str(kind) == "check-report" and not report_output_consistent(data):
            return False
    return True


def snapshot_artifact(connection: Conn, task_id: str) -> str | None:
    """Candidate hash for the current lease epoch. An older attempt's artifact does not count."""
    row = connection.execute(
        "SELECT artifact.sha256 FROM panestria.artifact AS artifact"
        " JOIN panestria.task AS task ON task.id = artifact.task_id"
        " JOIN panestria.task_attempt AS attempt ON attempt.id = artifact.attempt_id"
        " AND attempt.task_id = task.id AND attempt.lease_epoch = task.lease_epoch"
        " WHERE task.id = %s AND artifact.kind = 'candidate'"
        " ORDER BY artifact.created_at DESC LIMIT 1",
        (task_id,),
    ).fetchone()
    if row is None:
        return None
    return str(row[0])


def _matching_attempt(connection: Conn, task_id: str, epoch: int) -> str | None:
    row = connection.execute(
        "SELECT id::text FROM panestria.task_attempt WHERE task_id = %s AND lease_epoch = %s",
        (task_id, epoch),
    ).fetchone()
    if row is None:
        return None
    return str(row[0])


def _insert_attempt(
    connection: Conn,
    attempt_id: str,
    task_id: str,
    epoch: int,
    status: str,
    external_ref: str | None,
) -> str:
    number = connection.execute(
        "SELECT COALESCE(MAX(attempt_number), 0) + 1 FROM panestria.task_attempt WHERE task_id = %s",
        (task_id,),
    ).fetchone()
    assert number is not None
    connection.execute("SAVEPOINT attempt_insert")
    try:
        connection.execute(
            "INSERT INTO panestria.task_attempt"
            " (id, task_id, attempt_number, lease_epoch, status, adapter, external_ref)"
            " VALUES (%s, %s, %s, %s, %s, 'mock', %s)",
            (attempt_id, task_id, int(number[0]), epoch, status, external_ref),
        )
        connection.execute("RELEASE SAVEPOINT attempt_insert")
    except UniqueViolation:
        connection.execute("ROLLBACK TO SAVEPOINT attempt_insert")
        found = _matching_attempt(connection, task_id, epoch)
        if found is None:
            raise
        connection.commit()
        return found
    connection.commit()
    return attempt_id


def _task_epoch(connection: Conn, task_id: str) -> int:
    row = connection.execute(
        "SELECT lease_epoch FROM panestria.task WHERE id = %s FOR UPDATE",
        (task_id,),
    ).fetchone()
    if row is None:
        raise KernelDenied("not_found")
    return int(row[0])


def _current_attempt_epoch(connection: Conn, task_id: str, attempt_id: str) -> int:
    row = connection.execute(
        "SELECT attempt.lease_epoch FROM panestria.task_attempt AS attempt"
        " JOIN panestria.task AS task ON task.id = attempt.task_id"
        " WHERE attempt.id = %s AND attempt.task_id = %s AND attempt.lease_epoch = task.lease_epoch"
        " FOR UPDATE OF attempt",
        (attempt_id, task_id),
    ).fetchone()
    if row is None:
        raise KernelDenied("version_conflict")
    return int(row[0])


def _check_id(connection: Conn, contract_id: str, check_key: str) -> str:
    row = connection.execute(
        "SELECT id::text FROM panestria.acceptance_check WHERE contract_id = %s AND check_key = %s",
        (contract_id, check_key),
    ).fetchone()
    if row is None:
        raise KernelDenied("unknown_check")
    return str(row[0])


def _record_report(
    connection: Conn,
    ingress: ArtifactIngress,
    report: NodeReport,
    task_id: str,
    attempt_id: str,
    actor: Actor,
) -> str:
    blob = ingress.store / f"report-{report.check_id}"
    blob.write_bytes(report.canonical_bytes())
    digest = hashlib.sha256(blob.read_bytes()).hexdigest()
    target = ingress.store / digest
    if not target.exists():
        blob.replace(target)
    else:
        blob.unlink()
    artifact_id = str(uuid4())
    ingress.insert_authorized(
        connection,
        ArtifactRef(digest, str(target), _current_attempt_epoch(connection, task_id, attempt_id), actor.owner_id),
        artifact_id=artifact_id,
        task_id=task_id,
        attempt_id=attempt_id,
        owner_id=actor.owner_id,
        project_id=actor.project_id,
        kind="check-report",
    )
    return artifact_id
