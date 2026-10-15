"""CLI redaction and operation separation; actual OS run remains isolated."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from pydantic import SecretBytes
from typer.testing import CliRunner

from panestria.cli import profile
from panestria.cli.main import app
from panestria.memory.keys import KeyStoreUnavailable


class Store:
    def __init__(self):
        self.calls = []
        self.error = None

    def provision(self, handle):
        self.calls.append(("provision", handle))
        if self.error:
            raise self.error

    def load(self, handle):
        self.calls.append(("load", handle))
        if self.error:
            raise self.error
        return SecretBytes(b"synthetic-do-not-print-key-bytes!!")


@pytest.fixture
def store(monkeypatch):
    store = Store()
    monkeypatch.setattr(profile, "SecretServiceProfileKeys", lambda: store)
    return store


def test_explicit_setup_prints_only_a_scoped_handle_and_check_never_provisions(store):
    owner, project = str(uuid4()), str(uuid4())
    runner = CliRunner()
    result = runner.invoke(app, ["profile", "key-create", "--owner-id", owner, "--project-id", project])
    assert result.exit_code == 0
    body = json.loads(result.output)
    assert body["status"] == "PRESENT" and body["schema_version"] == 1
    handle = body["handle"]
    assert handle["owner_id"] == owner and handle["project_id"] == project
    assert len(handle) == 4 and store.calls[0][0] == "provision"
    args = [value for name, value in handle.items() for value in ("--" + name.replace("_", "-"), value)]
    checked = runner.invoke(app, ["profile", "key-check", *args])
    assert checked.exit_code == 0 and json.loads(checked.output) == body
    assert [call[0] for call in store.calls] == ["provision", "load"]
    assert "synthetic-do-not-print" not in result.output + checked.output


@pytest.mark.parametrize("operation", ["key-create", "key-check"])
def test_invalid_handles_never_touch_the_key_store(store, operation):
    result = CliRunner().invoke(
        app,
        [
            "profile",
            operation,
            "--owner-id",
            "private-sentinel",
            "--project-id",
            str(uuid4()),
            "--profile-id",
            str(uuid4()),
            "--key-id",
            str(uuid4()),
        ],
    )
    assert result.exit_code == 2 and "invalid_profile_key_handle" in result.output
    assert "private-sentinel" not in result.output and not store.calls


@pytest.mark.parametrize("code", ["key_store_locked", "key_handle_missing", "key_creation_unknown"])
def test_unavailable_store_returns_fixed_reason_without_fallback(store, code):
    store.error = KeyStoreUnavailable(code)
    result = CliRunner().invoke(
        app, ["profile", "key-create", "--owner-id", str(uuid4()), "--project-id", str(uuid4())]
    )
    body = json.loads(result.output)
    assert result.exit_code == 2 and body["code"] == code and len(body["handle"]) == 4
    assert body["handle"] == store.calls[0][1].model_dump()
    assert len(store.calls) == 1
