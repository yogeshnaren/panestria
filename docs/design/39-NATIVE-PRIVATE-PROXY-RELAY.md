# Private native proxy transport in a network-disabled container

Start from verified main `1648123` after PR88. The current native pilot has a trusted
vendor-auth process and confined registered tools, but CLI flags do not prove OS
containment of that auth process. The existing EgressGateway already admits exact
CONNECT hosts through a private Unix socket with public-DNS checks and IP pinning.

Add a standalone standard-library relay inside a future native container with
network=none: a trusted client connects to its own `127.0.0.1` HTTP proxy; the relay
forwards bytes only to the exact read-only mounted gateway socket; the trusted
host gateway owns public network access. There is no Docker bridge, published
port, host-network fallback, credential directory or model inference in this
transport task. The existing worker no-network runner remains separate.

Check socket device/inode/type/owner/private modes before and after connect and
verify Linux peer UID. Bind only IPv4 loopback. Bound lifetime, live/admitted
connections, aggregate bidirectional bytes and per-direction buffers. Use
nonblocking writes with backpressure and proper half-close/draining; stop/cancel
closes tracked channels. No request/header/payload logging. Native launchers
must pin the program/image/mounts and enforce the container envelope separately.

Default tests distinguish a synthetic private upstream from actual Docker network,
mount, identity/resource/secret-sentinel observations. A separately opted-in actual
public provider TLS HEAD may qualify the channel, with no login or inference.
This is not a native CLI, credential, arbitrary untrusted-client, task, grant or
release certificate. CONNECT admission is in the host gateway; end-to-end TLS and
application authorization remain with the trusted pinned client. Later native
integration must reject unexpected capabilities and credential/tool sharing,
apply current policy/grants/lease/budget and retain actual live evidence.

## Observed component validation

Clean source `c6fa589` passes 74 focused checks plus one explicitly opted-in actual
CA/hostname-verified TLS HEAD to Anthropic through the network-disabled container,
loopback relay, private Unix socket and host gateway. No auth, inference or paid
SDK request occurred. The program also refuses to start unless its Linux network
namespace has only loopback. Four actual Docker checks cover the effective mount,
network, resource and synthetic sentinel/environment boundary. Socket tests cover
large half-closed transfers, aggregate caps and endpoint replacement. Source and
JUnit hashes, development failures and limits are retained in
`evidence/native-private-relay-2026-10-16`. This observation does not change the
required native/task/grant conformance boundaries above.
