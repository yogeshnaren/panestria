# Select a reviewed native account/context connection

This adds a separately reviewed connection to PUBLIC Claude subscription Build.
It checks the exact existing private account/profile, configuration, current
policy/certificate, expiry and shared capacity during work. Revocation blocks
future effects and the existing supervisor cancels active native work. Already
sent content cannot be recalled. This component does not import chats, create a
login, install a provider, enable background work or certify a runtime.

Use a dedicated review project with the existing [Build setup](OWNER_BUILD_CLI.md),
current separately qualified [runtime](BUILD_RUNTIME_QUALIFICATION.md), accepted
[PUBLIC plan](NATIVE_PLAN_EXECUTION.md) and [connection terminal](CONNECTION_DECLARATION_TERMINAL.md).
Keep the matching database environment loaded privately. Preserve other project
databases/services. Implementation tests use synthetic native/auth/certificates;
their results cannot qualify your account or a different source configuration.

1. Start the existing loopback `connections serve` in its own terminal. It stays
   running until Ctrl+C. Choose the Build settings for the same owner/project.
   Keep the current dedicated authenticated profile; do not supply a new key.
2. Choose and retain a new proposal UUID and a stable opaque account UUID. The
   latter is a local reference, not your email, username or token. Generate a
   proposal in an existing private directory with permissions0700:

   ```bash
   uv run --offline --frozen panestria connections native-template \
     --config /absolute/private/connections/activity.json \
     --build-config /absolute/private/build.json \
     --task-id EXISTING_TASK_UUID --proposal-id NEW_PROPOSAL_UUID \
     --account-ref STABLE_ACCOUNT_UUID \
     --max-calls 2 --max-bytes 32768 --max-wall-seconds 900 \
     --expires-seconds 3600 --output /absolute/private/native-proposal.json
   ```

   Expect `TEMPLATE_CREATED_UNVERIFIED`, the protected account-observation hash,
   `billing_verified: false` and `runtime_available: false`. This probes supported
   pinned CLI account metadata only, writes a new0600 proposal and retains a
   bounded private redacted observation. No model prompt, proposal approval or
   worker is started. Wrong owner/project, unsafe output, occupied output or
   unsupported/mismatched CLI/profile refuses; files are not overwritten.
3. Submit and separately review that exact proposal:

   ```bash
   uv run --offline --frozen panestria connections propose \
     --config /absolute/private/connections/activity.json \
     --request-file /absolute/private/native-proposal.json
   uv run --offline --frozen panestria connections review \
     --config /absolute/private/connections/activity.json --proposal-id NEW_PROPOSAL_UUID
   ```

   Inspect every field to END: exact scope, connector/version, account/configuration,
   `claude-subscription` logical route, one pinned profile reference, PUBLIC
   read/write/send, no delete/spend, limits, original expiry/policy and digest.
   `a` then a separate `y` records approval; `d` then `y` declines. Recover an
   uncertain reply by inspecting the same proposal/grant, without resending a
   decision. A declaration remains UNVERIFIED; it is not a runtime certificate.
4. Inspect the resulting grant/version with `connections show`. Explicitly add
   this selection to the same private0600 Build config, keeping other fields:

   ```json
   "native_connection": {
     "grant_id": "RECORDED_GRANT_UUID",
     "version": 1,
     "account_observation_sha256": "ORIGINAL_TEMPLATE_OBSERVATION_SHA256"
   }
   ```

   Use the actual returned version and original hash, not placeholders. Reload
   any intentionally running Build controller to adopt its new private settings.
   Existing unselected configurations retain their policy-only behavior; they
   do not acquire this connection claim automatically.
5. Run the existing explicit `plan run ... --public-subscription-run` or
   `build submit ... --public-subscription-run` command. A two-worker plan needs
   at least two available native calls and enough selected-context bytes. Expect
   WAITING_APPROVAL only after actual independent final checks. This connection
   cannot approve/merge a result. Continue exact owner review in the Build TUI.

Calls count reserved **native process invocations**, not HTTP requests. Bytes
count exact selected PUBLIC context bytes, excluding fixed prompts, auth, output
and wire traffic. Those retain their independent transport/process bounds. This
logical route is not a physical network allowlist or measured cash/quota usage.
At most64 calls per grant version bounds retained ledger work. Reservations are
shared across goals/controllers; uncertainty consumes capacity conservatively.
Wall time starts at the first reservation and includes idle time. No automatic
refund, renewal, fallback, account switch or scope widening occurs.

Use the existing `connections revoke` followed by separate exact review to
disconnect this grant. Further selected work, tools and final publication refuse;
historical receipts remain. Replacement, expiry, changed account/profile/runtime
or policy and exhausted capacity also stop future effects. Reauthorization needs
a new deliberate review and exact config selection. Completed local owner merge
review remains separately governed by policy and its exact approval.

For an already reviewed background job, the selected connection and existing
queue/account/no-extra-spend/foreground-reserve guards must all allow execution.
This config cannot enable a queue or refresh billing. The owner's real billing
observation remains stale/background off. Search and real-phone setup are deferred.
General root/secret/OS/adapter conformance, TC05-TC08 and cumulative gates remain
open. [Component evidence](../../evidence/native-connection-grants-2026-10-23/report.json)
distinguishes real disposable PG/Git/MCP/Docker checks from synthetic native/auth.
