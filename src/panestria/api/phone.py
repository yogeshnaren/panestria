"""Explicit private TLS metadata observer; no remote bearer or task mutation surface."""

import hashlib
import hmac
import json
import os
import re
import resource
import socket
import ssl
import stat
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from panestria.api.activity_server import build_activity_app
from panestria.api.auth import error_body
from panestria.api.local_server import server_config
from panestria.api.mission_web import mount_mission_control
from panestria.api.security import _SECURITY_HEADERS, RequestLimits
from panestria.api.sessions import BrowserAccess
from panestria.config import Settings, ValidatedSettings
from panestria.config_local import LocalApplicationRejected, read_private
from panestria.config_phone import PhoneSettings, load_phone_settings, private_ip
from panestria.kernel.phone import PhoneSessionService


def phone_service(config: PhoneSettings, token: str) -> PhoneSessionService:
    return _phone_service(config, token, hashlib.sha256(read_private(config.certificate_file, 65536)).hexdigest())


def _phone_service(config: PhoneSettings, token: str, certificate_hash: str) -> PhoneSessionService:
    if not config.enabled:
        raise LocalApplicationRejected("phone_disabled")
    scope = hashlib.sha256(
        json.dumps(
            {
                "configuration": config.model_dump(mode="json", exclude_none=True),
                "certificate_sha256": certificate_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    secret = hmac.digest(token.encode(), b"panestria.phone.read-only.v1\0" + scope.encode(), "sha256")
    return PhoneSessionService(secret, scope)


class PhoneBrowserAccess(BrowserAccess):
    @staticmethod
    def _origin_host_allowed(host: str | None, scheme: str) -> bool:
        return scheme == "https" and host is not None and private_ip(host)

    @property
    def private_read_only(self) -> bool:
        return True


class PhoneBoundary:
    def __init__(self, app: ASGIApp, clients: tuple[str, ...]) -> None:
        self.app, self.clients, self.limits = app, clients, RequestLimits()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        peer = scope.get("client")
        headers = scope.get("headers", [])
        path, method = scope.get("path", ""), scope.get("method", "")
        allowed = (
            method == "GET"
            and (
                path
                in {
                    "/",
                    "/ui/mission.js",
                    "/ui/mission.css",
                    "/v1/activity",
                    "/v1/activity/reviews",
                    "/v1/mission/capabilities",
                }
                or re.fullmatch(r"/v1/activity/goals/[0-9a-f-]{36}/(events|build-progress)", path) is not None
            )
        ) or (method == "POST" and path in {"/v1/session/pair", "/v1/session/logout"})
        code = None
        if scope.get("scheme") != "https" or not peer or peer[0] not in self.clients:
            code = "phone_transport_denied"
        elif any(k.lower() == b"forwarded" or k.lower().startswith(b"x-forwarded-") for k, _ in headers):
            code = "phone_proxy_denied"
        elif not allowed:
            code = "phone_read_only"
        elif path == "/v1/session/pair" and not self.limits.admit("global-pairing", 10):
            code = "rate_limited"
        if code is not None:
            await JSONResponse(
                status_code=429 if code == "rate_limited" else 403, content=error_body(code), headers=_SECURITY_HEADERS
            )(scope, receive, send)
            return
        await self.app(scope, receive, send)


def build_phone_app(config: PhoneSettings, settings: ValidatedSettings, token: str, assets: Path) -> FastAPI:
    certificate_hash = hashlib.sha256(read_private(config.certificate_file, 65536)).hexdigest()
    service = _phone_service(config, token, certificate_hash)
    app = build_activity_app(config, settings, token)
    access = PhoneBrowserAccess(
        config.origin, service, settings.database_url.get_secret_value(), namespace="mission-phone"
    )
    access.session_seconds = 3600
    try:
        mount_mission_control(
            app, config, token, assets, phone_access=access, build_evidence_store=config.build_evidence_store
        )
        app.add_middleware(PhoneBoundary, clients=config.allowed_clients)
        app.state.phone_certificate_sha256 = certificate_hash
        return app
    except BaseException:
        app.state.health.shutdown()
        raise


def tls_server_config(app: FastAPI, config: PhoneSettings) -> uvicorn.Config:
    descriptors = []
    try:
        for path in (config.certificate_file, config.key_file):
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            descriptors.append(descriptor)
            info = os.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_mode & 0o077
                or not 0 < info.st_size <= 65536
            ):
                raise LocalApplicationRejected("phone_tls_file_invalid")
        result = server_config(app)
        pinned = os.read(descriptors[0], 65537)
        if hashlib.sha256(pinned).hexdigest() != app.state.phone_certificate_sha256:
            raise LocalApplicationRejected("phone_certificate_changed")
        os.lseek(descriptors[0], 0, os.SEEK_SET)
        result.ssl_certfile = f"/proc/self/fd/{descriptors[0]}"
        result.ssl_keyfile = f"/proc/self/fd/{descriptors[1]}"
        result.ssl_keyfile_password = ""  # Unsupported encrypted keys fail instead of prompting on stdin.
        result.ssl_version = ssl.PROTOCOL_TLS_SERVER
        result.load()
        if result.ssl is None:
            raise LocalApplicationRejected("phone_tls_required")
        result.ssl.minimum_version = ssl.TLSVersion.TLSv1_2
        return result
    except (OSError, ValueError):
        raise LocalApplicationRejected("phone_tls_unavailable") from None
    finally:
        for descriptor in descriptors:
            os.close(descriptor)


def serve_phone(path: Path, assets: Path) -> None:
    config, token = load_phone_settings(path)
    settings = Settings(database_url=os.environ.get("PANESTRIA_DATABASE_URL", "")).validate_profile()
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    app = build_phone_app(config, settings, token.get_secret_value(), assets)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        runtime = tls_server_config(app, config)
        try:
            # Permit a stopped listener's TIME_WAIT sockets to retire without
            # delaying restart. No SO_REUSEPORT or competing active listener.
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind((config.bind_address, config.bind_port))
            listener.listen(16)
        except OSError:
            raise LocalApplicationRejected("phone_bind_unavailable") from None
        listener.setblocking(False)
        server = uvicorn.Server(runtime)
        print(
            json.dumps({"status": "STARTING", "origin": config.origin, "authority": "READ_ONLY_METADATA"}), flush=True
        )
        server.run(sockets=[listener])
        if not server.started:
            raise LocalApplicationRejected("phone_startup_failed")
    finally:
        listener.close()
        app.state.health.shutdown()
