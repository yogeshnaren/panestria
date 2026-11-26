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
key is derived for that scope alone. A stolen Ask or activity session
therefore cannot read a Build diff, approve a Build or start a run. The loopback
bearer (CLI) is unchanged and may use every route.
"""

from __future__ import annotations

from pathlib import Path

from panestria.api.app import Activity, AppProfile, Ask, Feature, ScopedBrowser, State
from panestria.api.auth import GoalApi
from panestria.api.local_server import AskRuntime
from panestria.api.mission_web import BuildIntake, BuildReview, BuildRun, MissionAssets, load_mission_assets
from panestria.api.sessions import SESSION_SCOPES, BrowserScopes
from panestria.config import ValidatedSettings
from panestria.config_local import LocalApplicationSettings


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
    features += [
        # Capabilities report what is mounted; the dashboard reads these.
        State("mission_offline_ask", True),
        State("mission_storage_mode", False),
        State("private_phone_enabled", False),
        ScopedBrowser(BrowserScopes(config.origin, token, database_url)),
        MissionAssets(load_mission_assets(assets)),
        runtime.lifecycle(config, settings, api, scope=("ask",)),
    ]
    return AppProfile(settings, api, tuple(features))
