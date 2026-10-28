"""SEC-L1 request-time preview bounds and IDNA2008 host comparison."""

from datetime import UTC, datetime, timedelta

import pytest

from panestria.contracts.approval import MAX_REQUEST_TTL, PreviewRejected, load_preview, require_request_bounds
from panestria.contracts.hosts import ascii_host

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
UUID = "00000000-0000-4000-8000-000000000001"


def preview(**change: str):
    body = {
        "action_kind": "merge",
        "owner_id": UUID,
        "project_id": UUID,
        "task_id": UUID,
        "contract_sha256": "a" * 64,
        "contract_version": 1,
        "policy_version": "policy-v1",
        "destination": "refs/heads/main@" + "b" * 40,
        "expected_base": "c" * 40,
        "candidate_sha256": "d" * 64,
        "required_checks": ["unit"],
        "minimum_actor_id": UUID,
        "expires_at": (NOW + timedelta(minutes=10)).isoformat(),
        **change,
    }
    return load_preview(body)


def test_sec_l1_ordinary_request_is_accepted():
    require_request_bounds(preview(), NOW)
    require_request_bounds(preview(expires_at=(NOW + MAX_REQUEST_TTL).isoformat()), NOW)


@pytest.mark.parametrize(
    "destination",
    [
        "refs/heads/m\u0430in",  # Cyrillic a
        "refs/heads/main\nrefs/heads/other",
        "refs/heads/main ",
        "refs/heads/ main",
        "refs/heads/main\u200b",
        "refs/heads/main\t",
    ],
)
def test_sec_l1_destination_must_be_printable_ascii(destination):
    with pytest.raises(PreviewRejected) as denied:
        require_request_bounds(preview(destination=destination), NOW)
    assert denied.value.code == "invalid_preview_destination"


@pytest.mark.parametrize(
    "expires_at",
    [
        (NOW + MAX_REQUEST_TTL + timedelta(seconds=1)).isoformat(),
        "9999-12-31T23:59:59+00:00",
        "2026-02-30T00:00:00+00:00",
        "2026-10-28T25:00:00+00:00",
    ],
)
def test_sec_l1_expiry_must_be_a_real_bounded_instant(expires_at):
    with pytest.raises(PreviewRejected) as denied:
        require_request_bounds(preview(expires_at=expires_at), NOW)
    assert denied.value.code == "invalid_preview_expiry"


def test_sec_l1_stored_previews_still_load_without_request_bounds():
    # Read paths keep accepting what earlier releases stored.
    assert preview(expires_at="9999-12-31T23:59:59+00:00").expires_at.startswith("9999")


@pytest.mark.parametrize(
    "host,expected",
    [
        ("Example.ORG", "example.org"),
        ("127.0.0.1", "127.0.0.1"),
        ("fa\u00df.de", "xn--fa-hia.de"),
        ("B\u00fccher.example", "xn--bcher-kva.example"),
        ("\u0441\u0430\u0439\u0442.example", "xn--80aswg.example"),
    ],
)
def test_sec_l1_ascii_host_uses_uts46_nontransitional(host, expected):
    assert ascii_host(host) == expected


def test_sec_l1_sharp_s_is_not_folded_to_another_host():
    assert ascii_host("fa\u00df.de") != ascii_host("fass.de")


@pytest.mark.parametrize("host", ["\u2603\u2603..example", "a\u200db.example", "-\u00e9.example"])
def test_sec_l1_invalid_international_hosts_raise(host):
    with pytest.raises(UnicodeError):
        ascii_host(host)
