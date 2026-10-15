"""Actual public TLS observations; no authentication, provider inference or raw content export."""

import json

import pytest

from panestria.brokers.research.fetch import PublicHttpsFetcher
from panestria.contracts.research import ResearchLimits
from panestria.sandbox.egress import _public_unicast


@pytest.mark.live
@pytest.mark.parametrize("url", ["https://www.example.org/", "https://www.iana.org/domains/example"])
def test_actual_public_https_pins_tls_peer_and_retains_bounded_bytes(url, record_property):
    result = PublicHttpsFetcher().fetch(url, ResearchLimits(max_source_bytes=128 * 1024, deadline_seconds=20.0))
    observation = {
        "outcome": result.outcome,
        "reason": result.reason,
        "retained_sha256": result.retained_sha256,
        "retained_bytes": len(result.body),
        "hops": [
            {
                "url_sha256": hop.url_sha256,
                "address": hop.address,
                "status": hop.status,
                "certificate_sha256": hop.certificate_sha256,
            }
            for hop in result.hops
        ],
        "scope": "actual public HTTPS bytes only; no retained source/reader/citation authority",
    }
    record_property("public_fetch_observation", json.dumps(observation, sort_keys=True))
    assert result.outcome == "COMPLETE", observation
    assert 0 < len(result.body) <= 128 * 1024 and result.hops and 200 <= result.hops[-1].status < 300
    assert all(_public_unicast(hop.address) is not None and len(hop.certificate_sha256) == 64 for hop in result.hops)
