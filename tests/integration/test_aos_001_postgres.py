"""Disposable PostgreSQL bootstrap for AOS-001-TC03.

The fresh-host live case AOS-001-TC04 is not this module and stays NOT_RUN
without a separate Ubuntu host.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import psycopg
import pytest

from panestria.ops import EXPECTED_VOLUME, HOST_PORT, LOOPBACK_BIND, CleanupDenied, reset_volume_directory

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ["docker", "compose", "-f", str(ROOT / "compose.yaml"), "-p", "panestria-s3"]
DATABASE_URL = (
    "postgresql://panestria_synthetic:placeholder-not-a-secret"
    f"@{LOOPBACK_BIND}:{HOST_PORT}/panestria_synthetic"
)


@pytest.fixture(autouse=True)
def _case_metadata(record_property: pytest.RecordProperty) -> None:
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False)
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, text=True, capture_output=True, check=False)
    record_property("gate_case_id", "AOS-001-TC03")
    record_property("candidate_commit", commit.stdout.strip())
    record_property("fixture_digest", "compose-scaffold")
    record_property("lane", "integration")
    record_property("execution_mode", "OS_BOUNDARY")
    record_property("worktree_state", "dirty" if dirty.stdout.strip() else "clean")


def test_wrong_volume_and_symlink_cleanup_are_denied(tmp_path: Path) -> None:
    mount = tmp_path / "data"
    mount.mkdir()
    marker = mount / "keep.txt"
    marker.write_text("synthetic", encoding="utf-8")
    with pytest.raises(CleanupDenied) as wrong:
        reset_volume_directory("other_volume", mount)
    assert wrong.value.code == "wrong_volume"
    assert marker.read_text(encoding="utf-8") == "synthetic"

    target = tmp_path / "target"
    target.mkdir()
    (target / "secret.txt").write_text("stay", encoding="utf-8")
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(CleanupDenied) as linked:
        reset_volume_directory(EXPECTED_VOLUME, link)
    assert linked.value.code == "symlink_mount"
    assert (target / "secret.txt").read_text(encoding="utf-8") == "stay"

    child = mount / "escape"
    child.symlink_to(target, target_is_directory=True)
    with pytest.raises(CleanupDenied) as child_link:
        reset_volume_directory(EXPECTED_VOLUME, mount)
    assert child_link.value.code == "symlink_child"
    assert marker.exists()
    assert (target / "secret.txt").exists()


def test_expected_directory_reset_removes_only_children(tmp_path: Path) -> None:
    mount = tmp_path / "data"
    mount.mkdir()
    (mount / "old.txt").write_text("old", encoding="utf-8")
    reset_volume_directory(EXPECTED_VOLUME, mount)
    assert mount.is_dir()
    assert list(mount.iterdir()) == []


def test_scoped_database_is_healthy_and_scaffold_is_empty() -> None:
    env = os.environ.copy()
    env["PANESTRIA_DATABASE_URL"] = DATABASE_URL
    subprocess.run([*COMPOSE, "down", "-v"], cwd=ROOT, check=False, capture_output=True, text=True)
    try:
        up = subprocess.run(
            [*COMPOSE, "up", "-d", "--wait"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        assert up.returncode == 0, up.stderr
        container = subprocess.run(
            [*COMPOSE, "ps", "-q", "postgres"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        ports = subprocess.run(
            ["docker", "inspect", "--format", "{{json .NetworkSettings.Ports}}", container],
            check=True,
            capture_output=True,
            text=True,
        )
        bindings = json.loads(ports.stdout)["5432/tcp"]
        assert len(bindings) == 1
        assert bindings[0]["HostIp"] == LOOPBACK_BIND
        assert int(bindings[0]["HostPort"]) == HOST_PORT
        deadline = time.monotonic() + 30
        last_error = ""
        while time.monotonic() < deadline:
            try:
                with psycopg.connect(DATABASE_URL, connect_timeout=2) as connection:
                    connection.execute("SELECT 1")
                break
            except psycopg.Error as exc:
                last_error = exc.__class__.__name__
                time.sleep(0.5)
        else:
            raise AssertionError(last_error)
        upgraded = subprocess.run(
            ["uv", "run", "--frozen", "alembic", "-c", "migrations/alembic.ini", "upgrade", "head"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        assert upgraded.returncode == 0, upgraded.stderr
        with psycopg.connect(DATABASE_URL) as connection:
            version = connection.execute("SELECT version_num FROM alembic_version").fetchone()
            tables = connection.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'panestria'"
            ).fetchall()
        assert version is not None
        assert version[0] == "0001_scaffold"
        assert tables == []
    finally:
        subprocess.run([*COMPOSE, "down", "-v"], cwd=ROOT, check=False, capture_output=True, text=True)
