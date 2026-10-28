"""Property tests for digests, cursors, DAG validation, input framing and egress addresses."""

import hashlib
import io
import ipaddress
import json

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from panestria.contracts.approval import ActionPreview, effect_digest
from panestria.contracts.build import canonical_sha256
from panestria.kernel.errors import KernelDenied
from panestria.kernel.event_replay import MAX_CURSOR, parse_cursor
from panestria.kernel.tasks import DagRejected, validate_dag
from panestria.sandbox.egress import _public_unicast
from panestria.sandbox.native_tool_input import (
    MAX_REQUEST_BYTES,
    MAX_SCRIPT_BYTES,
    InputFrameRejected,
    decode_frame,
    encode_frame,
)

JSON = st.recursive(
    st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False, allow_infinity=False) | st.text(),
    lambda inner: st.lists(inner, max_size=4) | st.dictionaries(st.text(max_size=8), inner, max_size=4),
    max_leaves=12,
)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


@given(JSON, JSON)
def test_canonical_digest_is_equal_exactly_when_the_canonical_encoding_is(a, b):
    assert (canonical_sha256(a) == canonical_sha256(b)) == (_canonical(a) == _canonical(b))


@given(st.dictionaries(st.text(max_size=8), JSON, min_size=1, max_size=6), st.randoms(use_true_random=False))
def test_canonical_digest_ignores_key_insertion_order(value, random):
    keys = list(value)
    random.shuffle(keys)
    assert canonical_sha256({key: value[key] for key in keys}) == canonical_sha256(value)


PREVIEW = {
    "action_kind": "merge",
    "owner_id": "00000000-0000-4000-8000-000000000002",
    "project_id": "00000000-0000-4000-8000-000000000003",
    "task_id": "00000000-0000-4000-8000-000000000004",
    "contract_sha256": "ab" * 32,
    "contract_version": 1,
    "policy_version": "project-policy:1",
    "destination": "refs/heads/main",
    "expected_base": "0123456789abcdef0123456789abcdef01234567",
    "candidate_sha256": "ef" * 32,
    "required_checks": ["unit"],
    "minimum_actor_id": "00000000-0000-4000-8000-000000000002",
    "expires_at": "2026-10-28T12:00:00+00:00",
}
VARIANTS = {
    "action_kind": "finalize",
    "task_id": "00000000-0000-4000-8000-000000000005",
    "contract_sha256": "ac" * 32,
    "contract_version": 2,
    "policy_version": "project-policy:2",
    "destination": "refs/heads/release",
    "expected_base": "1123456789abcdef0123456789abcdef01234567",
    "candidate_sha256": "ee" * 32,
    "required_checks": ["unit", "lint"],
    "minimum_actor_id": "00000000-0000-4000-8000-000000000006",
    "expires_at": "2026-10-28T12:00:01+00:00",
}


@pytest.mark.parametrize("field", sorted(VARIANTS))
def test_effect_digest_binds_every_previewed_field(field):
    base = effect_digest(ActionPreview.model_validate(PREVIEW))
    changed = effect_digest(ActionPreview.model_validate({**PREVIEW, field: VARIANTS[field]}))
    assert changed != base
    assert (
        effect_digest(ActionPreview.model_validate_json(ActionPreview.model_validate(PREVIEW).model_dump_json()))
        == base
    )


@given(st.integers(0, MAX_CURSOR))
def test_parse_cursor_round_trips_every_valid_cursor(value):
    assert parse_cursor(str(value)) == value


@given(
    st.one_of(
        st.integers(MAX_CURSOR + 1, 10**19 - 1).map(str),
        st.integers(0, MAX_CURSOR).map(lambda v: "0" + str(v)),
        st.text().filter(lambda s: not (s.isascii() and s.isdigit())),
        st.sampled_from(["", "-1", "+1", " 1", "1 ", "١٢", "１", "1e3", "0x10"]),
    )
)
def test_parse_cursor_rejects_everything_else(value):
    with pytest.raises(KernelDenied, match="invalid_cursor"):
        parse_cursor(value)


def _acyclic(nodes: list[str], edges: list[tuple[str, str]]) -> bool:
    # Reference: Kahn's algorithm over the same edge direction.
    incoming = {node: 0 for node in nodes}
    for _, target in edges:
        incoming[target] += 1
    ready = [node for node, count in incoming.items() if count == 0]
    seen = 0
    while ready:
        node = ready.pop()
        seen += 1
        for source, target in edges:
            if source == node:
                incoming[target] -= 1
                if incoming[target] == 0:
                    ready.append(target)
    return seen == len(nodes)


