"""R1 PostgreSQL is separate from the owner's R0 review database."""

from __future__ import annotations

import json
import os
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

ROOT = Path(__file__).resolve().parents[2]
R1_DSN = "postgresql://panestria_synthetic:placeholder-not-a-secret@127.0.0.1:55439/panestria_synthetic"
IMAGE = "postgres@sha256:ca0bd484cb98bf4b24eb1010e73fb3fcbd6714d240fbc1a10eea5b7dbecb641d"


@pytest.fixture(scope="session")
def r1_database() -> Iterator[str]:
    name = f"panestria-r1-tests-{uuid4().hex[:12]}"
    created = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--label",
            "panestria.purpose=r1-test",
            "--publish",
            "127.0.0.1:55439:5432",
            "--env",
            "POSTGRES_USER=panestria_synthetic",
            "--env",
            "POSTGRES_PASSWORD=placeholder-not-a-secret",
            "--env",
            "POSTGRES_DB=panestria_synthetic",
            IMAGE,
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    try:
        assert created.returncode == 0, created.stderr
        deadline = time.monotonic() + 60
        while True:
            try:
                with psycopg.connect(R1_DSN, connect_timeout=1):
                    break
            except psycopg.OperationalError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.2)
        upgraded = subprocess.run(
            ["uv", "run", "--frozen", "alembic", "-c", "migrations/alembic.ini", "upgrade", "head"],
            cwd=ROOT,
            env={**os.environ, "PANESTRIA_DATABASE_URL": R1_DSN},
            text=True,
            capture_output=True,
            check=False,
        )
        assert upgraded.returncode == 0, upgraded.stderr
        yield R1_DSN
    finally:
        # Only remove the exact container created by this fixture. Anonymous volume included.
        subprocess.run(["docker", "rm", "--force", "--volumes", name], capture_output=True, check=False)


@pytest.fixture
def r1_task(r1_database: str) -> dict[str, str]:
    return _seed_r1_task(r1_database)


@pytest.fixture
def r1_migration_task(r1_database: str) -> Iterator[dict[str, str]]:
    """Old-schema roundtrips must not downgrade another test's retained audits."""
    name = "panestria_lease_migration_" + uuid4().hex
    dsn = r1_database.rsplit("/", 1)[0] + "/" + name
    with psycopg.connect(r1_database, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            result = subprocess.run(
                ["uv", "run", "--frozen", "alembic", "-c", "migrations/alembic.ini", "upgrade", "head"],
                cwd=ROOT,
                env={**os.environ, "PANESTRIA_DATABASE_URL": dsn},
                capture_output=True,
                timeout=60,
            )
            assert result.returncode == 0, result.stderr
            yield _seed_r1_task(dsn)
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def _seed_r1_task(r1_database: str) -> dict[str, str]:
    ids = {key: str(uuid4()) for key in ("owner", "project", "goal", "contract", "task", "check")}
    ids["dsn"] = r1_database
    with psycopg.connect(r1_database) as c:
        c.execute("INSERT INTO panestria.principal(id,display_name) VALUES (%s,'synthetic R1 owner')", (ids["owner"],))
        c.execute("INSERT INTO panestria.project(id,owner_id) VALUES (%s,%s)", (ids["project"], ids["owner"]))
        c.execute(
            "INSERT INTO panestria.goal(id,owner_id,project_id,intent,status) VALUES (%s,%s,%s,'test','ACTIVE')",
            (ids["goal"], ids["owner"], ids["project"]),
        )
        c.execute(
            "INSERT INTO panestria.goal_contract(id,goal_id,version,body,sha256) VALUES (%s,%s,1,%s::jsonb,%s)",
            (
                ids["contract"],
                ids["goal"],
                json.dumps(
                    {
                        "autonomy_profile_ref": "test-policy-v1",
                        "budget": {"max_api_usd": "1.000000", "max_attempts_per_task": 3},
                    }
                ),
                "ab" * 32,
            ),
        )
        c.execute(
            "INSERT INTO panestria.task(id,goal_id,contract_id,name,state) VALUES (%s,%s,%s,'test','READY')",
            (ids["task"], ids["goal"], ids["contract"]),
        )
        c.execute(
            "INSERT INTO panestria.acceptance_check"
            " (id,contract_id,check_key,description,verifier_type,verifier_spec)"
            " VALUES (%s,%s,'test','test','artifact-exists',%s::jsonb)",
            (ids["check"], ids["contract"], json.dumps({"type": "artifact-exists"})),
        )
    return ids


@pytest.fixture(scope="session")
def offline_model(tmp_path_factory: pytest.TempPathFactory) -> Iterator[object]:
    from panestria.inference.runtime import ModelRuntime

    runtime = ModelRuntime(ROOT / ".panestria-runtime/models", tmp_path_factory.mktemp("model-socket"), gpu=True)
    try:
        runtime.start()
        yield runtime
    finally:
        runtime.stop()


@pytest.fixture(autouse=True)
def r1_evidence_metadata(request: pytest.FixtureRequest, record_property: pytest.RecordProperty) -> None:
    import hashlib

    names = {
        "test_aos_006.py",
        "test_aos_007.py",
        "test_aos_008.py",
        "test_aos_009.py",
        "test_aos_010.py",
        "test_native_profile.py",
        "test_sandbox_cancellation.py",
        "test_native_tool_gateway.py",
        "test_invocations.py",
        "test_build_invocation_fence.py",
        "test_claude_proposal.py",
        "test_proposal_demo.py",
        "test_scoped_bash.py",
        "test_admitted_native_build.py",
        "test_owner_build_cli.py",
        "test_aos_011.py",
        "test_aos_012.py",
        "test_aos_014.py",
        "test_aos_015.py",
        "test_aos_016.py",
        "test_aos_017.py",
        "test_aos_018.py",
        "test_aos_027a.py",
        "test_build_evidence.py",
        "test_approval_revocation.py",
        "test_build_snapshot.py",
        "test_memory_context.py",
        "test_local_provider.py",
        "test_local_benchmark.py",
        "test_model_runtime.py",
        "test_ask_kernel.py",
        "test_ask_api.py",
        "test_ask_cli.py",
        "test_resource_admission.py",
        "test_telemetry.py",
        "test_memory_api.py",
        "test_memory_review.py",
        "test_memory_restore.py",
        "test_primary_lease.py",
        "test_sandboxed_verifier.py",
        "test_protected_merge.py",
    }
    path = Path(str(request.node.path))
    if path.name not in names:
        return
    candidate = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
    fixture_bytes = path.read_bytes() + (ROOT / "uv.lock").read_bytes()
    if path.name in {"test_aos_027a.py", "test_build_evidence.py", "test_approval_revocation.py"}:
        fixture_bytes += path.with_name("build_support.py").read_bytes()
    if path.name == "test_approval_revocation.py":
        fixture_bytes += path.with_name("test_aos_027a.py").read_bytes()
    if path.name == "test_scoped_bash.py":
        fixture_bytes += path.with_name("test_registered_check_authority.py").read_bytes()
    if path.name == "test_admitted_native_build.py":
        fixture_bytes += path.with_name("test_scoped_bash.py").read_bytes()
        fixture_bytes += path.with_name("test_registered_check_authority.py").read_bytes()
    fingerprint = hashlib.sha256(fixture_bytes).hexdigest()
    record_property("candidate_commit", candidate)
    record_property("fixture_digest", fingerprint)
    record_property("worktree_state", "dirty" if dirty.strip() else "clean")
    record_property("lane", "live" if request.node.get_closest_marker("live") else "integration")
