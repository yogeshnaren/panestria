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
from dataclasses import dataclass, field
from pathlib import Path

import psycopg
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from panestria.api.app import Activity, AppProfile, Ask, Browser, Feature, Profiles, build_app
from panestria.api.auth import GoalApi, LoopbackDenied, authorize, error_body
from panestria.api.db import DatabaseUnavailable, open_database
from panestria.api.local_web import LocalWeb
from panestria.api.routes.ask import AskApi
from panestria.api.routes.profiles import ProfileApi
from panestria.api.serving import owned_socket
from panestria.api.serving import server_config as server_config  # Re-exported for existing callers.
from panestria.api.sessions import BrowserAccess
from panestria.assets import skills_archive
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

SCHEMA_HEAD = "0042_task_event_kind_indexes"


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
    return owned_socket(config.bind_host, config.bind_port)


def local_profile(
    config: LocalApplicationSettings,
    settings: ValidatedSettings,
    token: str,
    *,
    profiles: ProfileApi | None = None,
    mission_assets: Path | None = None,
) -> AppProfile:
    """Offline Ask with its owned model; the Ask page or Mission Control, never both."""
    if mission_assets is not None and (profiles is not None or config.bind_host != "127.0.0.1"):
        raise LocalApplicationRejected("mission_ask_scope_unavailable")
    actor = Actor(str(config.owner_id), str(config.project_id))
    model = ModelRuntime(config.model_cache, config.runtime_directory / "model", preserve_existing=True)
    provider = LocalProvider(model.socket_path)
    probe = HardwareProbe(skills_archive())
    ask = AskApi(
        provider,
        probe.collect_cpu,
        include_charter=config.assistant_charter,
        lossless_presentation=config.lossless_presentation,
        pin_model_manifest=config.pin_model_manifest,
    )
    # Scope without exposing unrelated synthetic goal/merge/tool routes.
    api = GoalApi(token, actor.owner_id, actor.project_id, settings.database_url.get_secret_value())
    features: list[Feature] = [Activity(), Ask(ask)]
    if profiles is not None:
        features.append(Profiles(profiles))
    if mission_assets is None:
        session_secret = hmac.digest(token.encode(), b"panestria.local-browser-session.v1", hashlib.sha256)
        features += [
            Browser(BrowserAccess(config.origin, SessionService(session_secret), api.database_url)),
            LocalWeb(),
        ]
    else:
        from panestria.api.mission_web import MissionControl

        observation = ActivitySettings(
            schema_version=1,
            owner_id=config.owner_id,
            project_id=config.project_id,
            bind_port=config.bind_port,
            token_file=config.token_file,
        )
        features.append(MissionControl(observation, token, mission_assets, offline_ask=True))
    features.append(
        LocalAskRuntime(
            config, settings, actor, api, model, provider, probe, ask, profiles_enabled=profiles is not None
        )
    )
    return AppProfile(settings, api, tuple(features))


def build_local_app(
    config: LocalApplicationSettings,
    settings: ValidatedSettings,
    token: str,
    *,
    profiles: ProfileApi | None = None,
    mission_assets: Path | None = None,
) -> FastAPI:
    return build_app(local_profile(config, settings, token, profiles=profiles, mission_assets=mission_assets))


@dataclass(frozen=True)
class LocalAskRuntime:
    """The owned model's lifecycle and ``/v1/local/status``. Mount it last: it wraps every lifespan."""

    config: LocalApplicationSettings
    settings: ValidatedSettings
    actor: Actor
    api: GoalApi = field(repr=False)
    model: ModelRuntime
    provider: LocalProvider
    probe: HardwareProbe
    ask: AskApi
    profiles_enabled: bool = False

    def mount(self, app: FastAPI) -> None:
        config, settings, actor, api = self.config, self.settings, self.actor, self.api
        model, provider, probe, ask = self.model, self.provider, self.probe, self.ask
        profiles_enabled = self.profiles_enabled
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
                if config.pin_model_manifest:
                    descriptor = await asyncio.to_thread(model.describe_manifest)
                    provider.bind_manifest(descriptor)
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
                        "profiles": "EXPLICITLY_ENABLED" if profiles_enabled else "DISABLED",
                        "assistant_charter": "SHARED_DATA_FREE_V1" if config.assistant_charter else "LEGACY_CONTEXT",
                        "lossless_presentation": "STRUCTURED_PROFILE_ONLY"
                        if config.lossless_presentation
                        else "DISABLED",
                        "model_manifest": provider.model_manifest.model_dump(mode="json")
                        if config.pin_model_manifest and provider.model_manifest is not None
                        else None,
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