@given(
    st.integers(1, 7).flatmap(
        lambda n: st.tuples(
            st.just([f"n{i}" for i in range(n)]),
            st.lists(st.tuples(st.integers(0, n - 1), st.integers(0, n - 1)), max_size=12),
        )
    )
)
def test_validate_dag_matches_a_reference_cycle_check(graph):
    nodes, pairs = graph
    edges = [(nodes[a], nodes[b]) for a, b in pairs]
    if any(a == b for a, b in edges):
        with pytest.raises(DagRejected, match="self_link"):
            validate_dag(nodes, edges)
    elif _acyclic(nodes, edges):
        validate_dag(nodes, edges)
    else:
        with pytest.raises(DagRejected, match="cycle"):
            validate_dag(nodes, edges)


def test_validate_dag_rejects_duplicates_and_unknown_endpoints():
    with pytest.raises(DagRejected, match="duplicate_node"):
        validate_dag(["a", "a"], [])
    with pytest.raises(DagRejected, match="unknown_node"):
        validate_dag(["a"], [("a", "b")])


SCRIPTS = st.binary(min_size=1, max_size=2048)
REQUESTS = st.binary(min_size=1, max_size=512)


def _decode(frame: bytes, script: bytes, request: bytes):
    return decode_frame(
        io.BytesIO(frame),
        script_sha256=hashlib.sha256(script).hexdigest(),
        request_sha256=hashlib.sha256(request).hexdigest(),
    )


@given(SCRIPTS, REQUESTS)
def test_frame_round_trips(script, request):
    decoded = _decode(encode_frame(script, request), script, request)
    assert (decoded.script, decoded.request) == (script, request)


@given(SCRIPTS, REQUESTS, st.data())
def test_any_single_byte_change_truncation_or_trailer_is_rejected(script, request, data):
    frame = encode_frame(script, request)
    mutation = data.draw(st.sampled_from(["flip", "truncate", "trail"]))
    if mutation == "flip":
        index = data.draw(st.integers(0, len(frame) - 1))
        changed = frame[:index] + bytes([frame[index] ^ data.draw(st.integers(1, 255))]) + frame[index + 1 :]
    elif mutation == "truncate":
        changed = frame[: data.draw(st.integers(0, len(frame) - 1))]
    else:
        changed = frame + data.draw(st.binary(min_size=1, max_size=8))
    with pytest.raises(InputFrameRejected):
        _decode(changed, script, request)


def test_frame_size_bounds_are_enforced():
    for script, request in (
        (b"", b"r"),
        (b"s", b""),
        (b"s" * (MAX_SCRIPT_BYTES + 1), b"r"),
        (b"s", b"r" * (MAX_REQUEST_BYTES + 1)),
    ):
        with pytest.raises(InputFrameRejected):
            encode_frame(script, request)


# IANA special-purpose registries, entries that are not globally reachable.
# Globally reachable sub-allocations (192.0.0.9/32, 192.0.0.10/32, AS112, AMT,
# 2001:1::1/128, 2001:3::/32 and similar) are deliberately absent.
NOT_GLOBAL = [
    ipaddress.ip_network(value)
    for value in (
        "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12",
        "192.0.0.0/29", "192.0.0.170/31", "192.0.2.0/24", "192.168.0.0/16", "198.18.0.0/15", "198.51.100.0/24",
        "203.0.113.0/24", "224.0.0.0/4", "240.0.0.0/4", "255.255.255.255/32",
        "::/128", "::1/128", "::ffff:0:0/96", "64:ff9b::/96", "64:ff9b:1::/48", "100::/64", "2001::/32",
        "2001:2::/48", "2001:10::/28", "2001:db8::/32", "2002::/16", "3fff::/20", "5f00::/16", "fc00::/7",
        "fe80::/10", "fec0::/10", "ff00::/8",
    )
]  # fmt: skip
# Pending plan 1.5 (security lows): the deprecated 6to4 relay anycast prefix
# 192.88.99.0/24 (RFC 7526) is still accepted and is excluded until then.


@given(st.sampled_from(NOT_GLOBAL).flatmap(lambda net: st.integers(0, net.num_addresses - 1).map(lambda i: net[i])))
def test_public_unicast_rejects_every_non_global_special_purpose_address(address):
    assert _public_unicast(str(address)) is None


@given(
    st.integers(0, 2**32 - 1).map(ipaddress.IPv4Address)
    | st.integers(0x2000 << 112, (0x4000 << 112) - 1).map(ipaddress.IPv6Address)  # 2000::/3 global unicast
)
def test_public_unicast_only_returns_global_unicast_addresses(address):
    accepted = _public_unicast(str(address))
    assume(accepted is not None)
    assert accepted == address and accepted.is_global
    assert not (accepted.is_multicast or accepted.is_loopback or accepted.is_link_local or accepted.is_reserved)
