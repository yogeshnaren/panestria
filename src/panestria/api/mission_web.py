"""Explicit same-origin dashboard modes; reuse activity, auth and existing runtimes.

``MissionControl`` is the app feature for one explicitly selected dashboard
mode. It refuses any combination of modes, derives that mode's own session
cookie and key, and mounts the parts below in a fixed order. Each part is a
feature of its own (``api/app.py``), so an app profile can mount parts without
the one-mode rule.
"""

import asyncio
import hashlib
import hmac
import os
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi.responses import Response

from panestria.api.app import Browser
from panestria.api.sessions import BrowserAccess, BrowserNamespace
from panestria.config_activity import ActivitySettings
from panestria.config_local import LocalApplicationRejected
from panestria.kernel.sessions import SessionService

_ASSET_LIMITS = (("index.html", 16384), ("mission.js", 1048576), ("mission.css", 65536))
_ROOT_MARKER = b'<div id="root"></div>'


def load_mission_assets(directory: Path, *, phone_observer: bool = False) -> dict[str, bytes]:
    """Read a deliberate, local production build; never run a dev server or fetch assets."""
    try:
        if not directory.is_absolute() or directory.resolve() != directory or not directory.is_dir():
            raise LocalApplicationRejected("mission_build_required")
        assets = {}
        for name, maximum in _ASSET_LIMITS:
            path = directory / name
            if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
                raise LocalApplicationRejected("mission_build_required")
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, "rb") as stream:
                data = stream.read(maximum + 1)
            if not data or len(data) > maximum:
                raise LocalApplicationRejected("mission_build_required")
            assets[name] = data
        if phone_observer:
            if assets["index.html"].count(_ROOT_MARKER) != 1:
                raise LocalApplicationRejected("phone_observer_build_required")
            assets["index.html"] = assets["index.html"].replace(
                _ROOT_MARKER, b'<div id="root" data-phone-observer="true"></div>'
            )
    except OSError:
        raise LocalApplicationRejected("mission_build_required") from None
    return assets


@dataclass(frozen=True)
class MissionAssets:
    """The dashboard page, script and stylesheet, served from memory."""

    assets: Mapping[str, bytes]

    def mount(self, app: FastAPI) -> None:
        assets = self.assets
        app.state.mission_build_sha256 = hashlib.sha256(b"".join(assets.values())).hexdigest()

        @app.get("/", include_in_schema=False)
        def index() -> Response:
            return Response(assets["index.html"], media_type="text/html")

        @app.get("/ui/mission.js", include_in_schema=False)
        def script() -> Response:
            return Response(assets["mission.js"], media_type="text/javascript")

        @app.get("/ui/mission.css", include_in_schema=False)
        def style() -> Response:
            return Response(assets["mission.css"], media_type="text/css")


@dataclass(frozen=True)
class BuildReview:
    """PUBLIC diff and report review with consent recording; no merge dispatch."""

    root: Path

    def mount(self, app: FastAPI) -> None:
        from panestria.api.routes.mission_review import router
        from panestria.execution.build_review import BuildReviewService

        app.state.build_review = BuildReviewService(self.root)
        app.state.build_evidence_reader = app.state.build_review.evidence
        app.include_router(router)


@dataclass(frozen=True)
class BuildEvidence:
    """Read-only Build reports from an existing private evidence store."""

    store: Path

    def mount(self, app: FastAPI) -> None:
        from panestria.kernel.build import BuildEvidenceService, BuildEvidenceStore

        app.state.build_evidence_reader = BuildEvidenceService(BuildEvidenceStore(self.store, read_only=True))


@dataclass(frozen=True)
class ResearchIntake:
    """PUBLIC question staging; no execution."""

    service: Any  # ResearchIntakeService

    def mount(self, app: FastAPI) -> None:
        from panestria.api.routes.research_intake import router

        app.state.research_intake = self.service
        app.include_router(router)


