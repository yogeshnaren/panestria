"""Owner-only explicit memory writes and correction/suppression preserve lineage."""

from __future__ import annotations

from pathlib import Path

from test_aos_009 import _client
from test_ask_kernel import initialize
from test_local_provider import transport, valid_frames

from panestria.api.main import mount_ask_api
from panestria.api.routes.ask import AskApi
from panestria.inference.local import LocalProvider
from panestria.resources.hardware import HardwareProbe

ARCHIVE = Path(__file__).resolve().parents[2] / "docs/specification/attachments/agentos-skills-v0.1.0.zip"
CLI = {"Authorization": "Bearer test-only-cli-token-at-least-16"}


def test_explicit_memory_http_lifecycle(r1_task: dict[str, str], tmp_path: Path) -> None:
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
    document = {"body": "Storage preference: use SQLite", "label": "PRIVATE", "pinned": True}
    assert client.post("/v1/memory", json={**document, "approved": True}, headers=CLI).status_code == 422
    original = client.post("/v1/memory", json=document, headers=CLI)
    assert original.status_code == 201
    ref = original.json()
    hits = client.get("/v1/memory/search", params={"q": "Which storage do I prefer?"}, headers=CLI).json()["hits"]
    assert hits[0]["ref"]["revision_id"] == ref["revision_id"] and "SQLite" in hits[0]["body"]
    current = client.post(
        f"/v1/memory/{ref['item_id']}/correct",
        json={"expected_version": 0, "document": {**document, "body": "Storage preference: use PostgreSQL"}},
        headers=CLI,
    )
    assert current.status_code == 201 and current.json()["revision"] == 2
    assert current.json()["source_id"] != ref["source_id"]
    public = client.post(
        f"/v1/memory/{ref['item_id']}/correct",
        json={"expected_version": 1, "document": {**document, "label": "PUBLIC"}},
        headers=CLI,
    )
    assert public.status_code == 422 and public.json()["code"] == "privacy_downgrade_requires_review"
    assert (
        client.post(f"/v1/memory/{ref['item_id']}/suppress", json={"expected_version": 1}, headers=CLI).status_code
        == 200
    )
    assert client.get("/v1/memory/search", params={"q": "storage"}, headers=CLI).json()["hits"] == []
    assert calls == []  # Explicit memory operations never trigger inference or inferred writes.
