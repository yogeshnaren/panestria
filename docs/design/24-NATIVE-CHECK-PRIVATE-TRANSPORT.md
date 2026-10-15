# Private registered-check transport

Prerequisite: #73's internal MCP session. Provide one attempt-owned private Unix
endpoint and a minimal stdio shim for a future pinned native MCP configuration.
This is not an external-agent API, HTTP listener, installed plugin or enabled
native tool profile. The session's trusted executor still needs the later durable
gateway/policy/registry/report binding and actual native conformance.

Create only a new canonical private 0700 directory and 0600 socket. Refuse existing
paths; verify owner UID and Linux SO_PEERCRED. The shim must match the controller's
expected socket device/inode and server PID, as well as private path/UID/mode.
Do not pass credentials, database URLs, authentication handles or the store's
descriptors to the shim. It forwards protocol data, never executes tool arguments.

Use newline-delimited messages with at most 32 KiB per frame, bounded queues and
two request workers. Keep cancellation notifications responsive while a callback
runs. One connection and a bounded lifetime/partial-frame deadline limit resource
use. EOF/pressure/expiry requests session cancellation and closes only owned
sockets. Bounded shutdown must report unconfirmed workers, not claim they stopped.
Never remove a replacement path or pre-existing user data during cleanup.

The shim uses bounded nonblocking input/socket/output buffers and a total deadline;
it emits only complete protocol frames to stdout and fixed errors to stderr.
Ordinary stdin EOF ends the private request stream and cancels active work. This
is a cancellation request; only the execution supervisor can prove process reaping.
Test actual sockets and child processes, slow/incomplete/oversized input, no-read
output pressure, peer mismatch, cancellation during work, endpoint replacement,
EOF and cooperative versus uncooperative shutdown. Callback fixtures are not
native auth, current policy or a live capability certificate.

MCP framing: [2025-06-18 transports](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports).
No provider call, account/credential setup or new SDK dependency is needed.