@dataclass(frozen=True)
class BuildIntake:
    """PUBLIC zero-cash plan staging; with acceptance, also plan review and acceptance."""

    allow_acceptance: bool = False

    def mount(self, app: FastAPI) -> None:
        from panestria.api.routes.build_intake import router
        from panestria.execution.build_intake import BuildIntakeService

        app.state.build_intake = BuildIntakeService(allow_acceptance=self.allow_acceptance)
        app.include_router(router)


@dataclass(frozen=True)
class BuildRun:
    """Explicit finite foreground Build runs; the service is closed with the app."""

    service: Any  # MissionRunService

    def mount(self, app: FastAPI) -> None:
        from panestria.api.routes.mission_run import router

        service = self.service
        app.state.mission_run = service
        app.include_router(router)

        @asynccontextmanager
        async def run_lifecycle(_: FastAPI) -> AsyncIterator[None]:
            try:
                yield
            finally:
                await asyncio.to_thread(service.close)

        app.include_router(APIRouter(lifespan=run_lifecycle))


@dataclass(frozen=True)
class MissionControl:
    """One explicitly selected dashboard mode, with its own session scope."""

    config: ActivitySettings
    token: str = field(repr=False)
    directory: Path
    build_evidence_store: Path | None = None
    build_review_root: Path | None = None
    offline_ask: bool = False
    research_intake: Path | None = None
    build_intake: bool = False
    build_plan_review: bool = False
    build_run: Path | None = None
    storage_mode: bool = False
    phone_access: BrowserAccess | None = None

    def mount(self, app: FastAPI) -> None:
        config, phone_access, storage_mode, offline_ask = (
            self.config,
            self.phone_access,
            self.storage_mode,
            self.offline_ask,
        )
        build_evidence_store, build_review_root, research_intake = (
            self.build_evidence_store,
            self.build_review_root,
            self.research_intake,
        )
        build_intake, build_plan_review, build_run = self.build_intake, self.build_plan_review, self.build_run
        if phone_access is not None and (
            not phone_access.private_read_only
            or any(
                (
                    storage_mode,
                    offline_ask,
                    research_intake,
                    build_review_root,
                    build_intake,
                    build_plan_review,
                    build_run,
                )
            )
        ):
            raise LocalApplicationRejected("phone_observer_only")
        if storage_mode:
            from panestria.resources.storage_status import StorageObserver

            if not isinstance(getattr(app.state, "storage_observer", None), StorageObserver) or any(
                (
                    offline_ask,
                    research_intake,
                    build_evidence_store,
                    build_review_root,
                    build_intake,
                    build_plan_review,
                    build_run,
                )
            ):
                raise LocalApplicationRejected("mission_storage_select_one_mode")
        run_service = None
        if build_run is not None:
            from panestria.execution.mission_run import MissionRunService
            from panestria.kernel.goals import Actor

            if (
                offline_ask
                or research_intake is not None
                or build_review_root is not None
                or build_evidence_store is not None
                or build_intake
                or build_plan_review
            ):
                raise LocalApplicationRejected("mission_build_select_one_mode")
            run_service = MissionRunService(
                build_run, Actor(str(config.owner_id), str(config.project_id)), app.state.goal_api.database_url
            )
            build_plan_review = True
        build_intake = build_intake or build_plan_review
        if build_intake and (
            offline_ask
            or research_intake is not None
            or build_review_root is not None
            or build_evidence_store is not None
        ):
            raise LocalApplicationRejected("mission_build_select_one_mode")
        if research_intake is not None and (
            offline_ask or build_review_root is not None or build_evidence_store is not None
        ):
            raise LocalApplicationRejected("mission_research_select_one_mode")
        if offline_ask:
            from panestria.api.routes.ask import AskApi

            if (
                build_review_root is not None
                or build_evidence_store is not None
                or not isinstance(getattr(app.state, "ask_api", None), AskApi)
                or getattr(app.state, "profile_api", None) is not None
            ):
                raise LocalApplicationRejected("mission_ask_scope_unavailable")
        assets = load_mission_assets(self.directory, phone_observer=phone_access is not None)
        if run_service is not None:
            build_review_root = run_service.settings.root
        if build_review_root is not None:
            if build_evidence_store is not None:
                raise LocalApplicationRejected("mission_review_select_one_store")
            BuildReview(build_review_root).mount(app)
        elif build_evidence_store is not None:
            BuildEvidence(build_evidence_store).mount(app)
        research = None
        if research_intake is not None:
            from panestria.execution.research_intake import ResearchIntakeService
            from panestria.kernel.goals import Actor

            research = ResearchIntakeService(research_intake, Actor(str(config.owner_id), str(config.project_id)))
            ResearchIntake(research).mount(app)
        app.state.mission_offline_ask = offline_ask
        if build_intake:
            BuildIntake(allow_acceptance=build_plan_review).mount(app)
        if run_service is not None:
            BuildRun(run_service).mount(app)
        app.state.mission_storage_mode = storage_mode
        if phone_access is None:
            # Each mode has its own cookie and key purpose; a session from one
            # mode cannot gain another mode's access by reopening the URL.
            namespace, purpose = _session_scope(
                app,
                storage_mode=storage_mode,
                run_configuration=None if run_service is None else run_service.configuration,
                build_plan_review=build_plan_review,
                build_intake=build_intake,
                research_template=None if research is None else research.view.template_sha256,
                offline_ask=offline_ask,
                build_review=build_review_root is not None,
            )
            secret = hmac.digest(self.token.encode(), purpose + config.origin.encode(), "sha256")
            access = BrowserAccess(
                config.origin,
                SessionService(secret),
                app.state.goal_api.database_url,
                namespace=namespace,
            )
        else:
            access = phone_access
        Browser(access).mount(app)
        app.state.private_phone_enabled = phone_access is not None
        MissionAssets(assets).mount(app)


