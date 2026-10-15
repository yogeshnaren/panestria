"""Actual pg_dump/pg_restore preserves memory lineage, labels, pins and observed stages."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from test_ask_kernel import initialize

from panestria.contracts.memory import MemoryObservation, MemorySubmission
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.uow import UnitOfWork
from panestria.memory.classification import MemoryClassificationService
from panestria.memory.service import MemoryService


def _fixture_container() -> str:
    # Match the isolated fixture's purpose and exact bound port. Never address
    # the owner's R0 database or a generic compose service/container name.
    found = subprocess.check_output(
        ["docker", "ps", "--filter", "label=panestria.purpose=r1-test", "--format", "{{.ID}}"], text=True
    ).splitlines()
    inspected = json.loads(subprocess.check_output(["docker", "inspect", *found], text=True)) if found else []
    matches = [
        item["Id"]
        for item in inspected
        if any(
            binding.get("HostIp") == "127.0.0.1" and binding.get("HostPort") == "55439"
            for binding in (item["NetworkSettings"]["Ports"].get("5432/tcp") or [])
        )
    ]
    assert len(matches) == 1, "isolated_restore_fixture_not_identified"
    return matches[0]


def test_revision_suppression_restore(
    r1_task: dict[str, str], tmp_path: Path, record_property: pytest.RecordProperty
) -> None:
    record_property("gate_case_id", "AOS-011-TC04")
    record_property("source_clauses", "AOS-011-F01,AOS-011-F02,AOS-011-AC02,AOS-011-AC03")
    actor, _ = initialize(r1_task, tmp_path)
    memory = MemoryService()
    with psycopg.connect(r1_task["dsn"]) as c:
        uow = UnitOfWork(c)
        original = memory.add(
            uow, actor, MemorySubmission(body="Use MySQL for the project", label="PRIVATE", pinned=True)
        )
        corrected = memory.correct(
            uow,
            actor,
            original.item_id,
            0,
            MemorySubmission(body="Use PostgreSQL for the project", label="PRIVATE", pinned=True),
        )
        suppressed = memory.add(uow, actor, MemorySubmission(body="Outdated PostgreSQL preference", label="RESTRICTED"))
        memory.suppress(uow, actor, suppressed.item_id, 0)
        for stage in ("retrieved", "included", "used_by_worker", "judged_unused", "candidate_helped"):
            memory.record_usage(
                uow,
                actor,
                corrected,
                MemoryObservation(
                    stage=stage,
                    observer_kind="human" if stage == "candidate_helped" else "application",
                    observer_id="explicit-synthetic-test-observer",
                    evidence_ref="synthetic-owner-assessment" if stage == "candidate_helped" else None,
                ),
            )
        before = memory.history(uow, actor, original.item_id)
        hidden_before = memory.history(uow, actor, suppressed.item_id)
        classifier = MemoryClassificationService()
        classification_before = [classifier.get(uow, actor, ref.source_id) for ref in (original, corrected, suppressed)]
    container = _fixture_container()
    dump = subprocess.run(
        [
            "docker",
            "exec",
            container,
            "pg_dump",
            "--username=panestria_synthetic",
            "--dbname=panestria_synthetic",
            "--format=custom",
            "--no-owner",
            "--no-acl",
        ],
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert dump.returncode == 0, "synthetic_dump_failed"
    assert 0 < len(dump.stdout) < 8 * 1024 * 1024, "synthetic_dump_size_limit"
    record_property("backup_sha256", hashlib.sha256(dump.stdout).hexdigest())
    restore_name = "panestria_restore_" + uuid4().hex
    params = conninfo_to_dict(r1_task["dsn"])
    params["dbname"] = restore_name
    restored_dsn = make_conninfo(**params)
    with psycopg.connect(r1_task["dsn"], autocommit=True) as administrative:
        administrative.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(restore_name)))
        try:
            restored = subprocess.run(
                [
                    "docker",
                    "exec",
                    "-i",
                    container,
                    "pg_restore",
                    "--username=panestria_synthetic",
                    "--dbname=" + restore_name,
                    "--no-owner",
                    "--no-acl",
                    "--exit-on-error",
                ],
                input=dump.stdout,
                capture_output=True,
                timeout=60,
                check=False,
            )
            assert restored.returncode == 0, "synthetic_restore_failed"
            with psycopg.connect(restored_dsn) as c:
                uow = UnitOfWork(c)
                assert memory.history(uow, actor, original.item_id) == before
                assert memory.history(uow, actor, suppressed.item_id) == hidden_before
                assert [classifier.get(uow, actor, ref.source_id) for ref in (original, corrected, suppressed)] == (
                    classification_before
                )
                recalled = memory.search(uow, actor, "PostgreSQL")
                assert len(recalled) == 1 and recalled[0].ref == corrected and recalled[0].pinned
                assert recalled[0].label == "PRIVATE" and recalled[0].explanation == "owner_pin"
                stages = c.execute(
                    "SELECT stage,confidence FROM panestria.memory_use_event WHERE item_id=%s ORDER BY stage",
                    (original.item_id,),
                ).fetchall()
                assert stages == [
                    (stage, None)
                    for stage in sorted(
                        ("retrieved", "included", "used_by_worker", "judged_unused", "candidate_helped")
                    )
                ]
                with pytest.raises(KernelDenied, match="not_found"), c.transaction():
                    memory.search(uow, Actor(str(uuid4()), actor.project_id), "PostgreSQL")
                with pytest.raises(KernelDenied, match="not_found"), c.transaction():
                    memory.history(uow, Actor(actor.owner_id, str(uuid4())), original.item_id)
                with pytest.raises(psycopg.Error, match="immutable"), c.transaction():
                    c.execute(
                        "UPDATE panestria.memory_revision SET body='tampered' WHERE id=%s", (corrected.revision_id,)
                    )
        finally:
            # Only remove the unique database created above inside the disposable
            # fixture container; no source table/volume or owner database is reset.
            administrative.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(restore_name)))
