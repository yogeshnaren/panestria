"""Pin limits hold at write time; FTS text is never operator syntax and uses the index."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
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
from panestria.memory import context
from panestria.memory.context import ContextCompiler
from panestria.memory.service import PINNED_MEMORY_LIMIT, MemoryService
from panestria.resources.hardware import HardwareProbe

ARCHIVE = Path(__file__).resolve().parents[2] / "docs/specification/attachments/agentos-skills-v0.1.0.zip"
CLI = {"Authorization": "Bearer test-only-cli-token-at-least-16"}
# The default Ask that the TUI and Mission Control send: 2048 context, 128 output, 128 framing.
DEFAULT_ASK_BUDGET = 2048 - 128 - 128


def _pin(body: str, **changes: Any) -> MemorySubmission:
    return MemorySubmission(body=body, label="CONFIDENTIAL", pinned=True, **changes)


def _items(c: psycopg.Connection[Any], actor: Actor) -> int:
    row = c.execute("SELECT count(*) FROM panestria.memory_item WHERE project_id=%s", (actor.project_id,)).fetchone()
    assert row is not None
    return int(row[0])


def test_oversize_pin_is_refused_before_it_can_block_ask(r1_task: dict[str, str]) -> None:
    actor, service = Actor(r1_task["owner"], r1_task["project"]), MemoryService()
    with psycopg.connect(r1_task["dsn"]) as c:
        uow = UnitOfWork(c)
        with pytest.raises(KernelDenied, match="^memory_pin_budget_exceeded$"), c.transaction():
            service.add(uow, actor, _pin("x" * 6000))
        assert _items(c, actor) == 0
        # Unpinned memory of the same size stays allowed; Ask drops it instead of failing.
        large = service.add(uow, actor, MemorySubmission(body="PostgreSQL " * 545, label="CONFIDENTIAL"))
        c.commit()
        with pytest.raises(KernelDenied, match="^memory_pin_budget_exceeded$"), c.transaction():
            service.correct(uow, actor, large.item_id, 0, _pin("PostgreSQL " * 545))
        row = c.execute(
            "SELECT pinned,row_version,current_revision FROM panestria.memory_item WHERE id=%s", (large.item_id,)
        ).fetchone()
        assert row == (False, 0, 1)
        for compiler in (ContextCompiler(), ContextCompiler(include_charter=True)):
            pack = compiler.compose(uow, actor, str(uuid4()), "PostgreSQL?", "PUBLIC", token_budget=DEFAULT_ASK_BUDGET)
            assert pack.sources == ()
        c.commit()


def test_pinned_set_budget_covers_add_correct_and_unsuppress(r1_task: dict[str, str]) -> None:
    actor, service = Actor(r1_task["owner"], r1_task["project"]), MemoryService()
    with psycopg.connect(r1_task["dsn"]) as c:
        uow = UnitOfWork(c)
        first = service.add(uow, actor, _pin("Units: metric. " + "a" * 200))
        c.commit()
        # Each pin fits alone; the set does not, so the second is refused.
        with pytest.raises(KernelDenied, match="^memory_pin_budget_exceeded$"), c.transaction():
            service.add(uow, actor, _pin("Tone: brief. " + "b" * 200))
        service.suppress(uow, actor, first.item_id, 0)
        second = service.add(uow, actor, _pin("Tone: brief. " + "b" * 200))
        c.commit()
        with pytest.raises(KernelDenied, match="^memory_pin_budget_exceeded$"), c.transaction():
            service.unsuppress(uow, actor, first.item_id, 1)
        # Growing the only pin past the budget is refused; a fitting correction succeeds.
        with pytest.raises(KernelDenied, match="^memory_pin_budget_exceeded$"), c.transaction():
            service.correct(uow, actor, second.item_id, 0, _pin("Tone: brief. " + "b" * 900))
        service.correct(uow, actor, second.item_id, 0, _pin("Tone: brief and direct. " + "b" * 200))
        # Pins past retention no longer reach Ask, so they no longer use the budget.
        c.execute(
            "UPDATE panestria.memory_item SET retain_until=clock_timestamp() - interval '1 second' WHERE id=%s",
            (second.item_id,),
        )
        assert service.unsuppress(uow, actor, first.item_id, 1) == 2
        c.commit()
        # Whatever the pin check accepts composes in the default Ask, charter included,
        # with room for a short question.
        question = "Which units should the answer use, and how brief should it be? " * 3
        pack = ContextCompiler(include_charter=True).compose(
            uow, actor, str(uuid4()), question, "PUBLIC", token_budget=DEFAULT_ASK_BUDGET
        )
        assert [source.item_id for source in pack.sources] == [first.item_id]
        c.commit()


def test_pin_count_limit(r1_task: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    # The byte budget normally binds first; lift it to reach the count limit.
    monkeypatch.setattr(context, "PINNED_CONTEXT_BUDGET", 1 << 20)
    actor, service = Actor(r1_task["owner"], r1_task["project"]), MemoryService()
    with psycopg.connect(r1_task["dsn"]) as c:
        uow = UnitOfWork(c)
        for index in range(PINNED_MEMORY_LIMIT):
            service.add(uow, actor, _pin(f"Pinned preference {index}"))
        c.commit()
        with pytest.raises(KernelDenied, match="^memory_pin_limit_exceeded$"), c.transaction():
            service.add(uow, actor, _pin("One pin too many"))
        unpinned = service.add(uow, actor, MemorySubmission(body="Plain note", label="CONFIDENTIAL"))
        with pytest.raises(KernelDenied, match="^memory_pin_limit_exceeded$"), c.transaction():
            service.correct(uow, actor, unpinned.item_id, 0, _pin("Plain note"))
        c.commit()
        # The default search page still returns every pin instead of pinned_memory_limit.
        hits = service.search(uow, actor, "preference")
        assert sum(hit.pinned for hit in hits) == PINNED_MEMORY_LIMIT


def test_concurrent_pins_are_serialized(r1_task: dict[str, str]) -> None:
    actor, service = Actor(r1_task["owner"], r1_task["project"]), MemoryService()
    with psycopg.connect(r1_task["dsn"]) as first, psycopg.connect(r1_task["dsn"]) as second:
        second.execute("SET lock_timeout='200ms'")
        second.commit()
        service.add(UnitOfWork(first), actor, _pin("Units: metric. " + "a" * 200))
        # Unpinned writes never wait for the pin set.
        service.add(UnitOfWork(second), actor, MemorySubmission(body="Plain note", label="CONFIDENTIAL"))
        second.commit()
        # A second pin waits for the first instead of checking a stale pin set.
        with pytest.raises(psycopg.errors.LockNotAvailable):
            service.add(UnitOfWork(second), actor, _pin("Tone: brief. " + "b" * 200))
        second.rollback()
        first.commit()
        with pytest.raises(KernelDenied, match="^memory_pin_budget_exceeded$"):
            service.add(UnitOfWork(second), actor, _pin("Tone: brief. " + "b" * 200))
        second.rollback()


def test_operator_text_is_plain_search_text(r1_task: dict[str, str]) -> None:
    actor, service = Actor(r1_task["owner"], r1_task["project"]), MemoryService()
    with psycopg.connect(r1_task["dsn"]) as c:
        uow = UnitOfWork(c)
        freezer = service.add(uow, actor, MemorySubmission(body="The freezer holds -5 degrees", label="INTERNAL"))
        oven = service.add(uow, actor, MemorySubmission(body="Bake bread at 220 degrees", label="INTERNAL"))
        tomatoes = service.add(uow, actor, MemorySubmission(body="Water the tomatoes daily", label="INTERNAL"))
        storage = service.add(uow, actor, MemorySubmission(body="Prefer PostgreSQL for storage", label="INTERNAL"))
        c.commit()

        def refs(query: str) -> list[object]:
            return [hit.ref for hit in service.search(uow, actor, query)]

        # "-5" is a lexeme, not negation; the exact match ranks first.
        assert refs("-5 degrees") == [freezer, oven]
        assert refs("degrees") in ([freezer, oven], [oven, freezer])
        # Ordinary multi-word search keeps OR semantics across lexemes.
        assert set(refs("tomatoes storage")) == {tomatoes, storage}
        assert refs("Which storage do I prefer?") == [storage]
        # websearch/tsquery operators and quoting are inert text.
        for query in ['"tomatoes', "tomatoes OR", "-tomatoes", "tomatoes & | ! <-> :*", "it's tomatoes\\"]:
            assert refs(query) == [tomatoes], query
        for query in ["-", "OR", "!", "the a of", "'"]:
            assert refs(query) == [], query
        c.commit()


class _ExplainingUnitOfWork(UnitOfWork):
    """Record the planner's choice for the memory search statement, then run it."""

    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        super().__init__(connection)
        self.plans: list[str] = []

    def execute(self, query: str, params: tuple[object, ...] = ()) -> psycopg.Cursor[tuple[Any, ...]]:
        if "ts_rank_cd" in query:
            row = self.connection.execute("EXPLAIN (FORMAT JSON) " + query, params).fetchone()
            assert row is not None
            self.plans.append(json.dumps(row[0]))
        return super().execute(query, params)


