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
            (ids["contract"], ids["goal"], json.dumps({"autonomy_profile_ref": "test-policy-v1"}), "ab" * 32),
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
