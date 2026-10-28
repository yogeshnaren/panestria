"""Real PG/CLI/TLS/cookies with a synthetic CA; no actual phone/network qualification."""

import ipaddress
import json
import os
import select
import signal
import ssl
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx2 as httpx
import psycopg
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from test_aos_002_migration import _schema_fingerprint
from test_mission_control_browser import ASSETS, configure
from typer.testing import CliRunner

from panestria.cli.main import app
from panestria.config_local import LocalApplicationRejected
from panestria.config_phone import PhoneSettings, load_phone_settings
from panestria.kernel.goals import Actor
from panestria.kernel.sessions import SessionService
from panestria.kernel.uow import UnitOfWork

ROOT = Path(__file__).resolve().parents[2]


def configuration(f, tmp_path):
    path, activity, token = configure(f, tmp_path)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "synthetic-phone-test")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(minutes=1))
        .not_valid_after(datetime.now(UTC) + timedelta(hours=1))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(key, hashes.SHA256())
    )
    certificate, keyfile = path.parent / "fixture.crt", path.parent / "fixture.key"
    certificate.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    keyfile.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    certificate.chmod(0o600)
    keyfile.chmod(0o600)
    document = activity.model_dump(mode="json") | dict(
        enabled=True,
        bind_address="127.0.0.1",
        allowed_clients=["127.0.0.1"],
        certificate_file=str(certificate),
        key_file=str(keyfile),
    )
    phone = path.parent / "phone.json"
    phone.write_text(json.dumps(document))
    phone.chmod(0o600)
    return phone, load_phone_settings(phone)[0], token


def cli(path, *args):
    result = CliRunner().invoke(app, ["phone", *args, "--config", str(path)])
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def test_production_cli_tls_pairing_read_only_roles_revoke_and_desktop_scope(
    r1_migration_task, tmp_path, monkeypatch, record_property
):
    f = r1_migration_task
    path, config, token = configuration(f, tmp_path)
    monkeypatch.setenv("PANESTRIA_DATABASE_URL", f["dsn"])
    actor = Actor(f["owner"], f["project"])
    desktop = SessionService(b"synthetic-desktop-scope-key-32-bytes")
    with psycopg.connect(f["dsn"]) as c:
        oldcode = desktop.issue_pairing_code(UnitOfWork(c), actor)
        before = c.execute("SELECT count(*) FROM panestria.task_event").fetchone()
    code = cli(path, "pair-code")["code"]
    assert len(code) == 32
    # Different challenges cannot invalidate or consume one another's scope.
    with psycopg.connect(f["dsn"]) as c:
        desktop_tokens = desktop.pair(UnitOfWork(c), actor, oldcode)
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "from panestria.cli.main import app; app()",
            "phone",
            "serve",
            "--config",
            str(path),
            "--assets",
            str(ASSETS),
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    context = ssl.create_default_context(cafile=str(config.certificate_file))
    record_property(
        "scope", "Actual subprocess CLI/PG/TLS1.2+/cookies; temporary synthetic CA, loopback only, no target phone"
    )
    try:
        assert select.select([process.stdout], [], [], 20)[0], "phone CLI did not start"
        started = process.stdout.readline()
        assert json.loads(started)["authority"] == "READ_ONLY_METADATA", started
        with httpx.Client(base_url=config.origin, verify=context, trust_env=False, timeout=5) as client:
            # Startup log precedes uvicorn accepting connections; bounded readiness.
            import time

            deadline = time.monotonic() + 5
            while True:
                try:
                    response = client.get("/")
                    break
                except httpx.ConnectError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.05)
            assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
            assert client.get("/v1/activity", headers={"Authorization": "Bearer " + token}).status_code == 401
            assert client.post("/v1/session/code", json={}).status_code == 403
            pair = client.post("/v1/session/pair", json={"code": code}, headers={"Origin": config.origin})
            assert pair.status_code == 200, pair.text
            assert "Secure" in pair.headers["set-cookie"] and "HttpOnly" in pair.headers["set-cookie"]
            session = pair.json()
            identity = session["session_id"]
            result = client.get("/v1/activity")
            assert result.status_code == 200 and result.json()["project_id"] == f["project"]
            assert result.json()["view_authority"] == "READ_ONLY_METADATA"
            capabilities = client.get("/v1/mission/capabilities").json()
            assert capabilities.pop("private_phone_enabled") is True
            assert all(v is False or v == "NONE" for v in capabilities.values())
            for target in ("/v1/goals", "/v1/session/code", "/v1/mission/build/plans", "/v1/profiles", "/v1/approvals"):
                assert (
                    client.post(
                        target, json={}, headers={"Origin": config.origin, "X-Panestria-CSRF": session["csrf_token"]}
                    ).status_code
                    == 403
                )
            for headers in (
                {"Host": "evil.invalid"},
                {"Origin": "https://evil.invalid"},
                {"X-Forwarded-For": "127.0.0.1"},
            ):
                assert client.get("/v1/activity", headers=headers).status_code == 403
            assert client.get("/v1/artifacts/" + identity).status_code == 403
            replay = client.post("/v1/session/pair", json={"code": code}, headers={"Origin": config.origin})
            assert replay.status_code == 401
            listed = cli(path, "devices")["devices"]
            assert [row["session_id"] for row in listed] == [identity]
            no_confirm = CliRunner().invoke(app, ["phone", "revoke", identity, "--config", str(path)])
            assert no_confirm.exit_code == 2 and client.get("/v1/activity").status_code == 200
            # Local owner administration can retire this project's inactive
            # profile too; the running listener keeps its original fixed scope.
            updated = json.loads(path.read_text())
            updated["allowed_clients"].append("127.0.0.2")
            path.write_text(json.dumps(updated))
            assert cli(path, "devices")["devices"][0]["current_profile"] is False
            assert cli(path, "revoke", identity, "--confirm-revocation")["state"] == "REVOKED"
            assert client.get("/v1/activity").status_code == 401
            assert cli(path, "devices")["devices"][0]["revoked_at"] is not None
        with pytest.raises(httpx.HTTPError):
            httpx.get(config.origin.replace("https:", "http:") + "/v1/activity", trust_env=False, timeout=2)
        with psycopg.connect(f["dsn"]) as c:
            assert desktop.authenticate(UnitOfWork(c), actor, desktop_tokens.token) == desktop_tokens.session_id
            assert c.execute("SELECT count(*) FROM panestria.task_event").fetchone() == before
            with pytest.raises(psycopg.Error), c.transaction():
                c.execute("UPDATE panestria.phone_device SET role='ADMIN'")
        refused = subprocess.run(
            [
                "uv",
                "run",
                "--frozen",
                "alembic",
                "-c",
                "migrations/alembic.ini",
                "downgrade",
                "0039_curated_example_rights",
            ],
            cwd=ROOT,
            env={**os.environ, "PANESTRIA_DATABASE_URL": f["dsn"]},
            capture_output=True,
            text=True,
        )
        assert refused.returncode != 0 and "phone audit prevents downgrade" in refused.stderr
    finally:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=3)
        assert token not in (process.stdout.read() + process.stderr.read())


