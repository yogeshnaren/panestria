"""AOS-004 worker candidate and independent checks."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import psycopg
import pytest
from psycopg.errors import CheckViolation

from panestria.brokers.harness.mock import OUTPUT_LIMIT, Candidate, MockWorkerAdapter, Observation, WorkerEvent
from panestria.execution.synthetic_journey import JourneySnapshot, SyntheticJourney, _record_report, snapshot_artifact
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.sandbox.artifact_ingress import ArtifactIngress, ArtifactRef
from panestria.sandbox.worktree import CleanupReport, WorkspaceManifest, WorktreeManager
from panestria.verification.artifacts import decide
from panestria.verification.diff import inspect_diff
from panestria.verification.nodes import NodeReport
from panestria.verification.registry import CommandRegistry
from panestria.verification.runner import TrustedCheckRunner
from stack_support import COMPOSE, DATABASE_URL

ROOT = Path(__file__).resolve().parents[2]
SEED = "alpha"


REQUIRED_SCRIPT = """\
import os
import sys
from pathlib import Path

if os.environ.get("PANESTRIA_SECRET"):
    raise SystemExit(3)
data = Path(os.environ["PANESTRIA_CANDIDATE"]).read_bytes()
if data.startswith(b"edit:") and data.endswith(b"\\n"):
    raise SystemExit(0)
