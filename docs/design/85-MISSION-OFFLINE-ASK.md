# Offline Ask intake in Mission Control

Add an explicit production-dashboard option to the existing local Ask launcher.
Reuse its owner/project setup, one registered CPU model, network-isolated runtime,
resource governor, canonical request/receipt/cancellation and cleanup lifecycle.
Do not mount inference on the metadata observer or instantiate another model.

`local serve --mission-assets ABS_DIST` selects this UI at the existing local
settings' IPv4 origin. Default plain Ask assets/browser sessions remain unchanged.
The new mode uses a distinct mission-ask cookie/HMAC purpose and fresh pairing;
observer/default/review cookies grant no Ask-mode authority. The option refuses
combined personal-profile mode rather than silently enabling private context.
No downloads, provider fallback, cloud route, key, certificate or model selection
is added. Startup still requires the original exact offline project policy,
current schema, dedicated cache, CPU admission and exclusive listener/runtime.

The generated OpenAPI catalog includes existing v1 Ask input, receipt and cancel
schemas. Schema publication does not mount Ask on the observer. Responses retain
existing behavior; manual capped parsing still prevents validation errors from
echoing private questions. Only an explicitly configured app advertises Ask.

The React intake submits one UUID and RESTRICTED/offline/no-retention intent.
Questions and answer text stay in memory; sources/usage are canonical receipt
observations. Text renders as inert React text, never HTML. A long local request
has a bounded65second wait for the existing60second server deadline; metadata
reads remain short. Cancellation uses the existing CSRF-protected endpoint.
Unknown results block a new submission until the owner inspects that receipt;
GET never redispatches inference. Existing activity Ask rows and manual UUID entry
permit receipt recovery after reload without localStorage or retained plaintext.
Completed receipts cannot recover discarded answer text. No generic retry, provider
fallback or optimistic completion is offered. Auth loss/page departure clears
private text and aborts the current client request; canonical receipt owns state.

Use actual browser/HTTP/Postgres with an explicitly labeled model/process/capacity
fixture for deterministic input, answer escaping, cancellation, refusal, offline
ambiguity, receipt recovery and session isolation. Retain original default local
and metadata observer regressions. Actual cached CPU inference/OS qualification
is separate; never relabel old runtime certificates. Original three-mode scope,
phone, quality/resource gates and the owner trial remain incomplete.