def test_explicit_configuration_and_private_client_boundary(r1_migration_task, tmp_path):
    from fastapi.testclient import TestClient

    from panestria.api.phone import build_phone_app
    from panestria.config import Settings

    path, config, token = configuration(r1_migration_task, tmp_path)
    doc = json.loads(path.read_text())
    doc["enabled"] = False
    path.write_text(json.dumps(doc))
    with pytest.raises(LocalApplicationRejected, match="phone_disabled"):
        load_phone_settings(path)
    for address in ("0.0.0.0", "8.8.8.8", "localhost", "169.254.1.2"):
        with pytest.raises(ValueError):
            PhoneSettings.model_validate_json(json.dumps(doc | {"bind_address": address}))
    app_ = build_phone_app(config, Settings(database_url=r1_migration_task["dsn"]).validate_profile(), token, ASSETS)
    try:
        with TestClient(app_, base_url=config.origin, client=("127.0.0.2", 1000)) as foreign:
            assert foreign.get("/").status_code == 403
        with TestClient(
            app_, base_url=config.origin.replace("https:", "http:"), client=("127.0.0.1", 1000)
        ) as plaintext:
            assert plaintext.get("/").status_code == 403
    finally:
        app_.state.health.shutdown()
    # HTTPS's default port is omitted by browser Origin serialization.
    standard = config.model_copy(update={"bind_port": 443})
    assert standard.origin == "https://127.0.0.1"
    standard_app = build_phone_app(
        standard, Settings(database_url=r1_migration_task["dsn"]).validate_profile(), token, ASSETS
    )
    try:
        with TestClient(standard_app, base_url=standard.origin, client=("127.0.0.1", 1000)) as browser:
            assert browser.get("/").status_code == 200
    finally:
        standard_app.state.health.shutdown()