raise SystemExit(1)
"""

ALLOWLIST = frozenset({"allowed.txt"})


def _properties(record_property: pytest.RecordProperty, case_id: str, lane: str) -> None:
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False)
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, text=True, capture_output=True, check=False)
    record_property("gate_case_id", case_id)
    record_property("candidate_commit", commit.stdout.strip())
    record_property("fixture_digest", hashlib.sha256(SEED.encode()).hexdigest())
    record_property("lane", lane)
    record_property("execution_mode", "OS_BOUNDARY")
    record_property("worktree_state", "dirty" if dirty.stdout.strip() else "clean")


def _success(root: Path, attempt_id: str) -> tuple[WorkspaceManifest, Candidate]:
    manifest = WorktreeManager().create(root, attempt_id, SEED)
    adapter = MockWorkerAdapter(manifest, "success", SEED)
    adapter.start()
    return manifest, adapter.collect()


def test_mock_success_and_repeat(record_property: pytest.RecordProperty, tmp_path: Path) -> None:
    _properties(record_property, "AOS-004-TC01", "integration")
    expected = hashlib.sha256(b"edit:alpha\n").hexdigest()
    first_manifest, first = _success(tmp_path / "one", "attempt-a")
    second_manifest, second = _success(tmp_path / "two", "attempt-b")
    assert first.status == "CANDIDATE"
    assert first.accepted is False
    assert first.checks == "NOT_RUN"
    assert first.artifact_sha256 == expected
    assert second.artifact_sha256 == first.artifact_sha256
    assert second.stdout_sha256 == first.stdout_sha256
    assert second.base_sha == first.base_sha
    assert Path(first_manifest.worktree).is_relative_to(tmp_path)
    assert (Path(first_manifest.worktree) / "allowed.txt").read_text() == "edit:alpha\n"

    with pytest.raises(ValueError, match="attempt id"):
        WorktreeManager().create(tmp_path / "bad", "../outside", SEED)

    escaped = WorktreeManager().create(tmp_path / "escape", "attempt-c", SEED)
    bad = MockWorkerAdapter(escaped, "bad_path", SEED)
    bad.start()
    rejected = bad.collect()
    assert rejected.status == "REJECTED"
    assert rejected.accepted is False
    assert (tmp_path / "escape" / "outside.txt").is_file()

    hung_manifest = WorktreeManager().create(tmp_path / "hung", "attempt-d", SEED)
    hung = MockWorkerAdapter(hung_manifest, "hung", SEED)
    hung.start()
    assert hung.observe() == Observation(False, False, True)
    hung.cancel()
    cancelled = hung.observe()
    assert cancelled.cancellation_requested is True
    assert cancelled.terminated is True
    assert cancelled.running is False
    assert hung.collect().status == "CANCELLED"

    crashed_manifest = WorktreeManager().create(tmp_path / "crash", "attempt-e", SEED)
    crashed = MockWorkerAdapter(crashed_manifest, "crash", SEED)
    crashed.start()
    crash_result = crashed.collect()
    assert crash_result.status == "CRASHED"
    assert crash_result.accepted is False

    verbose_manifest = WorktreeManager().create(tmp_path / "verbose", "attempt-f", SEED)
    verbose = MockWorkerAdapter(verbose_manifest, "verbose", SEED)
    verbose.start()
    bounded = verbose.collect()
    assert bounded.truncated is True
    assert bounded.accepted is False
    assert bounded.stdout_sha256 == hashlib.sha256(b"x" * OUTPUT_LIMIT).hexdigest()


def _bundle(root: Path) -> CommandRegistry:
    protected = root / "protected"
    protected.mkdir(parents=True)
    (protected / "required_check.py").write_text(REQUIRED_SCRIPT)
    return CommandRegistry.load(protected, sys.executable)


def test_bad_path_and_tampered_checks(
    record_property: pytest.RecordProperty,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _properties(record_property, "AOS-004-TC02", "security")
    monkeypatch.setenv("PANESTRIA_SECRET", "synthetic-sentinel")
    root = tmp_path / "checked"
    registry = _bundle(root)
    manifest, candidate = _success(root, "attempt-ok")
    report = inspect_diff(Path(manifest.root), Path(manifest.worktree), ALLOWLIST)
    assert report.ok is True
    assert report.changed == ("allowed.txt",)
    published = ArtifactIngress(root / "store", Path(manifest.worktree)).finalize(
        Path(manifest.worktree) / "allowed.txt",
        "synthetic-owner",
        1,
    )
    assert published.digest == candidate.artifact_sha256
    assert not Path(published.path).resolve().is_relative_to(Path(manifest.worktree))
    command = registry.resolve("synthetic-required")
    assert command.argv[0] == sys.executable
    assert Path(command.argv[-1]).is_relative_to(root / "protected")
    result = TrustedCheckRunner(registry).run("synthetic-required", Path(published.path), 5)
    assert result.verdict == "PASS"
    assert decide(report, (result,), ("synthetic-required",), True).verdict == "PASS"

    (Path(manifest.worktree) / "other.txt").write_text("off-scope\n")
    off_scope = inspect_diff(Path(manifest.root), Path(manifest.worktree), ALLOWLIST)
    assert off_scope.ok is False
    assert "other.txt" in off_scope.denied
    assert decide(off_scope, (result,), ("synthetic-required",), True).verdict == "FAIL"

    claimed = WorktreeManager().create(tmp_path / "narrative", "attempt-narrative", SEED)
    narrator = MockWorkerAdapter(claimed, "bad-test", SEED)
    narrator.start()
    narrative = narrator.collect()
    assert narrative.status == "CANDIDATE"
    assert narrative.accepted is False
    assert narrative.checks == "NOT_RUN"
    assert narrative.stdout_sha256 == hashlib.sha256(b"tests pass\n").hexdigest()
    claimed_file = Path(claimed.worktree) / "allowed.txt"
    assert claimed_file.read_text(encoding="utf-8") == "tests pass\n"
    failed = TrustedCheckRunner(registry).run("synthetic-required", claimed_file, 5)
    assert failed.verdict == "FAIL"
    assert failed.reason == "exit_1"
    narrative_diff = inspect_diff(Path(claimed.root), Path(claimed.worktree), ALLOWLIST)
    assert decide(narrative_diff, (failed,), ("synthetic-required",), True).verdict == "FAIL"

    corrupt = WorktreeManager().create(tmp_path / "corrupt", "attempt-corrupt", SEED)
    liar = MockWorkerAdapter(corrupt, "artifact-corrupt", SEED)
    liar.start()
    lied = liar.collect()
    corrupt_file = Path(corrupt.worktree) / "allowed.txt"
    actual = hashlib.sha256(corrupt_file.read_bytes()).hexdigest()
    assert lied.artifact_sha256 == hashlib.sha256(f"edit:{SEED}\n".encode()).hexdigest()
    assert lied.artifact_sha256 != actual
    assert lied.status == "CANDIDATE"
    assert lied.accepted is False
    assert lied.checks == "NOT_RUN"
    corrupt_check = TrustedCheckRunner(registry).run("synthetic-required", corrupt_file, 5)
    assert corrupt_check.verdict == "FAIL"
    corrupt_store = ArtifactIngress(tmp_path / "corrupt-store", Path(corrupt.worktree))
    published_corrupt = corrupt_store.finalize(corrupt_file, "synthetic-owner", 1)
    assert published_corrupt.digest == actual
    forged = ArtifactRef(lied.artifact_sha256, published_corrupt.path, 1, "synthetic-owner")
    assert corrupt_store.recheck(forged) is False

    escaped = WorktreeManager().create(tmp_path / "escape", "attempt-escape", SEED)
    outside = MockWorkerAdapter(escaped, "bad-path", SEED)
    outside.start()
    assert outside.collect().status == "REJECTED"
    escaped_diff = inspect_diff(Path(escaped.root), Path(escaped.worktree), ALLOWLIST)
    assert escaped_diff.ok is False
    assert "outside.txt" in escaped_diff.denied

    linked = WorktreeManager().create(tmp_path / "link", "attempt-link", SEED)
    target = tmp_path / "secret-target.txt"
    target.write_text("edit:alpha\n")
    allowed = Path(linked.worktree) / "allowed.txt"
    allowed.symlink_to(target)
    linked_diff = inspect_diff(Path(linked.root), Path(linked.worktree), ALLOWLIST)
    assert linked_diff.ok is False
    assert "allowed.txt" in linked_diff.denied
    with pytest.raises(ValueError, match="symlink"):
        ArtifactIngress(tmp_path / "link" / "store", Path(linked.worktree)).finalize(allowed, "synthetic-owner", 1)
    assert TrustedCheckRunner(registry).run("synthetic-required", allowed, 5).reason == "symlink"

    (Path(manifest.worktree) / "always_pass.py").write_text("raise SystemExit(0)\n")
    with pytest.raises(PermissionError, match="always_pass"):
        registry.add_worker_command("always_pass", (sys.executable, str(Path(manifest.worktree) / "always_pass.py")))
    with pytest.raises(KeyError, match="always_pass"):
        registry.resolve("always_pass")
    assert tuple(item.ref for item in registry.required()) == ("synthetic-required",)

    script = root / "protected" / "required_check.py"
    script.write_text("from pathlib import Path\nPath('ran.txt').write_text('x')\nraise SystemExit(0)\n")
    tampered = TrustedCheckRunner(registry).run("synthetic-required", Path(published.path), 5)
    assert tampered.verdict == "FAIL"
    assert tampered.reason == "bundle_tampered"
    assert not (root / "protected" / "ran.txt").exists()
    assert decide(report, (tampered,), ("synthetic-required",), True).verdict == "FAIL"


def _watch(root: Path, attempt: str, mode: str, timeout: float) -> tuple[MockWorkerAdapter, Candidate]:
    manifest = WorktreeManager().create(root, attempt, SEED)
    adapter = MockWorkerAdapter(manifest, mode, SEED)
    adapter.start()
    result = adapter.collect(timeout)
    assert adapter._process is not None
    with pytest.raises(ProcessLookupError):
        os.killpg(adapter._process.pid, 0)
    return adapter, result


def test_hung_process_and_output(record_property: pytest.RecordProperty, tmp_path: Path) -> None:
    _properties(record_property, "AOS-004-TC03", "chaos")
    _first_adapter, first = _watch(tmp_path / "silent-a", "attempt-silent-a", "hung", 0.4)
    _second_adapter, second = _watch(tmp_path / "silent-b", "attempt-silent-b", "hung", 0.4)
    assert first.status == "TIMED_OUT"
    assert first.accepted is False
    assert first.checks == "NOT_RUN"
    assert first.truncated is False
    assert (first.status, first.accepted, first.checks, first.stdout_sha256) == (
        second.status,
        second.accepted,
        second.checks,
        second.stdout_sha256,
    )
    _done_adapter, claimed = _watch(tmp_path / "claimed", "attempt-claimed", "false_done", 0.4)
    assert claimed.status == "TIMED_OUT"
    assert claimed.accepted is False
    assert claimed.stdout_sha256 == hashlib.sha256(b"done\n").hexdigest()
    _timeout_adapter, timed = _watch(tmp_path / "timeout", "attempt-timeout", "timeout", 0.4)
    assert timed.status == "TIMED_OUT"
    assert timed.accepted is False
    assert timed.checks == "NOT_RUN"
    _flood_adapter, flooded = _watch(tmp_path / "flood", "attempt-flood", "flood", 0.5)
    assert flooded.status == "TIMED_OUT"
    assert flooded.accepted is False
    assert flooded.truncated is True
    assert flooded.stdout_sha256 == hashlib.sha256(b"x" * OUTPUT_LIMIT).hexdigest()




OWNER = "00000000-0000-4000-8000-000000000002"
PROJECT = "00000000-0000-4000-8000-000000000003"
GOAL = "00000000-0000-4000-8000-000000000001"
CONTRACT = "00000000-0000-4000-8000-000000000040"
TASK_STORE = "00000000-0000-4000-8000-0000000000f1"
ATTEMPT_STORE = "00000000-0000-4000-8000-0000000000f2"
ARTIFACT = "00000000-0000-4000-8000-0000000000f3"
CHECK = "00000000-0000-4000-8000-0000000000f4"


def _database() -> None:
    subprocess.run([*COMPOSE, "down", "-v"], check=False)
    up = subprocess.run(
        [*COMPOSE, "up", "-d", "--wait"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert up.returncode == 0, up.stderr
    upgraded = subprocess.run(
        ["uv", "run", "--frozen", "alembic", "-c", "migrations/alembic.ini", "upgrade", "head"],
        cwd=ROOT,
        env={**os.environ, "PANESTRIA_DATABASE_URL": DATABASE_URL},
        text=True,
        capture_output=True,
        check=False,
    )
    assert upgraded.returncode == 0, upgraded.stderr


def _seed_store_task(connection: psycopg.Connection[object]) -> None:
    digest = "ab" * 32
    connection.execute("INSERT INTO panestria.principal (id, display_name) VALUES (%s, 'owner')", (OWNER,))
    connection.execute("INSERT INTO panestria.project (id, owner_id) VALUES (%s, %s)", (PROJECT, OWNER))
    connection.execute(
        "INSERT INTO panestria.goal (id, owner_id, project_id, intent, status)"
        " VALUES (%s, %s, %s, 'synthetic', 'CREATED')",
        (GOAL, OWNER, PROJECT),
    )
    connection.execute(
        "INSERT INTO panestria.goal_contract (id, goal_id, version, body, sha256)"
        " VALUES (%s, %s, 1, %s::jsonb, %s)",
        (CONTRACT, GOAL, '{"autonomy_profile_ref":"synthetic-approve-first-v1"}', digest),
    )
    connection.execute(
        "INSERT INTO panestria.task (id, goal_id, contract_id, name, state, lease_epoch)"
        " VALUES (%s, %s, %s, 'store', 'CREATED', 1)",
        (TASK_STORE, GOAL, CONTRACT),
    )
    connection.execute(
        "INSERT INTO panestria.task_attempt (id, task_id, attempt_number, lease_epoch, status, adapter)"
        " VALUES (%s, %s, 1, 1, 'RUNNING', 'synthetic')",
        (ATTEMPT_STORE, TASK_STORE),
    )
    connection.execute(
        "INSERT INTO panestria.acceptance_check"
        " (id, contract_id, check_key, description, verifier_type, verifier_spec)"
        " VALUES (%s, %s, 'synthetic-required', 'required', 'trusted-command-ref',"
        " '{\"type\":\"trusted-command-ref\"}'::jsonb)",
        (CHECK, CONTRACT),
    )


def _race_epoch(ingress: ArtifactIngress, kept: ArtifactRef) -> None:
    import threading
    import time

    held = threading.Event()
    release = threading.Event()
    errors: list[str] = []

    def hold() -> None:
        with psycopg.connect(DATABASE_URL) as locked:
            locked.execute("SELECT id FROM panestria.task_attempt WHERE id = %s FOR UPDATE", (ATTEMPT_STORE,))
            held.set()
            assert release.wait(5)
            locked.execute("UPDATE panestria.task_attempt SET lease_epoch = 2 WHERE id = %s", (ATTEMPT_STORE,))
            locked.commit()

    def publish() -> None:
        assert held.wait(5)
        with psycopg.connect(DATABASE_URL) as racing:
            try:
                ingress.record_ref(
                    racing,
                    kept,
                    artifact_id="00000000-0000-4000-8000-0000000000fb",
                    task_id=TASK_STORE,
                    attempt_id=ATTEMPT_STORE,
                    owner_id=OWNER,
                    project_id=PROJECT,
                )
                racing.commit()
            except ValueError as exc:
                errors.append(str(exc))
                racing.rollback()

    holder = threading.Thread(target=hold)
    racer = threading.Thread(target=publish)
    holder.start()
    assert held.wait(5)
    racer.start()
    time.sleep(0.2)
    release.set()
    holder.join(5)
    racer.join(5)
    assert errors == ["stale epoch"]


def test_artifact_partial_publish(record_property: pytest.RecordProperty, tmp_path: Path) -> None:
    _properties(record_property, "AOS-004-TC04", "chaos")
    _database()
    try:
        manifest = WorktreeManager().create(tmp_path / "store-case", "attempt-store", SEED)
        worktree = Path(manifest.worktree)
        ingress = ArtifactIngress(tmp_path / "blob-store", worktree)
        partial_source = worktree / "partial.txt"
        partial_source.write_bytes(b"partial\n")
        partial = ingress.stage_partial(partial_source)
        assert partial.name.startswith(".")
        assert not (ingress.store / hashlib.sha256(b"partial\n").hexdigest()).exists()
        orphan_source = worktree / "orphan.txt"
        orphan_source.write_bytes(b"orphan\n")
        orphan = ingress.finalize(orphan_source, "synthetic-owner", 1)
        kept_source = worktree / "kept.txt"
        kept_source.write_bytes(b"kept\n")
        kept = ingress.finalize(kept_source, OWNER, 1)
        foreign_source = worktree / "foreign.txt"
        foreign_source.write_bytes(b"foreign\n")
        foreign = ingress.finalize(foreign_source, "foreign-synthetic-actor", 0)
        with psycopg.connect(DATABASE_URL) as connection:
            _seed_store_task(connection)
            connection.commit()
            with pytest.raises(ValueError, match="scope mismatch"):
                ingress.record_ref(
                    connection,
                    foreign,
                    artifact_id="00000000-0000-4000-8000-0000000000f7",
                    task_id=TASK_STORE,
                    attempt_id=ATTEMPT_STORE,
                    owner_id=OWNER,
                    project_id=PROJECT,
                )
            with pytest.raises(ValueError, match="scope mismatch"):
                ingress.record_ref(
                    connection,
                    kept,
                    artifact_id="00000000-0000-4000-8000-0000000000fa",
                    task_id=TASK_STORE,
                    attempt_id=ATTEMPT_STORE,
                    owner_id=OWNER,
                    project_id="00000000-0000-4000-8000-000000000099",
                )
            stale = ArtifactRef(kept.digest, kept.path, 0, OWNER)
            with pytest.raises(ValueError, match="stale epoch"):
                ingress.record_ref(
                    connection,
                    stale,
                    artifact_id="00000000-0000-4000-8000-0000000000f8",
                    task_id=TASK_STORE,
                    attempt_id=ATTEMPT_STORE,
                    owner_id=OWNER,
                    project_id=PROJECT,
                )
            connection.execute(
                "UPDATE panestria.task_attempt SET status = 'SUCCEEDED' WHERE id = %s",
                (ATTEMPT_STORE,),
            )
            with pytest.raises(ValueError, match="terminal attempt"):
                ingress.record_ref(
                    connection,
                    kept,
                    artifact_id="00000000-0000-4000-8000-0000000000f9",
                    task_id=TASK_STORE,
                    attempt_id=ATTEMPT_STORE,
                    owner_id=OWNER,
                    project_id=PROJECT,
                )
            connection.execute(
                "UPDATE panestria.task_attempt SET status = 'RUNNING' WHERE id = %s",
                (ATTEMPT_STORE,),
            )
            ingress.record_ref(
                connection,
                kept,
                artifact_id=ARTIFACT,
                task_id=TASK_STORE,
                attempt_id=ATTEMPT_STORE,
                owner_id=OWNER,
                project_id=PROJECT,
            )
            connection.commit()
            _race_epoch(ingress, kept)
            published = connection.execute("SELECT count(*) FROM panestria.artifact").fetchone()
            assert published is not None and int(published[0]) == 1
            kept_path = Path(kept.path)
            kept_path.write_bytes(b"tampered\n")
            assert ingress.recheck(kept) is False
            with pytest.raises(ValueError, match="does not match"):
                ingress.record_ref(
                    connection,
                    kept,
                    artifact_id="00000000-0000-4000-8000-0000000000f5",
                    task_id=TASK_STORE,
                    attempt_id=ATTEMPT_STORE,
                    owner_id=OWNER,
                    project_id=PROJECT,
                )
            with pytest.raises(CheckViolation):
                connection.execute(
                    "INSERT INTO panestria.check_run"
                    " (id, acceptance_check_id, attempt_id, task_id, contract_id, verdict)"
                    " VALUES (%s, %s, %s, %s, %s, 'PASS')",
                    ("00000000-0000-4000-8000-0000000000f6", CHECK, ATTEMPT_STORE, TASK_STORE, CONTRACT),
                )
            connection.rollback()
            referenced = {row[0].strip() for row in connection.execute("SELECT sha256 FROM panestria.artifact")}
            assert referenced == {kept.digest}
            passes = connection.execute("SELECT count(*) FROM panestria.check_run WHERE verdict = 'PASS'").fetchone()
            assert passes is not None and passes[0] == 0
        target = tmp_path / "outside-target.txt"
        target.write_text("stay\n")
        link = ingress.store / "linked"
        link.symlink_to(target)
        removed = ingress.cleanup_orphans({kept.digest})
        assert partial.name in removed
        assert orphan.digest in removed
        assert not partial.exists()
        assert not Path(orphan.path).exists()
        assert kept_path.exists()
        assert link.is_symlink()
        assert target.read_text() == "stay\n"
        assert ingress.recheck(kept) is False
    finally:
        subprocess.run([*COMPOSE, "down", "-v"], check=False)


def test_expired_worktree_cleanup_does_not_follow_symlinks(
    record_property: pytest.RecordProperty,
    tmp_path: Path,
) -> None:
    _properties(record_property, "AOS-004-TC04", "chaos")
    manager = WorktreeManager()
    root = tmp_path / "sandbox"
    manifest = manager.create(root, "attempt-live", SEED, owner="owner-a", ttl_seconds=10, now=1000)
    assert manifest.owner == "owner-a"
    assert manifest.ttl_seconds == 10
    assert manifest.disk_bytes > 0
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("stay\n")
    worktree = Path(manifest.worktree)
    (worktree / "escape").symlink_to(outside, target_is_directory=True)
    retained = manager.cleanup(root, now=1005, live_attempts={"attempt-live"})
    assert retained == (
        CleanupReport("attempt-live", "retained", "owner-a", manifest.disk_bytes, "live"),
    )
    assert secret.read_text() == "stay\n"
    store = tmp_path / "store"
    removed = manager.cleanup(root, now=1010, live_attempts={"attempt-live"}, store=store)
    assert removed == (
        CleanupReport("attempt-live", "removed", "owner-a", manifest.disk_bytes, "expired"),
    )
    assert not worktree.exists()
    assert secret.read_text() == "stay\n"
    readme = b"base:alpha\n"
    readme_digest = hashlib.sha256(readme).hexdigest()
    copied = store / readme_digest
    assert copied.is_file() and not copied.is_symlink()
    assert copied.read_bytes() == readme
    assert hashlib.sha256(secret.read_bytes()).hexdigest() not in {item.name for item in store.iterdir()}
    reports = [
        item
        for item in store.iterdir()
        if item.is_file() and not item.name.startswith(".") and b"owner-a" in item.read_bytes()
    ]
    assert len(reports) == 1
    assert hashlib.sha256(reports[0].read_bytes()).hexdigest() == reports[0].name
    rogue = root / "attempts" / "rogue-attempt"
    rogue.mkdir(parents=True)
    (rogue / "note.txt").write_text("orphan\n")
    linked_outside = tmp_path / "linked-outside"
    linked_outside.mkdir()
    kept = linked_outside / "kept.txt"
    kept.write_text("kept\n")
    (root / "attempts" / "linked-attempt").symlink_to(linked_outside, target_is_directory=True)
    live_dir = root / "attempts" / "still-live"
    live_dir.mkdir()
    (live_dir / "keep.txt").write_text("keep\n")
    reports = {
        item.attempt_id: item
        for item in manager.cleanup(root, now=2000, live_attempts={"still-live"}, store=store)
    }
    assert reports["rogue-attempt"] == CleanupReport("rogue-attempt", "removed", "orphan", 7, "orphan")
    assert reports["linked-attempt"].reason == "unlinked-symlink"
    assert reports["still-live"] == CleanupReport("still-live", "denied", "", 5, "unrecorded-live")
    assert not rogue.exists()
    assert not (root / "attempts" / "linked-attempt").exists()
    assert kept.read_text() == "kept\n"
    assert (live_dir / "keep.txt").read_text() == "keep\n"
    assert (store / hashlib.sha256(b"orphan\n").hexdigest()).read_bytes() == b"orphan\n"
    assert hashlib.sha256(b"keep\n").hexdigest() not in {item.name for item in store.iterdir()}
    assert (root / "repo" / "README.txt").read_text() == "base:alpha\n"
    blocked_root = tmp_path / "blocked"
    blocked = manager.create(blocked_root, "attempt-block", SEED, owner="owner-b", ttl_seconds=1, now=0)
    blocked_store = tmp_path / "blocked-store"
    blocked_store.mkdir()
    (blocked_store / readme_digest).symlink_to(secret)
    with pytest.raises(ValueError, match="store symlink"):
        manager.cleanup(blocked_root, now=10, live_attempts=set(), store=blocked_store)
    assert Path(blocked.worktree).exists()
    assert secret.read_text() == "stay\n"


def test_scripted_events_name_the_attempt_and_stay_unaccepted(
    record_property: pytest.RecordProperty,
    tmp_path: Path,
) -> None:
    _properties(record_property, "AOS-004-TC01", "integration")
    sequence = ("started", "progress", "artifact.created", "verifying", "finished")
    dummy = WorkspaceManifest("unused", "unused", "unused", "0" * 40, "attempt-events")
    refused = MockWorkerAdapter(dummy, "shell", SEED)
    assert "shell" not in refused.capabilities()
    with pytest.raises(ValueError, match="worker mode"):
        refused.start()
    assert refused.observe().running is False
    assert refused.events() == ()
    with pytest.raises(ValueError, match="worker path"):
        MockWorkerAdapter(dummy, "success", SEED, relative="../outside.txt").validate()
    with pytest.raises(ValueError, match="worker epoch"):
        MockWorkerAdapter(dummy, "success", SEED, epoch=-1).validate()

    first_manifest = WorktreeManager().create(tmp_path / "events-a", "attempt-events", SEED)
    first = MockWorkerAdapter(first_manifest, "success", SEED, epoch=3)
    first.validate()
    assert first.events() == ()
    first.start()
    assert [item.name for item in first.events()] == ["started"]
    candidate = first.collect()
    recorded = first.events()
    assert candidate.accepted is False
    assert candidate.status == "CANDIDATE"
    _assert_event_sequence(recorded, first_manifest.attempt_id, 3, sequence)

    second_manifest = WorktreeManager().create(tmp_path / "events-b", "attempt-events", SEED)
    second = MockWorkerAdapter(second_manifest, "success", SEED, epoch=3)
    second.start()
    second.collect()
    assert [item.event_id for item in second.events()] == [item.event_id for item in recorded]


def test_journey_publication_uses_the_stored_epoch(
    record_property: pytest.RecordProperty, tmp_path: Path
) -> None:
    _properties(record_property, "AOS-004-TC04", "chaos")
    _database()
    goal = "00000000-0000-4000-8000-000000000196"
    contract = "00000000-0000-4000-8000-000000000197"
    task = "00000000-0000-4000-8000-000000000198"
    digest = "cd" * 32
    actor = Actor(OWNER, PROJECT)
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute("INSERT INTO panestria.principal (id, display_name) VALUES (%s, 'owner')", (OWNER,))
        connection.execute("INSERT INTO panestria.project (id, owner_id) VALUES (%s, %s)", (PROJECT, OWNER))
        connection.execute(
            "INSERT INTO panestria.goal (id, owner_id, project_id, intent, status)"
            " VALUES (%s, %s, %s, 'synthetic', 'CREATED')",
            (goal, OWNER, PROJECT),
        )
        connection.execute(
            "INSERT INTO panestria.goal_contract (id, goal_id, version, body, sha256)"
            " VALUES (%s, %s, 1, %s::jsonb, %s)",
            (contract, goal, '{"autonomy_profile_ref":"synthetic-approve-first-v1"}', digest),
        )
        connection.execute(
            "INSERT INTO panestria.task (id, goal_id, contract_id, name, state, lease_epoch)"
            " VALUES (%s, %s, %s, 'epoch', 'READY', 4)",
            (task, goal, contract),
        )
        connection.commit()
        journey = SyntheticJourney()
        journey._advance(connection, actor, task, "LEASED", "worker")
        attempt_id = journey._attempt(connection, task)
        stored = connection.execute(
            "SELECT lease_epoch, status FROM panestria.task_attempt WHERE id = %s",
            (attempt_id,),
        ).fetchone()
        assert stored == (4, "RUNNING")
        moved = connection.execute(
            "SELECT state, lease_epoch FROM panestria.task WHERE id = %s",
            (task,),
        ).fetchone()
        assert moved == ("LEASED", 4)
        store = tmp_path / "epoch-store"
        worktree = tmp_path / "work"
        store.mkdir()
        worktree.mkdir()
        report = NodeReport(
            check_id="synthetic-required",
            verifier_type="trusted-command-ref",
            required=True,
            verdict="PASS",
            reason="ok",
            candidate_sha256=digest,
            base_sha=digest,
            attempt_id=attempt_id,
            contract_sha256=digest,
        )
        artifact_id = _record_report(connection, ArtifactIngress(store, worktree), report, task, attempt_id, actor)
        connection.commit()
        saved = connection.execute(
            "SELECT attempt_id::text FROM panestria.artifact WHERE id = %s",
            (artifact_id,),
        ).fetchone()
        assert saved is not None and saved[0] == attempt_id
        connection.execute("UPDATE panestria.task SET lease_epoch = 5 WHERE id = %s", (task,))
        connection.commit()
        before = connection.execute(
            "SELECT count(*) FROM panestria.artifact WHERE task_id = %s",
            (task,),
        ).fetchone()
        with pytest.raises(KernelDenied, match="version_conflict"):
            _record_report(connection, ArtifactIngress(store, worktree), report, task, attempt_id, actor)
        connection.rollback()
        after = connection.execute(
            "SELECT count(*) FROM panestria.artifact WHERE task_id = %s",
            (task,),
        ).fetchone()
        assert before == after


def test_stale_attempt_is_not_reused(record_property: pytest.RecordProperty, tmp_path: Path) -> None:
    _properties(record_property, "AOS-004-TC04", "chaos")
    _database()
    goal = "00000000-0000-4000-8000-0000000001b0"
    contract = "00000000-0000-4000-8000-0000000001b1"
    task = "00000000-0000-4000-8000-0000000001b2"
    stale = "00000000-0000-4000-8000-0000000001b3"
    digest = "ef" * 32
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute("INSERT INTO panestria.principal (id, display_name) VALUES (%s, 'owner')", (OWNER,))
        connection.execute("INSERT INTO panestria.project (id, owner_id) VALUES (%s, %s)", (PROJECT, OWNER))
        connection.execute(
            "INSERT INTO panestria.goal (id, owner_id, project_id, intent, status)"
            " VALUES (%s, %s, %s, 'synthetic', 'CREATED')",
            (goal, OWNER, PROJECT),
        )
        connection.execute(
            "INSERT INTO panestria.goal_contract (id, goal_id, version, body, sha256)"
            " VALUES (%s, %s, 1, %s::jsonb, %s)",
            (contract, goal, '{"autonomy_profile_ref":"synthetic-approve-first-v1"}', digest),
        )
        connection.execute(
            "INSERT INTO panestria.task (id, goal_id, contract_id, name, state, lease_epoch)"
            " VALUES (%s, %s, %s, 'epoch', 'READY', 4)",
            (task, goal, contract),
        )
        connection.execute(
            "INSERT INTO panestria.task_attempt"
            " (id, task_id, attempt_number, lease_epoch, status, adapter)"
            " VALUES (%s, %s, 1, 0, 'SUCCEEDED', 'mock')",
            (stale, task),
        )
        connection.commit()
        journey = SyntheticJourney()
        current = journey._attempt(connection, task)
        assert current != stale
        again = journey._attempt(connection, task)
        assert again == current
        pending = journey._pending_attempt(connection, task, tmp_path)
        assert pending == current
        stored = connection.execute(
            "SELECT attempt_number, lease_epoch, status, external_ref FROM panestria.task_attempt WHERE id = %s",
            (current,),
        ).fetchone()
        assert stored == (2, 4, "RUNNING", None)
        old = connection.execute(
            "SELECT attempt_number, lease_epoch, status FROM panestria.task_attempt WHERE id = %s",
            (stale,),
        ).fetchone()
        assert old == (1, 0, "SUCCEEDED")


def test_old_candidate_does_not_stand_in_for_the_current_attempt(
    record_property: pytest.RecordProperty,
) -> None:
    _properties(record_property, "AOS-004-TC04", "chaos")
    _database()
    goal = "00000000-0000-4000-8000-0000000001c0"
    contract = "00000000-0000-4000-8000-0000000001c1"
    task = "00000000-0000-4000-8000-0000000001c2"
    stale = "00000000-0000-4000-8000-0000000001c3"
    current = "00000000-0000-4000-8000-0000000001c4"
    old_hash = "ab" * 32
    new_hash = "cd" * 32
    digest = "ef" * 32
    actor = Actor(OWNER, PROJECT)
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute("INSERT INTO panestria.principal (id, display_name) VALUES (%s, 'owner')", (OWNER,))
        connection.execute("INSERT INTO panestria.project (id, owner_id) VALUES (%s, %s)", (PROJECT, OWNER))
        connection.execute(
            "INSERT INTO panestria.goal (id, owner_id, project_id, intent, status)"
            " VALUES (%s, %s, %s, 'synthetic', 'CREATED')",
            (goal, OWNER, PROJECT),
        )
        connection.execute(
            "INSERT INTO panestria.goal_contract (id, goal_id, version, body, sha256)"
            " VALUES (%s, %s, 1, %s::jsonb, %s)",
            (contract, goal, '{"autonomy_profile_ref":"synthetic-approve-first-v1"}', digest),
        )
        connection.execute(
            "INSERT INTO panestria.task (id, goal_id, contract_id, name, state, lease_epoch)"
            " VALUES (%s, %s, %s, 'epoch', 'READY', 4)",
            (task, goal, contract),
        )
        connection.execute(
            "INSERT INTO panestria.task_attempt"
            " (id, task_id, attempt_number, lease_epoch, status, adapter)"
            " VALUES (%s, %s, 1, 0, 'SUCCEEDED', 'mock'),"
            " (%s, %s, 2, 4, 'RUNNING', 'mock')",
            (stale, task, current, task),
        )
        connection.execute(
            "INSERT INTO panestria.artifact"
            " (id, task_id, attempt_id, kind, store_key, sha256, size_bytes)"
            " VALUES (%s, %s, %s, 'candidate', %s, %s, 1)",
            ("00000000-0000-4000-8000-0000000001c5", task, stale, old_hash, old_hash),
        )
        connection.execute(
            "INSERT INTO panestria.workflow_link (task_id, attempt_id, dbos_workflow_id)"
            " VALUES (%s, %s, 'old-workflow')",
            (task, stale),
        )
        connection.commit()
        assert snapshot_artifact(connection, task) is None
        journey = SyntheticJourney()
        assert journey._linked_workflow(connection, actor, goal) is None
        shown = journey._snapshot(connection, actor, goal)
        assert shown.artifact_sha256 is None
        connection.execute(
            "INSERT INTO panestria.artifact"
            " (id, task_id, attempt_id, kind, store_key, sha256, size_bytes)"
            " VALUES (%s, %s, %s, 'candidate', %s, %s, 1)",
            ("00000000-0000-4000-8000-0000000001c6", task, current, new_hash, new_hash),
        )
        connection.execute(
            "INSERT INTO panestria.workflow_link (task_id, attempt_id, dbos_workflow_id)"
            " VALUES (%s, %s, 'current-workflow')",
            (task, current),
        )
        connection.commit()
        assert snapshot_artifact(connection, task) == new_hash
        assert journey._snapshot(connection, actor, goal).artifact_sha256 == new_hash
        assert journey._linked_workflow(connection, actor, goal) == "current-workflow"


def test_latest_approval_request_wins(record_property: pytest.RecordProperty) -> None:
    _properties(record_property, "AOS-005-TC04", "chaos")
    _database()
    goal = "00000000-0000-4000-8000-0000000001d0"
    contract = "00000000-0000-4000-8000-0000000001d1"
    task = "00000000-0000-4000-8000-0000000001d2"
    older = "00000000-0000-4000-8000-0000000001d3"
    newer = "00000000-0000-4000-8000-0000000001d4"
    digest = "ab" * 32
    other = "cd" * 32
    actor = Actor(OWNER, PROJECT)
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute("INSERT INTO panestria.principal (id, display_name) VALUES (%s, 'owner')", (OWNER,))
        connection.execute("INSERT INTO panestria.project (id, owner_id) VALUES (%s, %s)", (PROJECT, OWNER))
        connection.execute(
            "INSERT INTO panestria.goal (id, owner_id, project_id, intent, status)"
            " VALUES (%s, %s, %s, 'synthetic', 'ACTIVE')",
            (goal, OWNER, PROJECT),
        )
        connection.execute(
            "INSERT INTO panestria.goal_contract (id, goal_id, version, body, sha256)"
            " VALUES (%s, %s, 1, %s::jsonb, %s)",
            (contract, goal, '{"autonomy_profile_ref":"synthetic-approve-first-v1"}', digest),
        )
        connection.execute(
            "INSERT INTO panestria.task"
            " (id, goal_id, contract_id, name, state, continuation_kind, lease_epoch)"
            " VALUES (%s, %s, %s, 'approve', 'WAITING_APPROVAL', 'DISPATCH', 0)",
            (task, goal, contract),
        )
        for request_id, state, effect in (
            (older, "DENIED", digest),
            (newer, "APPROVED", other),
        ):
            connection.execute(
                "INSERT INTO panestria.approval_request"
                " (id, goal_id, task_id, owner_id, project_id, minimum_actor_id, action_kind,"
                " effect_digest, policy_version, state, expires_at, decided_at, decided_by, preview)"
                " VALUES (%s, %s, %s, %s, %s, %s, 'contract_consent', %s,"
                " 'synthetic-approve-first-v1', %s, now() + interval '1 hour', now(), %s, %s::jsonb)",
                (
                    request_id,
                    goal,
                    task,
                    OWNER,
                    PROJECT,
                    OWNER,
                    effect,
                    state,
                    OWNER,
                    '{"action_kind":"contract_consent"}',
                ),
            )
            connection.execute(
                "INSERT INTO panestria.task_event (id, goal_id, task_id, kind, actor, payload)"
                " VALUES (%s, %s, %s, 'approval.requested', %s, %s::jsonb)",
                (
                    str(UUID(int=UUID(request_id).int + 1)),
                    goal,
                    task,
                    OWNER,
                    '{"approval_id":"%s"}' % request_id,
                ),
            )
        connection.commit()
        journey = SyntheticJourney()
        found = journey._approval(connection, task, "contract_consent")
        assert found is not None
        assert found[0] == newer
        assert found[1] == "APPROVED"
        snapshot = journey._snapshot(connection, actor, goal)
        assert snapshot.approval_id == newer
        assert journey._decision(connection, snapshot) == "APPROVED"


def test_observation_does_not_hide_a_prepared_effect(record_property: pytest.RecordProperty) -> None:
    _properties(record_property, "AOS-005-TC04", "chaos")
    _database()
    goal = "00000000-0000-4000-8000-0000000001e0"
    contract = "00000000-0000-4000-8000-0000000001e1"
    task = "00000000-0000-4000-8000-0000000001e2"
    approval = "00000000-0000-4000-8000-0000000001e3"
    digest = "ab" * 32
    actor = Actor(OWNER, PROJECT)
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute("INSERT INTO panestria.principal (id, display_name) VALUES (%s, 'owner')", (OWNER,))
        connection.execute("INSERT INTO panestria.project (id, owner_id) VALUES (%s, %s)", (PROJECT, OWNER))
        connection.execute(
            "INSERT INTO panestria.goal (id, owner_id, project_id, intent, status)"
            " VALUES (%s, %s, %s, 'synthetic', 'ACTIVE')",
            (goal, OWNER, PROJECT),
        )
        connection.execute(
            "INSERT INTO panestria.goal_contract (id, goal_id, version, body, sha256)"
            " VALUES (%s, %s, 1, %s::jsonb, %s)",
            (contract, goal, '{"autonomy_profile_ref":"synthetic-approve-first-v1"}', digest),
        )
        connection.execute(
            "INSERT INTO panestria.task"
            " (id, goal_id, contract_id, name, state, continuation_kind)"
            " VALUES (%s, %s, %s, 'effect', 'WAITING_APPROVAL', 'MERGE')",
            (task, goal, contract),
        )
        connection.execute(
            "INSERT INTO panestria.side_effect"
            " (id, task_id, effect_key, target, request_hash, state, external_ref)"
            " VALUES (%s, %s, 'synthetic-observe', 'synthetic', %s, 'SUCCEEDED', %s)",
            ("00000000-0000-4000-8000-0000000001e4", task, digest, f"synthetic:{task}"),
        )
        connection.commit()
        journey = SyntheticJourney()
        assert journey._snapshot(connection, actor, goal).effect_state is None
        connection.execute(
            "INSERT INTO panestria.approval_request"
            " (id, goal_id, task_id, owner_id, project_id, minimum_actor_id, action_kind,"
            " effect_digest, policy_version, state, expires_at, decided_at, decided_by, preview)"
            " VALUES (%s, %s, %s, %s, %s, %s, 'merge', %s,"
            " 'synthetic-approve-first-v1', 'APPROVED', now() + interval '1 hour', now(), %s, %s::jsonb)",
            (
                approval,
                goal,
                task,
                OWNER,
                PROJECT,
                OWNER,
                digest,
                OWNER,
                '{"action_kind":"merge"}',
            ),
        )
        connection.execute(
            "INSERT INTO panestria.task_event (id, goal_id, task_id, kind, actor, payload)"
            " VALUES (%s, %s, %s, 'approval.requested', %s, %s::jsonb)",
            (
                "00000000-0000-4000-8000-0000000001e6",
                goal,
                task,
                OWNER,
                '{"approval_id":"%s"}' % approval,
            ),
        )
        connection.execute(
            "INSERT INTO panestria.side_effect"
            " (id, task_id, effect_key, target, request_hash, state)"
            " VALUES (%s, %s, %s, 'refs/heads/main', %s, 'PREPARED')",
            ("00000000-0000-4000-8000-0000000001e5", task, f"approval:{approval}", digest),
        )
        connection.commit()
        assert journey._snapshot(connection, actor, goal).effect_state == "PREPARED"
        observed = connection.execute(
            "SELECT state FROM panestria.side_effect WHERE effect_key = 'synthetic-observe' AND task_id = %s",
            (task,),
        ).fetchone()
        assert observed is not None and observed[0] == "SUCCEEDED"


def test_old_effect_does_not_stand_in_for_the_current_approval(record_property: pytest.RecordProperty) -> None:
    _properties(record_property, "AOS-005-TC04", "chaos")
    _database()
    goal = "00000000-0000-4000-8000-0000000001f0"
    contract = "00000000-0000-4000-8000-0000000001f1"
    task = "00000000-0000-4000-8000-0000000001f2"
    older = "00000000-0000-4000-8000-0000000001f3"
    newer = "00000000-0000-4000-8000-0000000001f5"
    digest = "cd" * 32
    actor = Actor(OWNER, PROJECT)
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute("INSERT INTO panestria.principal (id, display_name) VALUES (%s, 'owner')", (OWNER,))
        connection.execute("INSERT INTO panestria.project (id, owner_id) VALUES (%s, %s)", (PROJECT, OWNER))
        connection.execute(
            "INSERT INTO panestria.goal (id, owner_id, project_id, intent, status)"
            " VALUES (%s, %s, %s, 'synthetic', 'ACTIVE')",
            (goal, OWNER, PROJECT),
        )
        connection.execute(
            "INSERT INTO panestria.goal_contract (id, goal_id, version, body, sha256)"
            " VALUES (%s, %s, 1, %s::jsonb, %s)",
            (contract, goal, '{"autonomy_profile_ref":"synthetic-approve-first-v1"}', digest),
        )
        connection.execute(
            "INSERT INTO panestria.task"
            " (id, goal_id, contract_id, name, state, continuation_kind)"
            " VALUES (%s, %s, %s, 'effect', 'WAITING_APPROVAL', 'MERGE')",
            (task, goal, contract),
        )
        for request_id, event_id in (
            (older, "00000000-0000-4000-8000-0000000001f4"),
            (newer, "00000000-0000-4000-8000-0000000001f6"),
        ):
            connection.execute(
                "INSERT INTO panestria.approval_request"
                " (id, goal_id, task_id, owner_id, project_id, minimum_actor_id, action_kind,"
                " effect_digest, policy_version, state, expires_at, decided_at, decided_by, preview)"
                " VALUES (%s, %s, %s, %s, %s, %s, 'merge', %s,"
                " 'synthetic-approve-first-v1', 'APPROVED', now() + interval '1 hour', now(), %s, %s::jsonb)",
                (request_id, goal, task, OWNER, PROJECT, OWNER, digest, OWNER, '{"action_kind":"merge"}'),
            )
            connection.execute(
                "INSERT INTO panestria.task_event (id, goal_id, task_id, kind, actor, payload)"
                " VALUES (%s, %s, %s, 'approval.requested', %s, %s::jsonb)",
                (event_id, goal, task, OWNER, '{"approval_id":"%s"}' % request_id),
            )
        connection.execute(
            "INSERT INTO panestria.side_effect"
            " (id, task_id, effect_key, target, request_hash, state)"
            " VALUES (%s, %s, %s, 'refs/heads/main', %s, 'PREPARED')",
            ("00000000-0000-4000-8000-0000000001f7", task, f"approval:{older}", digest),
        )
        connection.commit()
        journey = SyntheticJourney()
        hidden = journey._snapshot(connection, actor, goal)
        assert hidden.approval_id == newer
        assert hidden.effect_state is None
        connection.execute(
            "INSERT INTO panestria.side_effect"
            " (id, task_id, effect_key, target, request_hash, state)"
            " VALUES (%s, %s, %s, 'refs/heads/main', %s, 'PREPARED')",
            ("00000000-0000-4000-8000-0000000001f8", task, f"approval:{newer}", digest),
        )
        connection.commit()
        assert journey._snapshot(connection, actor, goal).effect_state == "PREPARED"
        older_state = connection.execute(
            "SELECT state FROM panestria.side_effect WHERE task_id = %s AND effect_key = %s",
            (task, f"approval:{older}"),
        ).fetchone()
        assert older_state is not None and older_state[0] == "PREPARED"


def test_stored_pass_does_not_merge_a_different_commit(
    record_property: pytest.RecordProperty, tmp_path: Path
) -> None:
    _properties(record_property, "AOS-004-TC02", "security")
    _database()
    goal = "00000000-0000-4000-8000-000000000210"
    contract_id = "00000000-0000-4000-8000-000000000211"
    task = "00000000-0000-4000-8000-000000000212"
    attempt = "00000000-0000-4000-8000-000000000213"
    digest = "de" * 32
    actor = Actor(OWNER, PROJECT)
    body = json.loads((ROOT / "docs/fixtures/synthetic-goal-contract.json").read_text(encoding="utf-8"))
    body["goal_id"] = goal
    sandbox = tmp_path / "different-commit"
    journey = SyntheticJourney()
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute("INSERT INTO panestria.principal (id, display_name) VALUES (%s, 'owner')", (OWNER,))
        connection.execute("INSERT INTO panestria.project (id, owner_id) VALUES (%s, %s)", (PROJECT, OWNER))
        connection.execute(
            "INSERT INTO panestria.goal (id, owner_id, project_id, intent, status)"
            " VALUES (%s, %s, %s, 'synthetic', 'CREATED')",
            (goal, OWNER, PROJECT),
        )
        connection.execute(
            "INSERT INTO panestria.goal_contract (id, goal_id, version, body, sha256)"
            " VALUES (%s, %s, 1, %s::jsonb, %s)",
            (contract_id, goal, json.dumps(body), digest),
        )
        connection.execute(
            "INSERT INTO panestria.task (id, goal_id, contract_id, name, state)"
            " VALUES (%s, %s, %s, 'commit', 'READY')",
            (task, goal, contract_id),
        )
        connection.commit()
        journey._checks(connection, (contract_id, digest, 1, body))
        manifest = journey._workspace(sandbox, attempt, goal, OWNER)
        worktree = Path(manifest.worktree)
        readme = worktree / "README.txt"
        readme.write_text("hidden from the stored pass\n", encoding="utf-8")
        _git_commit(worktree, ["add", "README.txt"])
        _git_commit(worktree, ["-c", "core.hooksPath=/dev/null", "commit", "-m", "synthetic-candidate"])
        _git_commit(worktree, ["branch", "synthetic-candidate"])
        _git_commit(worktree, ["checkout", manifest.base_sha, "--", "README.txt"])
        edited = worktree / "tests" / "synthetic.txt"
        edited.parent.mkdir(parents=True)
        payload = b"edit:alpha\n"
        edited.write_bytes(payload)
        file_hash = hashlib.sha256(payload).hexdigest()
        connection.execute(
            "INSERT INTO panestria.task_attempt"
            " (id, task_id, attempt_number, lease_epoch, status, adapter, external_ref)"
            " VALUES (%s, %s, 1, 0, 'RUNNING', 'mock', %s)",
            (attempt, task, str(sandbox.resolve())),
        )
        connection.execute(
            "INSERT INTO panestria.artifact"
            " (id, task_id, attempt_id, kind, store_key, sha256, size_bytes)"
            " VALUES (%s, %s, %s, 'candidate', 'candidate', %s, %s)",
            ("00000000-0000-4000-8000-000000000214", task, attempt, file_hash, len(payload)),
        )
        evidence = "00000000-0000-4000-8000-000000000215"
        connection.execute(
            "INSERT INTO panestria.artifact"
            " (id, task_id, attempt_id, kind, store_key, sha256, size_bytes)"
            " VALUES (%s, %s, %s, 'check-report', 'report', %s, %s)",
            (evidence, task, attempt, file_hash, len(payload)),
        )
        checks = connection.execute(
            "SELECT id::text FROM panestria.acceptance_check WHERE contract_id = %s AND required",
            (contract_id,),
        ).fetchall()
        assert len(checks) == 3
        for index, (check_id,) in enumerate(checks):
            connection.execute(
                "INSERT INTO panestria.check_run"
                " (id, acceptance_check_id, attempt_id, task_id, contract_id, verdict,"
                " evidence_artifact_id, candidate_sha256)"
                " VALUES (%s, %s, %s, %s, %s, 'PASS', %s, %s)",
                (
                    f"00000000-0000-4000-8000-00000000021{index + 6}",
                    check_id,
                    attempt,
                    task,
                    contract_id,
                    evidence,
                    file_hash,
                ),
            )
        connection.commit()
        journey._finish_dispatch(connection, actor, goal, sandbox)
        approval = connection.execute(
            "SELECT count(*) FROM panestria.approval_request WHERE task_id = %s",
            (task,),
        ).fetchone()
        goal_status = connection.execute("SELECT status FROM panestria.goal WHERE id = %s", (goal,)).fetchone()
        assert approval is not None and approval[0] == 0
        assert goal_status is not None and goal_status[0] == "CREATED"


def test_global_scope_denies_a_commit_without_a_path_check(
    record_property: pytest.RecordProperty, tmp_path: Path
) -> None:
    _properties(record_property, "AOS-004-TC02", "security")
    _database()
    goal = "00000000-0000-4000-8000-000000000250"
    contract_id = "00000000-0000-4000-8000-000000000251"
    task = "00000000-0000-4000-8000-000000000252"
    attempt = "00000000-0000-4000-8000-000000000253"
    digest = "ef" * 32
    actor = Actor(OWNER, PROJECT)
    body = json.loads((ROOT / "docs/fixtures/synthetic-goal-contract.json").read_text(encoding="utf-8"))
    body["goal_id"] = goal
    body["acceptance"] = [
        item for item in body["acceptance"] if item["verifier"]["type"] != "git-diff-path-check"
    ]
    sandbox = tmp_path / "global-scope"
    journey = SyntheticJourney()
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute("INSERT INTO panestria.principal (id, display_name) VALUES (%s, 'owner')", (OWNER,))
        connection.execute("INSERT INTO panestria.project (id, owner_id) VALUES (%s, %s)", (PROJECT, OWNER))
        connection.execute(
            "INSERT INTO panestria.goal (id, owner_id, project_id, intent, status)"
            " VALUES (%s, %s, %s, 'synthetic', 'CREATED')",
            (goal, OWNER, PROJECT),
        )
        connection.execute(
            "INSERT INTO panestria.goal_contract (id, goal_id, version, body, sha256)"
            " VALUES (%s, %s, 1, %s::jsonb, %s)",
            (contract_id, goal, json.dumps(body), digest),
        )
        connection.execute(
            "INSERT INTO panestria.task (id, goal_id, contract_id, name, state)"
            " VALUES (%s, %s, %s, 'scope', 'READY')",
            (task, goal, contract_id),
        )
        connection.commit()
        journey._checks(connection, (contract_id, digest, 1, body))
        manifest = journey._workspace(sandbox, attempt, goal, OWNER)
        worktree = Path(manifest.worktree)
        readme = worktree / "README.txt"
        readme.write_text("outside the global allowlist\n", encoding="utf-8")
        _git_commit(worktree, ["add", "README.txt"])
        _git_commit(worktree, ["-c", "core.hooksPath=/dev/null", "commit", "-m", "synthetic-candidate"])
        _git_commit(worktree, ["branch", "synthetic-candidate"])
        _git_commit(worktree, ["checkout", manifest.base_sha, "--", "README.txt"])
        edited = worktree / "tests" / "synthetic.txt"
        edited.parent.mkdir(parents=True)
        payload = b"edit:alpha\n"
        edited.write_bytes(payload)
        file_hash = hashlib.sha256(payload).hexdigest()
        connection.execute(
            "INSERT INTO panestria.task_attempt"
            " (id, task_id, attempt_number, lease_epoch, status, adapter, external_ref)"
            " VALUES (%s, %s, 1, 0, 'RUNNING', 'mock', %s)",
            (attempt, task, str(sandbox.resolve())),
        )
        connection.execute(
            "INSERT INTO panestria.artifact"
            " (id, task_id, attempt_id, kind, store_key, sha256, size_bytes)"
            " VALUES (%s, %s, %s, 'candidate', 'candidate', %s, %s)",
            ("00000000-0000-4000-8000-000000000254", task, attempt, file_hash, len(payload)),
        )
        evidence = "00000000-0000-4000-8000-000000000255"
        connection.execute(
            "INSERT INTO panestria.artifact"
            " (id, task_id, attempt_id, kind, store_key, sha256, size_bytes)"
            " VALUES (%s, %s, %s, 'check-report', 'report', %s, %s)",
            (evidence, task, attempt, file_hash, len(payload)),
        )
        checks = connection.execute(
            "SELECT id::text FROM panestria.acceptance_check WHERE contract_id = %s AND required"
            " ORDER BY check_key",
            (contract_id,),
        ).fetchall()
        assert len(checks) == 2
        for index, (check_id,) in enumerate(checks):
            connection.execute(
                "INSERT INTO panestria.check_run"
                " (id, acceptance_check_id, attempt_id, task_id, contract_id, verdict,"
                " evidence_artifact_id, candidate_sha256)"
                " VALUES (%s, %s, %s, %s, %s, 'PASS', %s, %s)",
                (
                    f"00000000-0000-4000-8000-00000000025{index + 6}",
                    check_id,
                    attempt,
                    task,
                    contract_id,
                    evidence,
                    file_hash,
                ),
            )
        connection.commit()
        journey._finish_dispatch(connection, actor, goal, sandbox)
        approval = connection.execute(
            "SELECT count(*) FROM panestria.approval_request WHERE task_id = %s",
            (task,),
        ).fetchone()
        goal_status = connection.execute("SELECT status FROM panestria.goal WHERE id = %s", (goal,)).fetchone()
        assert approval is not None and approval[0] == 0
        assert goal_status is not None and goal_status[0] == "CREATED"


def test_journey_contract_follows_the_task_or_the_latest_version(
    record_property: pytest.RecordProperty,
) -> None:
    _properties(record_property, "AOS-005-TC04", "chaos")
    _database()
    goal = "00000000-0000-4000-8000-000000000220"
    older = "00000000-0000-4000-8000-000000000221"
    newer = "00000000-0000-4000-8000-000000000222"
    task = "00000000-0000-4000-8000-000000000223"
    actor = Actor(OWNER, PROJECT)
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute("INSERT INTO panestria.principal (id, display_name) VALUES (%s, 'owner')", (OWNER,))
        connection.execute("INSERT INTO panestria.project (id, owner_id) VALUES (%s, %s)", (PROJECT, OWNER))
        connection.execute(
            "INSERT INTO panestria.goal (id, owner_id, project_id, intent, status)"
            " VALUES (%s, %s, %s, 'synthetic', 'CREATED')",
            (goal, OWNER, PROJECT),
        )
        for contract_id, version, digest in (
            (older, 1, "11" * 32),
            (newer, 2, "22" * 32),
        ):
            connection.execute(
                "INSERT INTO panestria.goal_contract (id, goal_id, version, body, sha256)"
                " VALUES (%s, %s, %s, %s::jsonb, %s)",
                (
                    contract_id,
                    goal,
                    version,
                    '{"autonomy_profile_ref":"synthetic-approve-first-v1","contract_version":%s}' % version,
                    digest,
                ),
            )
        connection.commit()
        journey = SyntheticJourney()
        selected = journey._contract(connection, actor, goal)
        assert selected[0] == newer
        assert selected[2] == 2
        connection.execute(
            "INSERT INTO panestria.task (id, goal_id, contract_id, name, state)"
            " VALUES (%s, %s, %s, 'bound', 'CREATED')",
            (task, goal, older),
        )
        connection.commit()
        bound = journey._contract(connection, actor, goal)
        assert bound[0] == older
        assert bound[2] == 1


def test_stale_snapshot_does_not_complete_a_different_approval(
    record_property: pytest.RecordProperty,
    tmp_path: Path,
) -> None:
    _properties(record_property, "AOS-005-TC04", "chaos")
    _database()
    goal = "00000000-0000-4000-8000-000000000240"
    contract = "00000000-0000-4000-8000-000000000241"
    task = "00000000-0000-4000-8000-000000000242"
    older = "00000000-0000-4000-8000-000000000243"
    newer = "00000000-0000-4000-8000-000000000245"
    digest = "ab" * 32
    actor = Actor(OWNER, PROJECT)
    sha = _bare_ref(tmp_path)
    preview = json.dumps(
        {
            "action_kind": "merge",
            "owner_id": OWNER,
            "project_id": PROJECT,
            "task_id": task,
            "contract_sha256": digest,
            "contract_version": 1,
            "policy_version": "synthetic-approve-first-v1",
            "destination": f"refs/heads/main@{sha}",
            "expected_base": sha,
            "candidate_sha256": "cd" * 32,
            "required_checks": ["synthetic-required"],
            "minimum_actor_id": OWNER,
            "expires_at": "2027-01-01T00:00:00+00:00",
        }
    )
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute("INSERT INTO panestria.principal (id, display_name) VALUES (%s, 'owner')", (OWNER,))
        connection.execute("INSERT INTO panestria.project (id, owner_id) VALUES (%s, %s)", (PROJECT, OWNER))
        connection.execute(
            "INSERT INTO panestria.goal (id, owner_id, project_id, intent, status)"
            " VALUES (%s, %s, %s, 'synthetic', 'CREATED')",
            (goal, OWNER, PROJECT),
        )
        connection.execute(
            "INSERT INTO panestria.goal_contract (id, goal_id, version, body, sha256)"
            " VALUES (%s, %s, 1, %s::jsonb, %s)",
            (contract, goal, '{"autonomy_profile_ref":"synthetic-approve-first-v1"}', digest),
        )
        connection.execute(
            "INSERT INTO panestria.task"
            " (id, goal_id, contract_id, name, state, continuation_kind)"
            " VALUES (%s, %s, %s, 'effect', 'VERIFYING', 'MERGE')",
            (task, goal, contract),
        )
        for request_id, event_id, body in (
            (older, "00000000-0000-4000-8000-000000000244", '{"action_kind":"merge"}'),
            (newer, "00000000-0000-4000-8000-000000000246", preview),
        ):
            connection.execute(
                "INSERT INTO panestria.approval_request"
                " (id, goal_id, task_id, owner_id, project_id, minimum_actor_id, action_kind,"
                " effect_digest, policy_version, state, expires_at, decided_at, decided_by, preview)"
                " VALUES (%s, %s, %s, %s, %s, %s, 'merge', %s,"
                " 'synthetic-approve-first-v1', 'APPROVED', now() + interval '1 hour', now(), %s, %s::jsonb)",
                (request_id, goal, task, OWNER, PROJECT, OWNER, digest, OWNER, body),
            )
            connection.execute(
                "INSERT INTO panestria.task_event (id, goal_id, task_id, kind, actor, payload)"
                " VALUES (%s, %s, %s, 'approval.requested', %s, %s::jsonb)",
                (event_id, goal, task, OWNER, '{"approval_id":"%s"}' % request_id),
            )
        connection.execute(
            "INSERT INTO panestria.side_effect"
            " (id, task_id, effect_key, target, request_hash, state)"
            " VALUES (%s, %s, %s, 'refs/heads/main', %s, 'PREPARED')",
            ("00000000-0000-4000-8000-000000000247", task, f"approval:{older}", digest),
        )
        connection.commit()
        journey = SyntheticJourney()
        stale = JourneySnapshot("CREATED", "VERIFYING", "MERGE", older, digest, 0, 0, None, "PREPARED")
        journey._confirm(connection, actor, goal, tmp_path, stale)
        goal_status = connection.execute("SELECT status FROM panestria.goal WHERE id = %s", (goal,)).fetchone()
        task_state = connection.execute("SELECT state FROM panestria.task WHERE id = %s", (task,)).fetchone()
        effect = connection.execute(
            "SELECT state FROM panestria.side_effect WHERE effect_key = %s",
            (f"approval:{older}",),
        ).fetchone()
        assert goal_status is not None and goal_status[0] == "CREATED"
        assert task_state is not None and task_state[0] == "VERIFYING"
        assert effect is not None and effect[0] == "PREPARED"
        assert _git_commit_sha(tmp_path / "protected" / "dest.git") == sha


def _bare_ref(sandbox: Path) -> str:
    seed = sandbox / "seed"
    seed.mkdir()
    _git_commit(seed, ["init", "-b", "main"])
    (seed / "README.txt").write_text("base\n")
    _git_commit(seed, ["add", "README.txt"])
    _git_commit(seed, ["commit", "-m", "base"])
    bare = sandbox / "protected" / "dest.git"
    bare.parent.mkdir()
    completed = subprocess.run(
        ["git", "clone", "--bare", str(seed), str(bare)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return _git_commit_sha(bare)


def _git_commit_sha(bare: Path) -> str:
    completed = subprocess.run(
        ["git", "--git-dir", str(bare), "rev-parse", "refs/heads/main"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


def _git_commit(worktree: Path, args: list[str]) -> None:
    completed = subprocess.run(
        ["git", "-C", str(worktree), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def _assert_event_sequence(
    recorded: tuple[WorkerEvent, ...],
    attempt_id: str,
    epoch: int,
    sequence: tuple[str, ...],
) -> None:
    assert [item.name for item in recorded] == list(sequence)
    seen: set[str] = set()
    for item in recorded:
        assert item.attempt_id == attempt_id
        assert item.epoch == epoch
        assert UUID(item.event_id).version == 5
        assert item.event_id not in seen
        seen.add(item.event_id)
