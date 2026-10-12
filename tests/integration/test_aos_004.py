"""AOS-004 worker candidate and independent checks."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest
from psycopg.errors import CheckViolation

from panestria.brokers.harness.mock import OUTPUT_LIMIT, Candidate, MockWorkerAdapter, Observation
from panestria.sandbox.artifact_ingress import ArtifactIngress, ArtifactRef
from panestria.sandbox.worktree import WorkspaceManifest, WorktreeManager
from panestria.verification.artifacts import decide
from panestria.verification.diff import inspect_diff
from panestria.verification.registry import CommandRegistry
from panestria.verification.runner import TrustedCheckRunner

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


COMPOSE = ["docker", "compose", "-f", str(ROOT / "compose.yaml"), "-p", "panestria-s3"]
DATABASE_URL = "postgresql://panestria_synthetic:placeholder-not-a-secret@127.0.0.1:55432/panestria_synthetic"
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
        " VALUES (%s, %s, 1, '{}'::jsonb, %s)",
        (CONTRACT, GOAL, digest),
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
