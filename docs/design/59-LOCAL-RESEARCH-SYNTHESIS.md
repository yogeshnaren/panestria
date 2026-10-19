# Local retained research draft

AOS-023 component, plan revision 3. A PUBLIC research request already stopped in
VERIFYING can now produce a bounded answer draft from its retained excerpts.
This is separate from qualified support/contradiction evaluation, automatic
query planning and the D-1/G2 gate. Original specifications remain unchanged.

The local owner CLI requires `--retain-local-draft`, a private synthesis config,
a new private output path and an idempotency key. It resolves the current owner,
project, goal, task, read policy, question and every retained source through
canonical Postgres/CAS records. No model prompt can authorize a tool or policy.
INTERNAL or more restrictive inputs are refused by this first component.

The controller chooses up to four distinct passage prefixes of 384 UTF-8 bytes
and a 512-byte question prefix. It records exact byte ranges, source/text hashes,
policy reference, task version/epoch, shortening and omissions. The model receives
question/passage text and controller IDs p1–p4, without source URLs or store paths.
It returns 1–4 typed claims with IDs. Extra fields, invented IDs, incomplete
streams, unknown usage and invalid JSON are rejected; there is no repair retry.
Citation membership proves provenance access, **not semantic support**.

The existing pinned local model runs CPU-only, network-none, nonroot, with a
read-only root, no host tools or credentials, 2 CPUs and 2.5 GiB RAM. Existing
primary-lease and foreground-resource admission apply. `preserve_existing=True`
refuses displacement of an existing owner controller. The bridge now permits
only literal `format: "json"` on generation; arbitrary schemas/tools remain
outside its allowlist. Default Ask calls do not request a new format.
Protocol references checked 2026-10-18: [Ollama generate](https://docs.ollama.com/api/generate)
and [structured outputs](https://docs.ollama.com/capabilities/structured-outputs).
These document formatting, not accuracy. No external implementation was copied.

Before inference, one acknowledged input artifact and STARTED event commit in
the same Postgres transaction under project/goal/task locks. No database lock
spans model execution. Inputs are rechecked immediately before dispatch and before
publication; task/policy/source changes fence output. A successful draft artifact
and RETURNED event commit together. Every event allocation is the transaction's
last write, preserving the global ordering rule. A failure is best-effort recorded
only if no RETURNED event exists. Ambiguous completion never becomes permission
to repeat inference. Same-key requests revalidate retained output or report
UNCONFIRMED/FAILED; a different key cannot create a second attempt for this request.
A crash can leave STARTED without a terminal event; operator reconciliation is
required, rather than blind retry. In-flight cancellation prevents publication;
it may run until the bounded local deadline before returning.

Output is a separate immutable draft artifact, leaving collected excerpts intact.
It contains actual measured token counts and complete input/provenance bindings.
Inspection checks input/output artifact rows and bytes, source lineage and current
scope/state/policy again. HTML exports escape every untrusted string, disable
active content and render URLs as text. Exports are exclusive 0600 files in a
canonical owner-only 0700 directory. Terminal receipts contain only IDs, counts,
hashes and fixed status; no question, claim, URL, config path or DSN.

Support/contradictions remain NOT_ASSESSED, completion authority NONE, task VERIFYING
and goal ACTIVE. No memory learning, training rights, entitlement or release pass
is inferred. The small local model may omit facts or produce an unusable draft;
no quality claim is made from schema validation. Later support qualification and
planner work must retain these drafts as untrusted inputs and preserve lineage.

Validation uses actual disposable PostgreSQL, CAS and isolated reader, explicitly
synthetic fetch/model fixtures for failure/concurrency cases, plus a separate
actual CPU model smoke check when the pinned cache and resources are available.
No mock result can replace live search, public TLS or semantic qualification.
