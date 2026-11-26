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
from typing import Any

import psycopg
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from panestria.api.app import Activity, AppProfile, Ask, Browser, Feature, Profiles, build_app, scope_dependencies
from panestria.api.auth import GoalApi, LoopbackDenied, authorize, error_body
from panestria.api.db import DatabaseUnavailable, open_database
from panestria.api.local_protocol import LocalHttpProtocol
from panestria.api.local_web import LocalWeb
from panestria.api.routes.ask import AskApi
from panestria.api.routes.profiles import ProfileApi
from panestria.api.serving import owned_socket
from panestria.api.serving import server_config as server_config  # Re-exported for existing callers.
from panestria.api.sessions import BrowserAccess, SessionScope
from panestria.assets import skills_archive
from panestria.config import Settings, ValidatedSettings
from panestria.config_activity import ActivitySettings
from panestria.config_local import LocalApplicationRejected, LocalApplicationSettings, load_local_settings
from panestria.contracts.inference import InferenceUnavailable
from panestria.contracts.policy import PolicyContext
from panestria.inference.local import LocalProvider
from panestria.inference.runtime import ModelRuntime
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.local_setup import ask_policy
from panestria.kernel.sessions import SessionService
from panestria.kernel.uow import UnitOfWork
from panestria.resources.admission import admit
from panestria.resources.hardware import HardwareProbe, ProbeUnavailable

SCHEMA_HEAD = "0042_task_event_kind_indexes"


def require_setup(settings: ValidatedSettings, actor: Actor, *, accept_successor: bool = False) -> PolicyContext:
    """The current schema and the policy Ask runs under (``local_setup.ask_policy``)."""
    with open_database(settings.database_url.get_secret_value()) as c:
        if c.execute("SELECT version_num FROM alembic_version").fetchall() != [(SCHEMA_HEAD,)]:
            raise KernelDenied("local_schema_migration_required")
        return ask_policy(UnitOfWork(c), actor, accept_successor=accept_successor)


def owned_listener(config: LocalApplicationSettings) -> socket.socket:
    return owned_socket(config.bind_host, config.bind_port)


@dataclass(frozen=True)
class AskRuntime:
    """The owned model, its provider and the Ask API for one local configuration."""

    actor: Actor
    model: ModelRuntime
    provider: LocalProvider
    probe: HardwareProbe
    ask: AskApi

    @classmethod
    def create(cls, config: LocalApplicationSettings) -> AskRuntime:
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
        return cls(Actor(str(config.owner_id), str(config.project_id)), model, provider, probe, ask)

    def lifecycle(
        self,
        config: LocalApplicationSettings,
        settings: ValidatedSettings,
        api: GoalApi,
        *,
        profiles_enabled: bool = False,
        scope: tuple[SessionScope, ...] = (),
        accept_successor_policy: bool = False,
    ) -> LocalAskRuntime:
        return LocalAskRuntime(
            config,
            settings,
            self.actor,
            api,
            self.model,
            self.provider,
            self.probe,
            self.ask,
            profiles_enabled=profiles_enabled,
            scope=scope,
            accept_successor_policy=accept_successor_policy,
        )


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
    runtime = AskRuntime.create(config)
    actor = runtime.actor
    # Scope without exposing unrelated synthetic goal/merge/tool routes.
    api = GoalApi(token, actor.owner_id, actor.project_id, settings.database_url.get_secret_value())
    features: list[Feature] = [Activity(), Ask(runtime.ask)]
    if profiles is not None:
        features.append(Profiles(profiles))
    if mission_assets is None:
        session_secret = hmac.digest(token.encode(), b"panestria.local-browser-session.v1", hashlib.sha256)
        access = BrowserAccess(config.origin, SessionService(session_secret), api.database_url)
        features += [Browser(access), LocalWeb()]
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
    features.append(runtime.lifecycle(config, settings, api, profiles_enabled=profiles is not None))
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
    scope: tuple[SessionScope, ...] = ()
    # The owner app: Ask also runs under an owner-applied successor policy (``local_setup.ask_policy``).
    accept_successor_policy: bool = False

    def mount(self, app: FastAPI) -> None:
        config, settings, actor, api = self.config, self.settings, self.actor, self.api
        model, provider, probe, ask = self.model, self.provider, self.probe, self.ask
        profiles_enabled, successor = self.profiles_enabled, self.accept_successor_policy
        app.state.local_model = model
        app.state.local_failure = None
        base_lifespan = app.router.lifespan_context

        @asynccontextmanager
        async def lifespan(application: FastAPI) -> AsyncIterator[None]:
            try:
                await asyncio.to_thread(require_setup, settings, actor, accept_successor=successor)
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

        @app.get("/v1/local/status", dependencies=scope_dependencies(self.scope))
        async def status(request: Request) -> JSONResponse:
            try:
                authorize(request, api)
                policy = await asyncio.to_thread(require_setup, settings, actor, accept_successor=successor)
                return JSONResponse(
                    content={
                        "schema_version": 1,
                        "owner_id": actor.owner_id,
                        "project_id": actor.project_id,
                        "policy_ref": f"project-policy:{policy.version}:{policy.sha256()}",
                        "trust_profile": policy.trust.profile,
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
        run_owned(app, listener, {"schema_version": 1, "status": "STARTING", "origin": config.origin})
    finally:
        listener.close()
        if app is not None:
            app.state.health.shutdown()


def run_owned(
    app: FastAPI,
    listener: socket.socket,
    announcement: dict[str, Any],
    *,
    http: type[LocalHttpProtocol] = LocalHttpProtocol,
) -> None:
    """Serve an app with a ``LocalAskRuntime`` on its owned listener until stopped.

    A startup or shutdown failure raises with the runtime's fixed reason.
    """
    server = uvicorn.Server(server_config(app, http=http))
    print(json.dumps(announcement), flush=True)
    try:
        server.run(sockets=[listener])
    except SystemExit:
        raise LocalApplicationRejected(app.state.local_failure or "local_startup_failed") from None
    if app.state.local_failure:
        raise LocalApplicationRejected(app.state.local_failure)
    if not server.started:
        raise LocalApplicationRejected("local_startup_failed")
