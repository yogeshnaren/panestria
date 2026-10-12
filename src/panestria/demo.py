"""Synthetic loopback demo.

Requires a migrated PostgreSQL database and these environment variables:

- ``PANESTRIA_DATABASE_URL``
- ``PANESTRIA_TOKEN`` (at least 16 characters)
- ``PANESTRIA_SCHEMA_VERSION``, ``PANESTRIA_PROFILE``, ``PANESTRIA_BIND_HOST``,
  ``PANESTRIA_BIND_PORT``, and ``PANESTRIA_READINESS_BUDGET_MS``

``make r0-demo`` reuses an authenticated loopback server or starts its own,
then drives submit, approval, evidence, and completion with the real CLI.
``make r0-review`` also serves a read-only run snapshot for browser review.
Each run uses a new goal id and idempotency key. It does not claim a fresh-host result.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from panestria.api.health import Liveness
from panestria.api.views import ApprovalList
from panestria.config import ProfileRejected, load_settings
from panestria.review import serve_report

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


def _get(base: str, path: str, token: str = "") -> object:
    # http.client neither follows redirects nor consults proxy environment variables.
    from urllib.parse import urlsplit

    parts = urlsplit(base)
    connection = http.client.HTTPConnection(str(parts.hostname), parts.port, timeout=2)
    try:
        connection.request("GET", path, headers={"Authorization": f"Bearer {token}"} if token else {})
        response = connection.getresponse()
        raw = response.read(65537)
        if response.status != 200 or len(raw) > 65536:
            raise ValueError("incompatible API")
        return json.loads(raw)
    finally:
        connection.close()


def _running_api(base: str, token: str) -> bool:
    try:
        health = _get(base, "/healthz")
    except ConnectionRefusedError:
        return False
    except (OSError, ValueError, http.client.HTTPException):
        raise SystemExit("api_port_in_use: the listener is not a compatible Panestria API") from None
    try:
        Liveness.model_validate(health)
        ApprovalList.model_validate(_get(base, "/v1/approvals", token))
    except (OSError, ValueError, ValidationError, http.client.HTTPException):
        raise SystemExit(
            "api_port_in_use: cannot authenticate the existing Panestria API; check PANESTRIA_TOKEN"
        ) from None
    return True


def run_demo() -> dict[str, object]:
    token = os.environ.pop("PANESTRIA_TOKEN", "")
    if os.environ.get("PANESTRIA_DATABASE_URL", "") == "" or len(token) < 16:
        sys.stderr.write("demo requires PANESTRIA_DATABASE_URL and PANESTRIA_TOKEN\n")
        raise SystemExit(2)
    os.environ.setdefault("PANESTRIA_SCHEMA_VERSION", "1")
    os.environ.setdefault("PANESTRIA_PROFILE", "SYNTHETIC_DEV")
    os.environ.setdefault("PANESTRIA_BIND_HOST", "127.0.0.1")
    os.environ.setdefault("PANESTRIA_BIND_PORT", "8765")
    os.environ.setdefault("PANESTRIA_READINESS_BUDGET_MS", "1000")
    owner = os.environ.pop("PANESTRIA_OWNER_ID", "00000000-0000-4000-8000-000000000002")
    project = os.environ.pop("PANESTRIA_PROJECT_ID", "00000000-0000-4000-8000-000000000003")
    sandbox_setting = os.environ.pop("PANESTRIA_SANDBOX", "")
    try:
        settings = load_settings()
    except ProfileRejected as exc:
        sys.stderr.write(f"{exc.code}\n")
        raise SystemExit(2) from None
    if settings.bind_host != "127.0.0.1":
        sys.stderr.write("invalid_bind: the demo CLI requires 127.0.0.1\n")
        raise SystemExit(2)
    base = f"http://127.0.0.1:{settings.bind_port}"
    reused = _running_api(base, token)
    sandbox = Path(sandbox_setting or tempfile.mkdtemp(prefix="panestria-r0-"))
    sandbox.mkdir(parents=True, exist_ok=True)
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("PANESTRIA_")
        or key
        in {
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
    env.update(
        PANESTRIA_TOKEN=token, PANESTRIA_OWNER_ID=owner, PANESTRIA_PROJECT_ID=project, PANESTRIA_SANDBOX=str(sandbox)
    )
    server = (
        None
        if reused
        else subprocess.Popen(
            [sys.executable, "-m", "panestria.api.serve"],
            cwd=ROOT,
            env=env,
        )
    )
    sys.stderr.write("Reusing the running Panestria API.\n" if reused else "Starting a temporary Panestria API.\n")
    try:
        if server is not None:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if server.poll() is not None:
                    sys.stderr.write("server exited before it accepted connections\n")
                    raise SystemExit(1)
                if _running_api(base, token):
                    break
                time.sleep(0.1)
            else:
                sys.stderr.write("server did not become live\n")
                raise SystemExit(1)
        document = json.loads(FIXTURE.read_text())
        document["goal_id"] = str(uuid4())
        document["owner_id"] = owner
        document["project_id"] = project
        demo_key = str(document["goal_id"])
        contract = sandbox / f"contract-{demo_key}.json"
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
        consent_receipt = _cli(
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
        recorded = [item for item in event_rows if isinstance(item, dict) and item.get("kind") == "evidence.recorded"]
        payload = recorded[-1].get("payload") if recorded else None
        if not isinstance(payload, dict) or not isinstance(payload.get("artifact_id"), str):
            raise SystemExit("missing_evidence: demo will not approve a merge without its artifact")
        artifact = _cli(base, token, "artifact", "show", payload["artifact_id"])
        if payload.get("verdict") != "PASS" or payload.get("artifact_sha256") != artifact.get("sha256"):
            raise SystemExit("unverified_candidate: demo will not approve a merge without matching passing evidence")
        merge_receipt = _cli(
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
                source = subprocess.run(
                    ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
                ).stdout.strip()
                dirty = bool(
                    subprocess.run(
                        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=True
                    ).stdout.strip()
                )
                report: dict[str, object] = {
                    "status": status,
                    "artifact": artifact,
                    "verification": payload,
                    "approvals": [
                        {"label": "Contract consent", "request": consent, "receipt": consent_receipt},
                        {"label": "Synthetic merge", "request": merge, "receipt": merge_receipt},
                    ],
                    "events": _cli(base, token, "goal", "events", goal_id),
                    "base_url": base,
                    "api_reused": reused,
                    "source_commit": source,
                    "source_worktree_dirty": dirty,
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                }
                report_path = sandbox / f"review-{demo_key}.json"
                report_path.write_text(json.dumps(report, indent=2) + "\n")
                sys.stderr.write(f"Run receipt: {report_path}\n")
                return report
            time.sleep(0.5)
        sys.stderr.write("goal did not complete\n")
        raise SystemExit(1)
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the synthetic R0 CLI journey.")
    parser.add_argument("--review", action="store_true", help="serve a read-only run snapshot afterward")
    parser.add_argument("--review-port", type=int, default=8870)
    args = parser.parse_args()
    if not 1 <= args.review_port <= 65535:
        parser.error("review port must be between 1 and 65535")
    report = run_demo()
    sys.stdout.write(json.dumps(report["status"]) + "\n")
    sys.stdout.flush()
    if args.review:
        serve_report(report, args.review_port)


if __name__ == "__main__":
    main()
