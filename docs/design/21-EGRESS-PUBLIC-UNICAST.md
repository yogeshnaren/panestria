# Require native public unicast at the existing provider gateway

Review of the existing R1 gateway found that Python 3.12 reports `is_global=True`
for IPv4/IPv6 multicast addresses. A global flag alone is insufficient for the
existing policy's multicast/reserved denial. The installed runtime also accepts
an IPv6 zone suffix on an otherwise public address. Actual read-only observations
used 224.0.0.1, ff0e::1 and a zoned public IPv6 literal; no connection was made.

Require global **unicast**, rejecting multicast, reserved, unspecified, loopback,
link-local, scoped and mapped/transition addresses before connecting. Reject the
whole DNS answer set if any answer is unsafe. Recheck the connected peer with the
same predicate and require equality with the pinned destination/port. Retain the
existing three-host provider allowlist and Unix-socket/no-direct-egress boundary.
This is an R1 gateway correction, not public-web fetching or complete OS/live
qualification. No inference, provider permission, fallback or credentials change.

Primary semantics: [Python 3.12 ipaddress](https://docs.python.org/3.12/library/ipaddress.html),
with the installed stdlib address predicates inspected directly under the existing
REA direct-source workflow. Reuse standard address properties, not copied vendor
code. Deterministic tests inject DNS/transport and must not contact the internet;
run the existing actual sandbox/gateway checks independently of hermetic fixtures.
