"""Loopback HTTP server for the scoped goal API.

Start with ``python -m panestria.api.serve``. The process binds the configured
loopback address and probes PostgreSQL from ``/readyz``. It does not listen on
any other interface. It runs under uvicorn with the shared server configuration
and ``TransportLimits`` (``api/serving.py``), which keep the request bounds this
module used to enforce with its own HTTP parser. Accepted goals are continued
only by a journey passed to ``main``; ``python -m panestria_devkit.api.serve``
passes the synthetic R0 one.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import psycopg
import uvicorn

from panestria.api.auth import GoalApi
from panestria.api.health import default_readiness_probe
from panestria.api.main import create_app, mount_goal_api
from panestria.api.serving import GOAL_API_PROTOCOL, TransportLimits, owned_socket, server_config
from panestria.config import ProfileRejected, load_settings
from panestria.config_local import LocalApplicationRejected

SYNTHETIC_OWNER = "00000000-0000-4000-8000-000000000002"
SYNTHETIC_PROJECT = "00000000-0000-4000-8000-000000000003"


class Journey(Protocol):
    """Continues accepted goals off the request path. HTTP handlers only submit the goal id."""

    def start(self) -> None: ...

    def submit(self, goal_id: str) -> None: ...

    def stop(self) -> None: ...


# (database_url, owner_id, project_id, sandbox) -> journey. The product server
# registers none; the dev-only R0 server (panestria_devkit.api.serve) passes the
# synthetic one.
JourneyFactory = Callable[[str, str, str, Path], Journey]


def _seed(database_url: str, owner_id: str, project_id: str) -> None:
    with psycopg.connect(database_url, connect_timeout=2) as connection:
        connection.execute(
            "INSERT INTO panestria.principal (id, display_name) VALUES (%s, 'synthetic-owner')"
            " ON CONFLICT (id) DO NOTHING",
            (owner_id,),
        )
        connection.execute(
            "INSERT INTO panestria.project (id, owner_id) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING",
            (project_id, owner_id),
        )
        connection.commit()


def main(journey: JourneyFactory | None = None) -> None:
    token = os.environ.pop("PANESTRIA_TOKEN", "")
    owner = os.environ.pop("PANESTRIA_OWNER_ID", SYNTHETIC_OWNER)
    project = os.environ.pop("PANESTRIA_PROJECT_ID", SYNTHETIC_PROJECT)
    sandbox = Path(os.environ.pop("PANESTRIA_SANDBOX", "/tmp/panestria-r0")).resolve()
    try:
        settings = load_settings()
    except ProfileRejected as exc:
        sys.stderr.write(f"{exc.code}\n")
        raise SystemExit(2) from None
    if len(token) < 16:
        sys.stderr.write("missing_token\n")
        raise SystemExit(2)
    sandbox.mkdir(parents=True, exist_ok=True)
    database_url = settings.database_url.get_secret_value()
    try:
        _seed(database_url, owner, project)
    except psycopg.Error:
        sys.stderr.write("database_unavailable\n")
        raise SystemExit(2) from None
    application = create_app(settings, default_readiness_probe)
    mount_goal_api(application, GoalApi(token, owner, project, database_url))
    # The artifact route reads evidence from this root, with or without a journey.
    application.state.sandbox = sandbox
    application.add_middleware(TransportLimits)
    try:
        listener = owned_socket(settings.bind_host, settings.bind_port)
    except LocalApplicationRejected as exc:
        sys.stderr.write(f"{exc.code}\n")
        raise SystemExit(2) from None
    driver = None if journey is None else journey(database_url, owner, project, sandbox)
    application.state.journey = driver
    if driver is not None:
        driver.start()
    try:
        uvicorn.Server(server_config(application, http=GOAL_API_PROTOCOL)).run(sockets=[listener])
    finally:
        listener.close()
        if driver is not None:
            driver.stop()


if __name__ == "__main__":
    main()
