"""AI-P2b: suppression is only lifted explicitly, and the newest conflicting fact wins."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from test_aos_009 import _client
from test_ask_kernel import initialize
from test_local_provider import transport, valid_frames

from panestria.api.main import mount_ask_api
from panestria.api.routes.ask import AskApi
from panestria.contracts.memory import MemorySubmission
from panestria.inference.local import LocalProvider
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.uow import UnitOfWork
from panestria.memory.context import ContextCompiler
from panestria.memory.service import MemoryService
from panestria.resources.hardware import HardwareProbe

CLI = {"Authorization": "Bearer test-only-cli-token-at-least-16"}
ARCHIVE = Path(__file__).resolve().parents[2] / "docs/specification/attachments/agentos-skills-v0.1.0.zip"


def test_ai_p2b_correction_never_reactivates_and_unsuppress_is_explicit(r1_task):
    actor, service = Actor(r1_task["owner"], r1_task["project"]), MemoryService()
    with psycopg.connect(r1_task["dsn"]) as c:
        uow = UnitOfWork(c)
        ref = service.add(uow, actor, MemorySubmission(body="Deploy on Fridays", label="INTERNAL"))
        assert service.suppress(uow, actor, ref.item_id, 0) == 1
        c.commit()
        with pytest.raises(KernelDenied, match="^memory_suppressed$"), c.transaction():
            service.correct(uow, actor, ref.item_id, 1, MemorySubmission(body="Deploy on Mondays", label="INTERNAL"))
        assert service.search(uow, actor, "Deploy") == []
        with pytest.raises(KernelDenied, match="version_conflict"), c.transaction():
            service.unsuppress(uow, actor, ref.item_id, 0)
        with pytest.raises(KernelDenied, match="not_found"), c.transaction():
            service.unsuppress(uow, Actor(actor.owner_id, str(uuid4())), ref.item_id, 1)
        assert service.unsuppress(uow, actor, ref.item_id, 1) == 2
        assert service.unsuppress(uow, actor, ref.item_id, 2) == 2  # Already active: unchanged.
        corrected = service.correct(
            uow, actor, ref.item_id, 2, MemorySubmission(body="Deploy on Mondays", label="INTERNAL")
        )
        c.commit()
        assert corrected.revision == 2 and corrected.row_version == 3
        assert [hit.body for hit in service.search(uow, actor, "Deploy")] == ["Deploy on Mondays"]


def test_ai_p2b_newest_fact_per_conflict_key_wins_and_pins_are_not_dropped(r1_task):
    actor, service, compiler = Actor(r1_task["owner"], r1_task["project"]), MemoryService(), ContextCompiler()
    now = datetime.now(UTC)
    with psycopg.connect(r1_task["dsn"]) as c:
        uow = UnitOfWork(c)

        def fact(body, key, age, **changes):
            document = MemorySubmission(
                body=body, label="INTERNAL", conflict_key=key, valid_from=now - timedelta(days=age), **changes
            )
            return service.add(uow, actor, document)

        old = fact("Database host is alpha", "db-host", 3)
        new = fact("Database host is bravo", "db-host", 1)
        other = fact("Database port is 5432", "db-port", 2)
        c.commit()
        pack = compiler.compose(uow, actor, str(uuid4()), "Which host and port?", "INTERNAL")
        c.commit()
        assert {ref.item_id for ref in pack.sources} == {new.item_id, other.item_id}
        assert "alpha" not in pack.prompt and "bravo" in pack.prompt
        sources = c.execute("SELECT metadata->'sources' FROM panestria.context_pack WHERE id=%s", (pack.id,)).fetchone()
        flags = {item["item_id"]: (item["included"], item.get("superseded", False)) for item in sources[0]}
        assert flags[old.item_id] == (False, True) and flags[new.item_id] == (True, False)
        assert c.execute(
            "SELECT stage FROM panestria.memory_use_event WHERE context_pack_id=%s AND item_id=%s",
            (pack.id, old.item_id),
        ).fetchall() == [("retrieved",)]
        compiler.revalidate(uow, actor, pack)
        # A pinned fact superseded by a newer one is surfaced as a conflict, never dropped.
        service.correct(
            uow,
            actor,
            old.item_id,
            0,
            MemorySubmission(
                body="Database host is alpha",
                label="INTERNAL",
                conflict_key="db-host",
                valid_from=now - timedelta(days=3),
                pinned=True,
            ),
        )
        c.commit()
        with pytest.raises(KernelDenied, match="^pinned_memory_conflict$"), c.transaction():
            compiler.compose(uow, actor, str(uuid4()), "Which host and port?", "INTERNAL")


def test_ai_p2b_v2_http_unsuppress(r1_task, tmp_path):
    initialize(r1_task, tmp_path)
    client = _client(r1_task)
    mocked, calls = transport(valid_frames())
    mount_ask_api(
        client.app,
        AskApi(
            LocalProvider(Path("/synthetic"), transport=mocked),
            lambda: HardwareProbe(ARCHIVE).collect(preset="omen-8gb"),
        ),
    )
    document = {"schema_version": 2, "body": "Synthetic lifecycle preference", "label": "INTERNAL"}
    item = client.post("/v2/memory", json=document, headers=CLI).json()["item_id"]
    path = f"/v2/memory/{item}"
    assert client.post(path + "/suppress", json={"expected_version": 0}, headers=CLI).json()["row_version"] == 1
    refused = client.post(path + "/correct", json={"expected_version": 1, "document": document}, headers=CLI)
    assert refused.status_code == 422 and refused.json()["code"] == "memory_suppressed"
    restored = client.post(path + "/unsuppress", json={"expected_version": 1}, headers=CLI)
    assert restored.status_code == 200
    assert json.loads(restored.text) == {"schema_version": 2, "item_id": item, "row_version": 2, "state": "ACTIVE"}
    stale = client.post(path + "/unsuppress", json={"expected_version": 0}, headers=CLI)
    assert stale.status_code == 422 and stale.json()["code"] == "version_conflict"
    assert calls == []
