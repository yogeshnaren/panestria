# Review a connection for anonymous public research

This connects a reviewed declaration to the supported **anonymous PUBLIC HTTPS
fetch** path. It sends selected URLs to explicitly named origins; it uses no
login, API key, browser cookies or private folder. It still requires a separately
qualified current research runtime and reviewed PUBLIC-web policy. Actual search
setup is owner-deferred. These instructions do not declare that runtime ready or
grant a release pass.

Use a dedicated project and the existing [PUBLIC policy guide](OWNER_RESEARCH_POLICY.md),
[question staging guide](OWNER_RESEARCH_SUBMISSION.md) and
[connection terminal setup](CONNECTION_DECLARATION_TERMINAL.md). Keep private files
outside Git. The examples below assume the explicit private paths selected there,
a staged question task UUID and owner-chosen new proposal UUID. Do not paste keys.

1. Run `connections serve --config /absolute/private/connections/activity.json`
   in its own terminal with the existing database environment. It is a foreground
   loopback declaration-review service, with no worker/root/account activation.
2. Prepare a new private template (replace UUIDs/paths/origins deliberately):

   ```bash
   uv run --frozen panestria connections prepare-public-fetch \
     --config /absolute/private/connections/activity.json \
     --research-config /absolute/private/research/settings.json \
     --task-id TASK_UUID --proposal-id NEW_PROPOSAL_UUID \
     --origin https://example.org --origin https://example.net \
     --max-calls 16 --max-bytes 8388608 \
     --max-wall-seconds 3600 --expires-seconds 3600 \
     --output /absolute/private/research/fetch-proposal.json
   ```

   Expect `TEMPLATE_CREATED_UNVERIFIED`, runtime unavailable and an anonymous
   service identity. This creates one new0600 file only. Existing output and scope
   mismatch refuse. Template creation is not a proposal, approval or certificate.
3. Submit that exact template, then review it separately:

   ```bash
   uv run --frozen panestria connections propose \
     --config /absolute/private/connections/activity.json \
     --request-file /absolute/private/research/fetch-proposal.json
   uv run --frozen panestria connections review \
     --config /absolute/private/connections/activity.json \
     --proposal-id NEW_PROPOSAL_UUID
   ```

   Read to END, inspect account/configuration/origins/actions/classification,
   limits/expiry/policy/digest; press a, then separately y only for the exact
   declaration you intend. Decline with d then y. Inspect canonical state after
   an uncertain reply; do not automatically retry. DECLARED_ACTIVE still does
   not mean a runtime is certified.
4. Inspect the returned grant and version:

   ```bash
   uv run --frozen panestria connections show \
     --config /absolute/private/connections/activity.json --grant-id GRANT_UUID
   ```

   Explicitly add the exact reference to your private research settings:

   ```json
   "fetch_connection": {"grant_id": "GRANT_UUID", "version": 1}
   ```

   Keep its other fields and0600 permissions. Configuration selects a declaration;
   it creates no permission. A missing reference refuses collection. Changed
   policy, revoked/replaced/expired declarations, old versions, wrong capability/
   account/configuration and unmatched runtime certificates refuse before fetch.
5. Use the existing explicit [collection command](OWNER_RESEARCH_COLLECTION.md).
   Expect only declared exact origins; if search returns an ungranted target or
   redirect, it stops without sending to that target. Inspect the failure and
   prepare a separately reviewed replacement if needed; there is no automatic
   widening. Old pinned plans cannot silently adopt a replacement.

Budgets are shared across all tasks/goals using this declaration revision. Every
possible redirect is reserved before dispatch, even when unused. Calls therefore
mean reserved HTTP hops, not completed sources. Bytes reserve each possible hop's
49153 application request/framing/buffer bytes plus terminal body capacity+1.
They are conservative **application capacity**, not measured wire usage or TLS/
DNS/TCP cost. Lost acknowledgment, failure and revocation never refund capacity.
Exhaustion before a new collection prevents even its search/lease; a mid-collection
capacity stop is recorded as `connection_limit`. Source retention still means
unassessed evidence, not supported factual conclusions or task completion.

To disconnect, use `connections revoke` and separately review/confirm the retained
proposal as in the connection terminal guide. Further hops/publication are fenced;
already sent bytes cannot be recalled. Keep uncertain/history records for review.
This feature does not manage authenticated accounts, secrets or local roots.
Full adapter/OS/public TLS/search qualification and cumulative gates remain open.
