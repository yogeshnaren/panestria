# Supported local Ask process

Explicit prerequisite: owner setup PR #62. The accepted R0 server and preserved
native proposal demo remain separate. This task delivers a supported v1 offline
Ask process and CLI path; the next UI task composes it into a browser surface.
Profiles stay disabled until their remaining setup/boundary obligations qualify.

Use the existing pinned Uvicorn 0.54.0 dependency instead of a new HTTP parser.
REA's [source path](https://github.com/morluto/rea/blob/main/.agents/skills/reverse-engineer-anything/SKILL.md)
applies: inspect installed complete relevant source, retain identities/limitations,
and verify runtime behavior. No REA engine installation or target acquisition.
Uvicorn's BSD-3-Clause dependency stays unmodified; uv.lock pins its distribution.
Source inspected: server.py, config.py, protocols/http/h11_impl.py, lifespan/on.py.
Its [deployment guide](https://www.uvicorn.org/deployment/) describes programmatic
single-process serving and its settings expose the bounds used here.

Important observed source behavior: `serve(sockets=...)` accepts an owned prebound
socket; shutdown waits then cancels requests and runs ASGI lifespan; signal replay
occurs after that lifespan. Model cleanup therefore belongs inside lifespan, with
an outer finally for startup failures. Disable access/ASGI/error log handlers,
proxy headers, reload, multiple workers, websocket transport and core dumps.
Set concurrency/backlog/header/keepalive/graceful-shutdown bounds explicitly.
Middleware still enforces full body/header/exact Host/Origin/CSRF limits. No global
logging/exception text, prompt, token or database URL goes to process output.

The owner supplies a bounded private versioned JSON config and private local
bearer token file; the existing DB URL comes only from the environment. No .env
autoload, provider credential creation, image/model download, fallback, migration
on boot or implicit project setup. Stable domain-separated session signing derives
from the local token; rotating it intentionally invalidates previous sessions.
The config enables only literal loopback and the pinned CPU model/cache. Cache
must be dedicated public model data, not an owner home/project mounted wholesale.

Bind the exact port before starting a model. Refuse conflicts and preserve other
listeners. Verify schema/current read-only policy/setup audit, actual hardware
headroom and pinned local model catalog. Acquire the existing global primary
lease; preserve every pre-existing model container, even stale ones. Start only
the owned network-none constrained runtime and stop only that exact identity.
Never reap owner services during this launcher. Startup failure is redacted and
cleans owned resources; cancellation/shutdown stops admissions and active Ask.

Mount only owner scope, pairing, memory/learning and Ask routes. No synthetic
driver or goal/merge/tool routes are exposed. Authenticated local status reports
current DB/policy/socket/admission facts and disabled profiles. Existing /readyz
retains its historical DB-only contract, not complete executor/release readiness.
Ask itself rechecks resources/policy/source before every local inference.

Prove private configuration, scope, port conflict, preserved model controller,
DB/policy/schema failure, real HTTP pairing/CSRF/revocation, v1 Ask and receipt
replay, bounded request rejection, actual model startup/shutdown and restart.
Synthetic live evidence is separate from default CI and full G1/R3 acceptance.