def _session_scope(
    app: FastAPI,
    *,
    storage_mode: bool,
    run_configuration: str | None,
    build_plan_review: bool,
    build_intake: bool,
    research_template: str | None,
    offline_ask: bool,
    build_review: bool,
) -> tuple[BrowserNamespace, bytes]:
    """The selected mode's cookie namespace and session key purpose, most specific first."""
    if storage_mode:
        observed = hashlib.sha256(str(app.state.storage_observer.path).encode()).digest()
        return "mission-storage", b"panestria.mission-storage-session.v1\0" + observed
    if run_configuration is not None:
        return "mission-build-run", b"panestria.mission-build-run-session.v1\0" + run_configuration.encode() + b"\0"
    if build_plan_review:
        return "mission-plan-review", b"panestria.mission-plan-review-session.v1\0"
    if build_intake:
        return "mission-build-intake", b"panestria.mission-build-intake-session.v1\0"
    if research_template is not None:
        return "mission-research", b"panestria.mission-research-session.v1\0" + research_template.encode() + b"\0"
    if offline_ask:
        return "mission-ask", b"panestria.mission-ask-session.v1\0"
    if build_review:
        return "mission-review", b"panestria.mission-review-session.v1\0"
    return "mission", b"panestria.mission-session.v1\0"


def mount_mission_control(
    app: FastAPI,
    config: ActivitySettings,
    token: str,
    directory: Path,
    *,
    build_evidence_store: Path | None = None,
    build_review_root: Path | None = None,
    offline_ask: bool = False,
    research_intake: Path | None = None,
    build_intake: bool = False,
    build_plan_review: bool = False,
    build_run: Path | None = None,
    storage_mode: bool = False,
    phone_access: BrowserAccess | None = None,
) -> None:
    MissionControl(
        config,
        token,
        directory,
        build_evidence_store=build_evidence_store,
        build_review_root=build_review_root,
        offline_ask=offline_ask,
        research_intake=research_intake,
        build_intake=build_intake,
        build_plan_review=build_plan_review,
        build_run=build_run,
        storage_mode=storage_mode,
        phone_access=phone_access,
    ).mount(app)