def test_scoped_search_uses_the_fts_index(r1_task: dict[str, str]) -> None:
    actor, service = Actor(r1_task["owner"], r1_task["project"]), MemoryService()
    with psycopg.connect(r1_task["dsn"]) as c:
        uow = _ExplainingUnitOfWork(c)
        target = service.add(uow, actor, MemorySubmission(body="Prefer PostgreSQL for storage", label="INTERNAL"))
        for index in range(250):
            service.add(uow, actor, MemorySubmission(body=f"Unrelated note {index}", label="INTERNAL"))
        c.commit()
        c.execute("ANALYZE panestria.memory_item, panestria.memory_revision, panestria.memory_source")
        # Sequential scans stay cheaper until about 20,000 revisions. Disabling them
        # asks only whether the FTS predicate can reach ix_memory_fts; the previous
        # query filtered a materialized CTE, so no plan could use the index.
        c.execute("SET LOCAL enable_seqscan=off")
        assert [hit.ref for hit in service.search(uow, actor, "PostgreSQL storage")] == [target]
        assert len(uow.plans) == 1 and '"Index Name": "ix_memory_fts"' in uow.plans[0], uow.plans
        c.rollback()


def test_pin_refusals_surface_through_http(r1_task: dict[str, str], tmp_path: Path) -> None:
    initialize(r1_task, tmp_path)
    client: Any = _client(r1_task)
    mocked, calls = transport(valid_frames())
    mount_ask_api(
        client.app,
        AskApi(
            LocalProvider(Path("/synthetic"), transport=mocked),
            lambda: HardwareProbe(ARCHIVE).collect(preset="omen-8gb"),
        ),
    )
    oversize = {"body": "x" * 6000, "label": "INTERNAL", "pinned": True}
    for route, document in [("/v1/memory", oversize), ("/v2/memory", {**oversize, "schema_version": 2})]:
        refused = client.post(route, json=document, headers=CLI)
        assert refused.status_code == 422 and refused.json()["code"] == "memory_pin_budget_exceeded", route
    note = client.post("/v1/memory", json={**oversize, "pinned": False}, headers=CLI).json()
    for route in [f"/v1/memory/{note['item_id']}/correct", f"/v2/memory/{note['item_id']}/correct"]:
        document = {**oversize, "schema_version": 2} if route.startswith("/v2") else oversize
        refused = client.post(route, json={"expected_version": 0, "document": document}, headers=CLI)
        assert refused.status_code == 422 and refused.json()["code"] == "memory_pin_budget_exceeded", route
    pin = {"body": "Units: metric. " + "a" * 200, "label": "INTERNAL", "pinned": True}
    first = client.post("/v1/memory", json=pin, headers=CLI).json()
    assert client.post(f"/v1/memory/{first['item_id']}/suppress", json={"expected_version": 0}, headers=CLI).is_success
    assert client.post("/v1/memory", json=pin, headers=CLI).status_code == 201
    refused = client.post(f"/v2/memory/{first['item_id']}/unsuppress", json={"expected_version": 1}, headers=CLI)
    assert refused.status_code == 422 and refused.json()["code"] == "memory_pin_budget_exceeded"
    hits = client.get("/v1/memory/search", params={"q": "-5 degrees"}, headers=CLI).json()["hits"]
    assert all(hit["pinned"] for hit in hits)  # Only the pin, never stray negation matches.
    assert calls == []
