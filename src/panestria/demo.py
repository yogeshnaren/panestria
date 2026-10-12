"""Synthetic loopback demo.

Requires a migrated PostgreSQL database and these environment variables:

- ``PANESTRIA_DATABASE_URL``
- ``PANESTRIA_TOKEN`` (at least 16 characters)
- ``PANESTRIA_SCHEMA_VERSION``, ``PANESTRIA_PROFILE``, ``PANESTRIA_BIND_HOST``,
  ``PANESTRIA_BIND_PORT``, and ``PANESTRIA_READINESS_BUDGET_MS``

``make r0-demo`` starts the loopback server and drives submit, approval, evidence,
and completion with the real CLI. Each run uses a new goal id and idempotency key.
It does not claim a fresh-host result.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "docs" / "fixtures" / "synthetic-goal-contract.json"


def _cli(base: str, token: str, *args: str) -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, "-m", "panestria.cli.main", *args, "--base-url", base, "--token", token],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        sys.stderr.write(completed.stderr)
        raise SystemExit(completed.returncode or 1)
    loaded = json.loads(completed.stdout)
    if not isinstance(loaded, dict):
        raise SystemExit(1)
    return loaded


def _wait_approval(base: str, token: str, goal_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        listed = _cli(base, token, "approvals")
        approvals = listed.get("approvals")
        if isinstance(approvals, list):
            for item in approvals:
                if isinstance(item, dict) and item.get("goal_id") == goal_id:
                    return item
        time.sleep(0.5)
    sys.stderr.write("approval wait expired\n")
    raise SystemExit(1)


def main() -> None:
    token = os.environ.get("PANESTRIA_TOKEN", "")
    if os.environ.get("PANESTRIA_DATABASE_URL", "") == "" or len(token) < 16:
        sys.stderr.write("demo requires PANESTRIA_DATABASE_URL and PANESTRIA_TOKEN\n")
        raise SystemExit(2)
    os.environ.setdefault("PANESTRIA_SCHEMA_VERSION", "1")
    os.environ.setdefault("PANESTRIA_PROFILE", "SYNTHETIC_DEV")
    os.environ.setdefault("PANESTRIA_BIND_HOST", "127.0.0.1")
    os.environ.setdefault("PANESTRIA_BIND_PORT", "8765")
    os.environ.setdefault("PANESTRIA_READINESS_BUDGET_MS", "1000")
    os.environ.setdefault("PANESTRIA_SANDBOX", tempfile.mkdtemp(prefix="panestria-r0-"))
    port = os.environ["PANESTRIA_BIND_PORT"]
    base = f"http://127.0.0.1:{port}"
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("PANESTRIA_") or key in {
            "PANESTRIA_SCHEMA_VERSION",
            "PANESTRIA_PROFILE",
            "PANESTRIA_BIND_HOST",
            "PANESTRIA_BIND_PORT",
            "PANESTRIA_READINESS_BUDGET_MS",
            "PANESTRIA_DATABASE_URL",
            "PANESTRIA_TOKEN",
            "PANESTRIA_OWNER_ID",
            "PANESTRIA_PROJECT_ID",
            "PANESTRIA_SANDBOX",
        }
    }
    server = subprocess.Popen(
        [sys.executable, "-m", "panestria.api.serve"],
        cwd=ROOT,
        env=env,
    )
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if server.poll() is not None:
                sys.stderr.write("server exited before it accepted connections\n")
                raise SystemExit(1)
            try:
                with urllib.request.urlopen(f"{base}/healthz", timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.1)
        else:
            sys.stderr.write("server did not become live\n")
            raise SystemExit(1)
        document = json.loads(FIXTURE.read_text())
        document["goal_id"] = str(uuid4())
        demo_key = str(document["goal_id"])
        contract = Path(os.environ["PANESTRIA_SANDBOX"]) / "contract.json"
        contract.write_text(json.dumps(document))
        submitted = _cli(
            base,
            token,
            "goal",
            "submit",
            "--contract",
            str(contract),
            "--idempotency-key",
            f"r0-demo-{demo_key}",
        )
        goal_id = str(submitted["goal_id"])
        consent = _wait_approval(base, token, goal_id)
        _cli(
            base,
            token,
            "approve",
            str(consent["approval_id"]),
            "--effect-digest",
            str(consent["effect_digest"]),
            "--expected-version",
            str(consent["expected_version"]),
            "--idempotency-key",
            f"r0-demo-consent-{demo_key}",
        )
        merge = _wait_approval(base, token, goal_id)
        events = _cli(base, token, "goal", "events", goal_id)
        raw_events = events.get("events")
        event_rows = raw_events if isinstance(raw_events, list) else []
        recorded = [
            item for item in event_rows if isinstance(item, dict) and item.get("kind") == "evidence.recorded"
        ]
        if recorded:
            payload = recorded[-1].get("payload")
            if isinstance(payload, dict) and isinstance(payload.get("artifact_id"), str):
                _cli(base, token, "artifact", "show", payload["artifact_id"])
        _cli(
            base,
            token,
            "approve",
            str(merge["approval_id"]),
            "--effect-digest",
            str(merge["effect_digest"]),
            "--expected-version",
            str(merge["expected_version"]),
            "--idempotency-key",
            f"r0-demo-merge-{demo_key}",
        )
        finished = time.monotonic() + 30
        while time.monotonic() < finished:
            status = _cli(base, token, "goal", "status", goal_id)
            if status.get("status") == "COMPLETED":
                sys.stdout.write(json.dumps(status) + "\n")
                return
            time.sleep(0.5)
        sys.stderr.write("goal did not complete\n")
        raise SystemExit(1)
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    main()
