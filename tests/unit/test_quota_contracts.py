"""Closed quota transport and faithful reported/estimated/unknown semantics."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from quota_support import observation


@pytest.mark.parametrize("value", [True, 1, 1.2, "-1", "NaN", "inf", "1e2", "01", ".5", "0.0001", "101"])
def test_percentage_rejects_coercion_nonfinite_and_out_of_range(value):
    with pytest.raises(ValidationError):
        observation(remaining=value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", True),
        ("schema_version", 1.0),
        ("schema_version", "1"),
        ("fresh_for_seconds", True),
        ("fresh_for_seconds", 86401),
        ("observed_at", "2026-10-16T10:00:00"),
        ("source", "known"),
        ("approved", True),
        ("unit", "cash_microusd"),
        ("source_sha256", "ab" * 32),
        ("observation_id", "not-an-id"),
    ],
)
def test_invalid_versions_provenance_units_times_and_authority_fail_closed(field, value):
    with pytest.raises(ValidationError):
        observation(**{field: value})


@pytest.mark.parametrize("source", ["PROVIDER_REPORTED", "ESTIMATED"])
def test_supported_source_lane_requires_provenance_without_conferring_authority(source):
    with pytest.raises(ValidationError):
        observation(source=source)
    accepted = observation(source=source, source_sha256="ab" * 32)
    assert accepted.source == source and "authority" not in accepted.model_dump()
    unknown = observation(source=source, source_sha256="ab" * 32, remaining=None)
    assert unknown.remaining is None and unknown.source == source


def test_unknown_is_nullable_and_cannot_claim_zero_or_an_unlimited_value():
    for value in ("0", "40"):
        with pytest.raises(ValidationError):
            observation(source="UNKNOWN", remaining=value)
    assert observation(source="UNKNOWN", remaining=None, unit=None).remaining is None
    assert observation(source="OWNER_REPORTED", remaining=None).source == "OWNER_REPORTED"
    assert observation(remaining="0").remaining == "0"


def test_exact_decimal_normalization_and_units_do_not_convert_capacity():
    original = observation()
    equivalent = observation(**{**original.model_dump(mode="json"), "remaining": "40.000"})
    assert original.sha256() == equivalent.sha256() and equivalent.remaining == "40"
    assert observation(remaining="0.5").remaining == "0.5"
    with pytest.raises(ValidationError):
        observation(remaining="0.5", unit="requests")
    assert observation(remaining="500", unit="tokens").remaining == "500"


def test_scope_distinguishes_account_model_provider_window_and_explicit_timezone():
    original = observation()
    scope = original.scope.model_dump()
    hashes = {original.scope.sha256()}
    for changes in ({"model_ref": "haiku-4.5"}, {"window_ref": "weekly"}, {"provider": "anthropic-api"}):
        hashes.add(observation(scope={**scope, **changes}).scope.sha256())
    assert len(hashes) == 4
    explicit = observation(observed_at="2026-10-15T17:00:00-07:00", resets_at="2026-10-16T17:00:00-07:00")
    assert explicit.observed_at == datetime(2026, 10, 16, tzinfo=UTC)
    with pytest.raises(ValidationError):
        observation(resets_at=(original.observed_at - timedelta(seconds=1)).isoformat())
    with pytest.raises(ValidationError):
        observation(scope={**scope, "account_ref": "private@example.com"})


def test_a_server_clock_rollback_does_not_make_an_observation_new_again():
    from panestria.kernel.quota import _view

    body = observation()
    earlier = body.observed_at - timedelta(seconds=1)
    view = _view(body, body.observed_at, earlier)
    assert view.freshness == "STALE" and view.confidence == "UNKNOWN" and view.effective_remaining is None
