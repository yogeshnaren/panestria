"""Supported local Ask lifecycle, separate from the historical R0 synthetic server."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import resource
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import psycopg
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from panestria.api.auth import GoalApi, LoopbackDenied, authorize, error_body
from panestria.api.db import DatabaseUnavailable, open_database
from panestria.api.health import default_readiness_probe
from panestria.api.local_protocol import LocalHttpProtocol
from panestria.api.local_web import mount_local_web
from panestria.api.main import create_app, mount_activity_api, mount_ask_api, mount_browser_api
from panestria.api.routes.ask import AskApi
from panestria.api.routes.profiles import ProfileApi
from panestria.api.sessions import BrowserAccess
from panestria.config import Settings, ValidatedSettings
from panestria.config_activity import ActivitySettings
from panestria.config_local import LocalApplicationRejected, LocalApplicationSettings, load_local_settings
from panestria.contracts.inference import InferenceUnavailable
from panestria.inference.local import LocalProvider
from panestria.inference.runtime import ModelRuntime
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.local_setup import offline_policy
from panestria.kernel.repositories.policy import current_policy
from panestria.kernel.sessions import SessionService
from panestria.kernel.uow import UnitOfWork
from panestria.resources.admission import admit
from panestria.resources.hardware import HardwareProbe, ProbeUnavailable

SCHEMA_HEAD = "0037_repair_draft_intents"


def require_setup(settings: ValidatedSettings, actor: Actor) -> str:
    with open_database(settings.database_url.get_secret_value()) as c:
        if c.execute("SELECT version_num FROM alembic_version").fetchall() != [(SCHEMA_HEAD,)]:
            raise KernelDenied("local_schema_migration_required")
        policy = current_policy(UnitOfWork(c), actor)
        receipt = c.execute(
            "SELECT policy_sha256 FROM panestria.local_project_setup WHERE owner_id=%s AND project_id=%s",
            (actor.owner_id, actor.project_id),
        ).fetchone()
        if receipt is None or policy != offline_policy(actor) or str(receipt[0]).strip() != policy.sha256():
            raise KernelDenied("local_setup_policy_conflict")
        return f"project-policy:{policy.version}:{policy.sha256()}"


def owned_listener(config: LocalApplicationSettings) -> socket.socket:
    listener = socket.socket(socket.AF_INET6 if config.bind_host == "::1" else socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if config.bind_host == "::1":
            listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        listener.bind((config.bind_host, config.bind_port))
        # Reserve the port exclusively throughout startup. Two SO_REUSEADDR
        # sockets may otherwise bind the same address before either listens.
        listener.listen(16)
        listener.setblocking(False)
        return listener
    except OSError:
        listener.close()
        raise LocalApplicationRejected("local_bind_unavailable") from None


def build_local_app(
    config: LocalApplicationSettings,
    settings: ValidatedSettings,
    token: str,
    *,
    profiles: ProfileApi | None = None,
    mission_assets: Path | None = None,
) -> FastAPI:
    if mission_assets is not None and (profiles is not None or config.bind_host != "127.0.0.1"):
        raise LocalApplicationRejected("mission_ask_scope_unavailable")
    actor = Actor(str(config.owner_id), str(config.project_id))
    model = ModelRuntime(config.model_cache, config.runtime_directory / "model", preserve_existing=True)
    provider = LocalProvider(model.socket_path)
    archive = Path(__file__).resolve().parents[3] / "docs/specification/attachments/agentos-skills-v0.1.0.zip"
    probe = HardwareProbe(archive)
    ask = AskApi(provider, probe.collect_cpu)
    app = create_app(settings, default_readiness_probe)
    # Scope without exposing unrelated synthetic goal/merge/tool routes.
    api = GoalApi(token, actor.owner_id, actor.project_id, settings.database_url.get_secret_value())
    app.state.goal_api = api
    mount_activity_api(app)
    mount_ask_api(app, ask)
    if profiles is not None:
        from panestria.api.main import mount_profile_api

        mount_profile_api(app, profiles)
    if mission_assets is None:
        session_secret = hmac.digest(token.encode(), b"panestria.local-browser-session.v1", hashlib.sha256)
        mount_browser_api(app, BrowserAccess(config.origin, SessionService(session_secret), api.database_url))
        mount_local_web(app)
    else:
        from panestria.api.mission_web import mount_mission_control

        observation = ActivitySettings(
            schema_version=1,
            owner_id=config.owner_id,
            project_id=config.project_id,
            bind_port=config.bind_port,
            token_file=config.token_file,
        )
        mount_mission_control(app, observation, token, mission_assets, offline_ask=True)
    app.state.local_model = model
    app.state.local_failure = None
    base_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        try:
            await asyncio.to_thread(require_setup, settings, actor)
            config.runtime_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            info = config.runtime_directory.stat()
            if config.runtime_directory.is_symlink() or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise LocalApplicationRejected("local_runtime_directory_not_private")
            admission = admit(await asyncio.to_thread(probe.collect_cpu), gpu=False)
            if admission.decision != "PERMIT":
                raise InferenceUnavailable(admission.reasons[0])
            await asyncio.to_thread(model.start)
            async with base_lifespan(application):
                yield
        except (KernelDenied, InferenceUnavailable, LocalApplicationRejected) as exc:
            app.state.local_failure = exc.code
            raise
        except (psycopg.Error, DatabaseUnavailable):
            app.state.local_failure = "database_unavailable"
            raise LocalApplicationRejected("database_unavailable") from None
        except (OSError, ProbeUnavailable):
            app.state.local_failure = "local_runtime_unavailable"
            raise LocalApplicationRejected("local_runtime_unavailable") from None
        finally:
            ask.governor.stop_admissions()
            active = list(ask.active.values())
            for task in active:
                task.cancel()
            await asyncio.gather(*active, return_exceptions=True)
            try:
                await asyncio.to_thread(model.stop)
            except InferenceUnavailable:
                app.state.local_failure = "local_owned_runtime_cleanup_failed"
            app.state.health.shutdown()

    app.router.lifespan_context = lifespan

    @app.get("/v1/local/status")
    async def status(request: Request) -> JSONResponse:
        try:
            authorize(request, api)
            ref = await asyncio.to_thread(require_setup, settings, actor)
            return JSONResponse(
                content={
                    "schema_version": 1,
                    "owner_id": actor.owner_id,
                    "project_id": actor.project_id,
                    "policy_ref": ref,
                    "trust_profile": "SYNTHETIC_DEV",
                    "runtime_certified": False,
                    "model_socket_present": model.socket_path.is_socket(),
                    "model_catalog": "checked_per_inference",
                    "admission": ask.governor.status(),
                    "profiles": "DISABLED" if profiles is None else "EXPLICITLY_ENABLED",
                    "cloud_routes": "UNMOUNTED",
                    "resource_headroom": "rechecked_per_inference",
                    "release_gate": "NOT_EVALUATED",
                }
            )
        except LoopbackDenied as exc:
            return JSONResponse(status_code=exc.status_code, content=error_body(exc.code))
        except KernelDenied as exc:
            return JSONResponse(status_code=503, content=error_body(exc.code))
        except (DatabaseUnavailable, psycopg.Error):
            return JSONResponse(status_code=503, content=error_body("database_unavailable"))

    return app


def server_config(app: FastAPI) -> uvicorn.Config:
    # Installed source confirms TRACE wraps ASGI messages and access logs include
    # query strings. Fixed NullHandlers prevent accidental exception/body output.
    logging = {
        "version": 1,
        "disable_existing_loggers": False,
        "handlers": {"discard": {"class": "logging.NullHandler"}},
        "loggers": {
            name: {"handlers": ["discard"], "level": "CRITICAL", "propagate": False}
            for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "uvicorn.asgi")
        },
    }
    return uvicorn.Config(
        app,
        host="127.0.0.1",
        workers=1,
        reload=False,
        proxy_headers=False,
        http=LocalHttpProtocol,
        ws="none",
        interface="asgi3",
        lifespan="on",
        access_log=False,
        log_config=logging,
        log_level="critical",
        server_header=False,
        limit_concurrency=16,
        backlog=16,
        timeout_keep_alive=2,
        timeout_graceful_shutdown=5,
        h11_max_incomplete_event_size=32768,
    )


def serve_local(path: Path, *, profiles: ProfileApi | None = None, mission_assets: Path | None = None) -> None:
    config, token = load_local_settings(path)
    settings = Settings(
        database_url=os.environ.get("PANESTRIA_DATABASE_URL", ""),
        bind_host=config.bind_host,
        bind_port=config.bind_port,
    ).validate_profile()
    # No personal prompt, key or token can be included in a core dump.
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    listener = owned_listener(config)
    app = None
    try:
        app = build_local_app(
            config, settings, token.get_secret_value(), profiles=profiles, mission_assets=mission_assets
        )
        server = uvicorn.Server(server_config(app))
        print(json.dumps({"schema_version": 1, "status": "STARTING", "origin": config.origin}), flush=True)
        try:
            server.run(sockets=[listener])
        except SystemExit:
            raise LocalApplicationRejected(app.state.local_failure or "local_startup_failed") from None
        if app.state.local_failure:
            raise LocalApplicationRejected(app.state.local_failure)
        if not server.started:
            raise LocalApplicationRejected("local_startup_failed")
    finally:
        listener.close()
        if app is not None:
            app.state.health.shutdown()
