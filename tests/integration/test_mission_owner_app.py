"""Mission Control on the owner app in real Chromium: one pairing, CSRF token and logout per scope.

``panestria serve`` runs on a real loopback port with the production dashboard
build, real PostgreSQL and real HTTP. The model, hardware and Build run service
are the fixtures of ``test_owner_serve.py``; Ask answers through a mock model
transport. Each pairing code comes from the ``panestria pair-code`` CLI.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from test_local_provider import transport, valid_frames
from test_owner_serve import Owner, running
from test_owner_serve import owner_setup as owner_setup  # noqa: F401

from browser_support import browser_node
from panestria.api import owner
from panestria.api.sessions import SESSION_SECONDS, SessionScope

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "apps/mission-control/dist"


def _journey(owner_setup: Owner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **options: Any) -> dict[str, Any]:
    """Run ``tests/owner-app.mjs`` against ``serve_owner`` with the production dashboard build."""
    owner_setup.assets = ASSETS
    built = owner.build_app

    def answering(profile: Any) -> Any:
        application = built(profile)
        application.state.ask_api.provider.transport = transport(valid_frames())[0]
        return application

    monkeypatch.setattr(owner, "build_app", answering)
    fixture = tmp_path / "browser.json"
    fixture.write_text(
        json.dumps(
            {
                "origin": owner_setup.config.origin,
                "python": sys.executable,
                "config": str(owner_setup.path),
                "plan": str(uuid4()),
                **options,
            }
        )
    )
    fixture.chmod(0o600)
    with running(owner_setup, monkeypatch):
        result = subprocess.run(
            [browser_node(), "tests/owner-app.mjs"],
            cwd=ROOT / "apps/mission-control",
            env={
                **os.environ,
                "PANESTRIA_BROWSER_FIXTURE": str(fixture),
                "PANESTRIA_BROWSER_SCREENSHOT": str(tmp_path / "owner-app.png"),
            },
            capture_output=True,
            text=True,
            timeout=120,
        )
    assert result.returncode == 0, result.stdout + result.stderr
    assert owner_setup.token not in result.stdout + result.stderr
    outcome: dict[str, Any] = json.loads(result.stdout.strip().splitlines()[-1])
    return outcome


@pytest.mark.requires_browser
def test_browser_pairs_uses_and_logs_out_each_scope_alone(
    owner_setup: Owner,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    record_property: Any,
) -> None:
    record_property("mode", "ACTUAL_CHROMIUM_HTTP_PG__TEST_FIXTURE_NOT_LIVE_MODEL_PROCESS_HARDWARE")
    outcome = _journey(owner_setup, monkeypatch, tmp_path)
    with psycopg.connect(owner_setup.task["dsn"]) as db:
        asked = db.execute(
            "SELECT state FROM panestria.ask_request WHERE id=%s AND project_id=%s",
            (outcome["asked"], str(owner_setup.config.project_id)),
        ).fetchone()
        # The journey pairs one session at a time: Ask, Build, Build again, Activity, Ask again.
        sessions = db.execute(
            "SELECT extract(epoch FROM expires_at - created_at)::int, revoked_at IS NOT NULL"
            " FROM panestria.browser_session WHERE project_id=%s ORDER BY created_at",
            (str(owner_setup.config.project_id),),
        ).fetchall()
    assert asked == ("COMPLETED",)
    # Each scope's session lasts its own lifetime: a working day for Activity and Ask,
    # an hour for Build. Each logout revoked its own session on the server. The first
    # Ask session lost its CSRF token on reload and the second Build session its
    # cookie; neither was logged out, and each expires on its own.
    assert sessions == [
        (SESSION_SECONDS["ask"], False),
        (SESSION_SECONDS["build"], True),
        (SESSION_SECONDS["build"], False),
        (SESSION_SECONDS["activity"], True),
        (SESSION_SECONDS["ask"], True),
    ]
    assert SESSION_SECONDS == {"activity": 8 * 3600, "ask": 8 * 3600, "build": 3600}
    target = os.environ.get("PANESTRIA_MISSION_SCREENSHOT")
    if target:
        import shutil

        shutil.copyfile(tmp_path / "owner-app.png", target)


@pytest.mark.requires_browser
@pytest.mark.parametrize("left_out", ["activity", "build"])
def test_browser_refuses_a_page_whose_scopes_differ_from_the_server(
    owner_setup: Owner,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    left_out: SessionScope,
) -> None:
    loaded = owner.load_mission_assets

    def without(directory: Path, *, session_scopes: tuple[SessionScope, ...] = ()) -> dict[str, bytes]:
        return loaded(directory, session_scopes=tuple(s for s in session_scopes if s != left_out))

    monkeypatch.setattr(owner, "load_mission_assets", without)
    assert _journey(owner_setup, monkeypatch, tmp_path, mismatch=left_out) == {"mismatch": left_out}
