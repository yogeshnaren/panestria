"""A real cookie jar must authenticate both API versions with the same scope."""

from __future__ import annotations

from pathlib import Path

from test_aos_009 import _client
from test_ask_kernel import initialize
from test_local_provider import transport, valid_frames

from panestria.api.main import mount_ask_api
from panestria.api.routes.ask import AskApi
from panestria.api.sessions import COOKIE_NAME
from panestria.inference.local import LocalProvider
from panestria.resources.hardware import HardwareProbe

CLI = {"Authorization": "Bearer test-only-cli-token-at-least-16"}
ORIGIN = {"Origin": "http://127.0.0.1:8766"}
ARCHIVE = Path(__file__).resolve().parents[2] / "docs/specification/attachments/agentos-skills-v0.1.0.zip"


def test_cookie_scope_and_logout_span_api_versions(r1_task, tmp_path):
    initialize(r1_task, tmp_path)
    client = _client(r1_task)
    mocked, calls = transport(valid_frames())
    mount_ask_api(
        client.app,
        AskApi(
            LocalProvider(Path("/synthetic"), transport=mocked),
            lambda: HardwareProbe(ARCHIVE).collect(preset="omen-8gb"),
        ),
    )
    code = client.post("/v1/session/code", json={}, headers=CLI).json()["code"]
    # An already paired old browser can retain its /v1 cookie until re-pairing.
    client.cookies.set(COOKIE_NAME, "legacy-synthetic-cookie", domain="127.0.0.1", path="/v1")
    paired = client.post("/v1/session/pair", json={"code": code}, headers=ORIGIN)
    assert paired.status_code == 200
    cookies = [cookie for cookie in client.cookies.jar if cookie.name == COOKIE_NAME]
    assert len(cookies) == 1 and cookies[0].path == "/"
    assert client.cookies.get(COOKIE_NAME) == cookies[0].value
    raw = paired.headers.get_list("set-cookie")
    assert any("Path=/;" in value and "HttpOnly" in value and "SameSite=strict" in value for value in raw)
    assert any("Path=/v1;" in value and "Max-Age=0" in value for value in raw)
    headers = {**ORIGIN, "X-Panestria-CSRF": paired.json()["csrf_token"]}
    document = {"schema_version": 2, "body": "Synthetic browser-v2 preference", "label": "INTERNAL"}
    assert client.post("/v2/memory", json=document, headers=ORIGIN).status_code == 403
    assert (
        client.post("/v2/memory", json=document, headers={**headers, "Origin": "https://evil.example"}).status_code
        == 403
    )
    added = client.post("/v2/memory", json=document, headers=headers)
    assert added.status_code == 201
    identity = added.json()["item_id"]
    assert client.get(f"/v1/memory/{identity}", headers=ORIGIN).status_code == 200
    assert client.get(f"/v2/memory/{identity}", headers=ORIGIN).status_code == 200
    assert client.get(f"/v2/memory/{identity}", headers={"Host": "rebind.attacker.example"}).status_code == 403
    assert client.post("/v1/session/logout", json={}, headers=headers).status_code == 200
    assert not [cookie for cookie in client.cookies.jar if cookie.name == COOKIE_NAME]
    for version in (1, 2):
        assert client.get(f"/v{version}/memory/{identity}").status_code == 401
    assert calls == []
