# Internal registered-check MCP session

Selected independent AOS-010 shell-tier component while protected research bytes
are in CI. The existing command gateway and durable controller authority remain
the execution boundary. This task adds a closed, bounded MCP session state machine;
it does not enable a native profile or install/start an MCP server.

Pin the wire dialect to MCP 2025-06-18 and JSON-RPC 2.0. Support initialization,
initialized notification, ping, tools/list, tools/call and cancellation. Advertise
only one `run_registered_check` tool. The trusted constructor fixes reviewed command
references, opaque candidate reference, call/request limits and a callback that
must recheck current kernel scope/lease/policy and read-only registry access before using NativeToolGateway. A completed report reference must exist in protected storage before return.
Clients supply only command_ref/candidate_ref, never paths, shell text, owner,
project, approval, policy, permit, authentication or budget fields.

Require initialization before tools, exact closed arguments, bounded UTF-8 JSON,
duplicate/nonfinite/depth rejection and bounded request IDs. Identical request-ID
retries return a cached response without executing again; changed reuse denies.
Allow one active command, with a per-call cancellation event available even while
the callback runs. Unknown/finished cancellation is harmless; it cannot cancel an
initialize request or a kernel goal. A small total session/request/call budget and
no raw stdout, files, resources, prompts or sampling limit the exposed surface.

Callback results are closed bounded outcome/exit/report-reference metadata. They
never assert overall task verification/completion or expose tool output. Errors
use fixed codes; unknown callback outcomes stay unknown. Protocol identity and
tool annotations are not authorization. The next task owns trusted transport,
durable gateway binding, native configuration/permission/hostile-project and actual
authenticated CLI conformance. Those remain required before any enabled shell
tier, full AOS-010 case or G1 promotion.

Primary references: MCP [lifecycle](https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle),
[tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools) and
[cancellation](https://modelcontextprotocol.io/specification/2025-06-18/basic/utilities/cancellation).
Use the published wire contract with stdlib JSON and existing validation. No new
SDK dependency, provider call, credential or account provisioning.
