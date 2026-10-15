"""Run the isolated native review demo without touching the R0 database."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
import uvicorn

from panestria.api.proposal_demo import create_demo_app
from panestria.brokers.harness.claude_proposal import ClaudeProposalAdapter
from panestria.brokers.harness.cli_profile import BinaryPin
from panestria.execution.proposal_demo import DemoUnavailable, ProposalDemo, _lock
from panestria.kernel.sessions import SessionService
from panestria.kernel.uow import UnitOfWork

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DSN = "postgresql://panestria_demo:placeholder-not-a-secret@127.0.0.1:55438/panestria_native_demo"
IMAGE = "postgres@sha256:ca0bd484cb98bf4b24eb1010e73fb3fcbd6714d240fbc1a10eea5b7dbecb641d"
CONTAINER = "panestria-native-review-demo-db"
VOLUME = "panestria_native_review_demo_pgdata"
BINARY = Path("/home/yogesh/.local/share/claude/versions/2.1.273")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init", "serve", "pair", "status", "qualify", "reconcile"])
    parser.add_argument("--root", type=Path, default=Path.home() / ".local/share/panestria/native-review-demo")
    parser.add_argument("--port", type=int, default=8871)
    parser.add_argument("--goal", default=None)
    parser.add_argument("--claude-binary", type=Path, default=BINARY)
    parser.add_argument("--claude-config", type=Path, default=Path.home() / ".panestria-native-claude")
    args = parser.parse_args()
    dsn = os.environ.get("PANESTRIA_DEMO_DATABASE_URL", DEFAULT_DSN)
    # This convenience command cannot point at the owner R0 DB or a remote DB.
    parts = urlsplit(dsn)
    if parts.hostname != "127.0.0.1" or parts.port != 55438 or parts.path != "/panestria_native_demo":
        raise SystemExit("demo_database_scope_denied: use the dedicated loopback database on 55438")
    if not 1024 <= args.port <= 65535:
        raise SystemExit("invalid_demo_port")
    if args.command == "init":
        found = subprocess.run(["docker", "inspect", CONTAINER], capture_output=True, text=True)
        if found.returncode == 0:
            body = json.loads(found.stdout)[0]
            if body["Config"].get("Labels", {}).get("panestria.purpose") != "native-review-demo":
                raise SystemExit("existing_container_not_owned_by_demo")
            if body["Config"]["Image"] != IMAGE:
                raise SystemExit("existing_demo_database_image_changed")
            subprocess.run(["docker", "start", CONTAINER], check=True, capture_output=True)
        else:
            subprocess.run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    CONTAINER,
                    "--label",
                    "panestria.purpose=native-review-demo",
                    "--publish",
                    "127.0.0.1:55438:5432",
                    "--env",
                    "POSTGRES_USER=panestria_demo",
                    "--env",
                    "POSTGRES_PASSWORD=placeholder-not-a-secret",
                    "--env",
                    "POSTGRES_DB=panestria_native_demo",
                    "--mount",
                    f"type=volume,source={VOLUME},target=/var/lib/postgresql/data",
                    IMAGE,
                ],
                check=True,
                capture_output=True,
            )
        deadline = time.monotonic() + 30
        while True:
            try:
                with psycopg.connect(dsn, connect_timeout=1):
                    break
            except psycopg.OperationalError:
                if time.monotonic() >= deadline:
                    raise SystemExit("demo_database_unavailable") from None
                time.sleep(0.2)
        subprocess.run(
            [str(ROOT / ".venv/bin/alembic"), "-c", "migrations/alembic.ini", "upgrade", "head"],
            cwd=ROOT,
            env={**os.environ, "PANESTRIA_DATABASE_URL": dsn},
            check=True,
        )
    from panestria.brokers.harness.claude_proposal import PINNED_BINARY_SHA256

    adapter = ClaudeProposalAdapter(
        BinaryPin(args.claude_binary, PINNED_BINARY_SHA256),
        args.claude_config,
        ROOT / "docs/specification/attachments/agentos-skills-v0.1.0.zip",
    )
    demo = ProposalDemo(args.root.absolute(), dsn, adapter)
    if args.command == "init":
        demo.initialize()
        print("Isolated native demo initialized. No inference was requested.")
    elif args.command == "serve":
        with _lock(demo.root / "server.lock"):
            demo.recover()
            uvicorn.run(
                create_demo_app(demo, f"http://127.0.0.1:{args.port}"),
                host="127.0.0.1",
                port=args.port,
                access_log=False,
                log_level="warning",
            )
    elif args.command == "pair":
        service = SessionService(bytes.fromhex(demo.identity["session_secret"]))
        with demo.connect() as connection:
            code = service.issue_pairing_code(UnitOfWork(connection), demo.actor, ttl_seconds=300)
        print(f"Pairing code: {code} (valid for 5 minutes)")
    elif args.command == "qualify":
        result = demo.qualify()
        print(json.dumps(result))
        if result["status"] != "PASS":
            raise SystemExit(1)
    elif args.command == "reconcile":
        if not args.goal:
            raise SystemExit("--goal is required")
        demo.reconcile(args.goal)
        print("Recorded merge reconciled; no new worker was started.")
    else:
        print(json.dumps(demo.view(), indent=2))


if __name__ == "__main__":
    try:
        main()
    except DemoUnavailable as exc:
        raise SystemExit(str(exc)) from None
