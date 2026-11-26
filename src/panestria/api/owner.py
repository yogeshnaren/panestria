"""The Release 1 owner app: Ask, Build and activity on one port, each behind its own session scope.

The single-mode servers allow one Mission Control mode per process, because a
mode's one browser session carries all of that mode's authority. The owner app
mounts Ask, Build review, plan acceptance and Build runs together instead, and
splits browser authority by scope (``sessions.BrowserScopes``):

- ``activity``: content-free observation (``/v1/activity``, Build progress,
  capabilities). A session for any scope may read these.
- ``ask``: questions, memory, corrections and ``/v1/local/status``.
- ``build``: Build review and decisions, plan staging and acceptance, runs.

Each scope is paired separately under ``/v1/session/{scope}``, and its session
key is derived for that scope alone. The dashboard page names the mounted scopes
(``data-session-scopes``), so Mission Control offers one pairing, CSRF token and
logout per scope; ``/v1/mission/capabilities`` reports the same scopes. A stolen Ask or activity session
therefore cannot read a Build diff, approve a Build or start a run. A Build
session lasts an hour, the others eight. The loopback bearer (CLI) is unchanged
and may use every route.

``panestria serve`` runs this app (``serve_owner``). Its configuration is the
local Ask configuration, which names the one token and the one port, plus an
optional Build configuration. The dashboard defaults to the build packaged with
panestria. Setting up Build applies a broader policy to the same project; Ask
still starts under it (``local_setup.ask_policy``). The R0 goal, approval and
artifact routes are not mounted: nothing outside the devkit executes a goal.
"""

from __future__ import annotations

import os
import resource
from pathlib import Path

from panestria.api.app import Activity, AppProfile, Ask, Feature, Middleware, ScopedBrowser, State, build_app
from panestria.api.auth import GoalApi
from panestria.api.local_protocol import AnsweringHttpProtocol
from panestria.api.local_server import AskRuntime, owned_listener, run_owned
from panestria.api.mission_web import BuildIntake, BuildReview, BuildRun, MissionAssets, load_mission_assets
from panestria.api.serving import TransportLimits
from panestria.api.sessions import SESSION_SCOPES, BrowserScopes, SessionScope
from panestria.assets import AssetUnavailable, mission_control
from panestria.config import Settings, ValidatedSettings
from panestria.config_local import LocalApplicationRejected, LocalApplicationSettings, load_local_settings


def owner_profile(
    config: LocalApplicationSettings,
    settings: ValidatedSettings,
    token: str,
    assets: Path,
    *,
    build_run: Path | None = None,
) -> AppProfile:
    """Ask with its owned model, Mission Control and, given a Build configuration, Build."""
    runtime = AskRuntime.create(config)
    actor = runtime.actor
    database_url = settings.database_url.get_secret_value()
    api = GoalApi(token, actor.owner_id, actor.project_id, database_url)
    features: list[Feature] = [Activity(scope=SESSION_SCOPES), Ask(runtime.ask, scope=("ask",))]
    if build_run is not None:
        from panestria.execution.mission_run import MissionRunService

        run = MissionRunService(build_run, actor, database_url)
        features += [
            BuildReview(run.settings.root, scope=("build",)),
            BuildIntake(allow_acceptance=True, scope=("build",)),
            BuildRun(run, scope=("build",)),
        ]
    scopes = mounted_scopes(build_run)
    features += [
        # Capabilities report what is mounted; the dashboard reads these.
        State("mission_offline_ask", True),
        State("mission_storage_mode", False),
        State("private_phone_enabled", False),
        State("owner_session_scopes", scopes),
        ScopedBrowser(BrowserScopes(config.origin, token, database_url)),
        MissionAssets(load_mission_assets(assets, session_scopes=scopes)),
        # The request bounds every product server shares; outermost, so it sees every request first.
        Middleware(TransportLimits),
        runtime.lifecycle(config, settings, api, scope=("ask",), accept_successor_policy=True),
    ]
    return AppProfile(settings, api, tuple(features))


def mounted_scopes(build_run: Path | None) -> tuple[SessionScope, ...]:
    """The session scopes that reach something: Build only with a Build configuration."""
    return tuple(scope for scope in SESSION_SCOPES if scope != "build" or build_run is not None)


def serve_owner(path: Path, *, build_run: Path | None = None, assets: Path | None = None) -> None:
    """Run the owner app in the foreground on the configured port; Ctrl+C stops it and its model."""
    config, token = load_local_settings(path)
    settings = Settings(
        database_url=os.environ.get("PANESTRIA_DATABASE_URL", ""),
        bind_host=config.bind_host,
        bind_port=config.bind_port,
    ).validate_profile()
    if assets is None:
        try:
            assets = mission_control()
        except AssetUnavailable:
            raise LocalApplicationRejected("mission_build_required") from None
    # No personal prompt, key or token can be included in a core dump.
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    listener = owned_listener(config)
    app = None
    try:
        app = build_app(owner_profile(config, settings, token.get_secret_value(), assets, build_run=build_run))
        announcement = {
            "schema_version": 1,
            "status": "STARTING",
            "origin": config.origin,
            "session_scopes": list(mounted_scopes(build_run)),
        }
        # One header-deadline behaviour for the whole app: a stalled header block gets 408.
        run_owned(app, listener, announcement, http=AnsweringHttpProtocol)
    finally:
        listener.close()
        if app is not None:
            app.state.health.shutdown()