def test_empty_phone_schema_roundtrip_and_original_observation(r1_migration_task):
    f = r1_migration_task
    env = {**os.environ, "PANESTRIA_DATABASE_URL": f["dsn"]}
    with psycopg.connect(f["dsn"]) as c:
        before = _schema_fingerprint(c)
    for action in (["downgrade", "0039_curated_example_rights"], ["upgrade", "head"]):
        result = subprocess.run(
            ["uv", "run", "--frozen", "alembic", "-c", "migrations/alembic.ini", *action],
            env=env,
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
    with psycopg.connect(f["dsn"]) as c:
        after = _schema_fingerprint(c)
    assert after == before
    selected = os.environ.get("PANESTRIA_PHONE_SCHEMA_OBSERVATION")
    if selected:
        Path(selected).write_text(after)


def test_role_expiry_configuration_change_and_certificate_pin(r1_migration_task, tmp_path):
    from fastapi.testclient import TestClient

    from panestria.api.phone import build_phone_app, phone_service, tls_server_config
    from panestria.config import Settings
    from panestria.kernel.errors import KernelDenied

    f = r1_migration_task
    _, config, token = configuration(f, tmp_path)
    actor = Actor(f["owner"], f["project"])
    service = phone_service(config, token)
    settings = Settings(database_url=f["dsn"]).validate_profile()
    observer = build_phone_app(config, settings, token, ASSETS)
    changed = build_phone_app(
        config.model_copy(update={"allowed_clients": ("127.0.0.1", "127.0.0.2")}), settings, token, ASSETS
    )
    try:
        with psycopg.connect(f["dsn"]) as c:
            code = service.issue_pairing_code(UnitOfWork(c), actor)
            paired = service.pair(UnitOfWork(c), actor, code)
            # Same HMAC key but absent phone role: base sessions cannot grant data access.
            bare = SessionService(service._secret, pairing_bytes=16, challenge_scope=service.challenge_scope)
            othercode = bare.issue_pairing_code(UnitOfWork(c), actor)
            unscoped = bare.pair(UnitOfWork(c), actor, othercode)
        with TestClient(observer, base_url=config.origin, client=("127.0.0.1", 1000)) as client:
            name = observer.state.browser_access.cookie_name
            client.cookies.set(name, unscoped.token)
            assert client.get("/v1/activity").status_code == 401
            client.cookies.set(name, paired.token)
            assert client.get("/v1/activity").status_code == 200
            with TestClient(changed, base_url=config.origin, client=("127.0.0.1", 1000)) as other:
                other.cookies.set(name, paired.token)
                assert other.get("/v1/activity").status_code == 401
            with psycopg.connect(f["dsn"]) as c:
                c.execute(
                    "UPDATE panestria.browser_session SET expires_at=clock_timestamp()-interval '1 second' WHERE id=%s",
                    (paired.session_id,),
                )
            assert client.get("/v1/activity").status_code == 401
        with psycopg.connect(f["dsn"]) as c:
            with pytest.raises(KernelDenied, match="not_found"):
                service.revoke_device(
                    UnitOfWork(c), Actor(f["owner"], "00000000-0000-4000-8000-000000000099"), paired.session_id
                )
        original = config.certificate_file.read_bytes()
        try:
            config.certificate_file.write_bytes(b"synthetic replaced certificate")
            with pytest.raises(LocalApplicationRejected, match="phone_certificate_changed"):
                tls_server_config(observer, config)
        finally:
            config.certificate_file.write_bytes(original)
    finally:
        observer.state.health.shutdown()
        changed.state.health.shutdown()


def test_sec_l1_phone_cap_counts_live_devices_and_lists_newest_first(r1_migration_task, tmp_path):
    from panestria.api.phone import phone_service
    from panestria.kernel.errors import KernelDenied

    f = r1_migration_task
    _, config, token = configuration(f, tmp_path)
    actor = Actor(f["owner"], f["project"])
    service = phone_service(config, token)

    def seed(c, revoked):
        c.execute(
            "WITH s AS (INSERT INTO panestria.browser_session"
            "(id,token_hash,csrf_hash,owner_id,project_id,created_at,expires_at,revoked_at) "
            "SELECT gen_random_uuid(),md5(g::text||%(k)s)||md5(g::text||'t'||%(k)s),"
            "md5(g::text||'c'||%(k)s)||md5(%(k)s||g::text),"
            "%(o)s,%(p)s,clock_timestamp()-interval '1 day',clock_timestamp()+interval '1 hour',"
            "CASE WHEN %(r)s THEN clock_timestamp() END FROM generate_series(1,256) g RETURNING id) "
            "INSERT INTO panestria.phone_device(session_id,owner_id,project_id,scope_ref) "
            "SELECT id,%(o)s,%(p)s,%(scope)s FROM s",
            {
                "k": str(revoked),
                "o": actor.owner_id,
                "p": actor.project_id,
                "r": revoked,
                "scope": service.challenge_scope,
            },
        )

    with psycopg.connect(f["dsn"]) as c:
        seed(c, True)
        paired = service.pair(UnitOfWork(c), actor, service.issue_pairing_code(UnitOfWork(c), actor))
        listed = service.devices(UnitOfWork(c), actor)
        assert len(listed) == 256 and listed[0]["session_id"] == paired.session_id
        assert listed[0]["state"] == "ACTIVE" and {item["state"] for item in listed[1:]} == {"REVOKED"}
    with psycopg.connect(f["dsn"]) as c:
        seed(c, False)
        with pytest.raises(KernelDenied, match="phone_device_history_limit"):
            service.pair(UnitOfWork(c), actor, service.issue_pairing_code(UnitOfWork(c), actor))
