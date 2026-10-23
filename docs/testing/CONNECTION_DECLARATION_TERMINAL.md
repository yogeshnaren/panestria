# Review intended connections in the terminal

You can now review and revoke **connection declarations**. This does not connect
an account/folder, import chats or enable a tool. Every result explicitly says
DECLARATION_ONLY, conformance UNVERIFIED and `runtime_available: false`.
Actual account/broker/conformance integration remains required for R3.

Use current main with locked dependencies installed. The database must already
be migrated and contain an existing owner, project, task and initialized project
policy, such as your existing [Build project](OWNER_BUILD_CLI.md). Use its unchanged
IDs. Load its private `PANESTRIA_DATABASE_URL` environment without printing it.
These commands create no project/task/policy and request no provider login/key.

Prepare a new private directory once, choosing an unused loopback port:

```bash
uv run --offline --frozen panestria connections init \
  --directory "$HOME/.panestria-connections" \
  --owner-id OWNER_UUID --project-id PROJECT_UUID --port 8784
```

Expect CONFIGURED and `project_created: false`, `server_started: false`. It reuses
the private activity format (`activity.json`, `activity.token`, initialization
lock); this is an owner/project configuration, not a connected account. Existing
unsafe/conflicting files are refused, not overwritten. Keep them out of Git.

Terminal 1, with the database environment loaded:

```bash
uv run --offline --frozen panestria connections serve \
  --config "$HOME/.panestria-connections/activity.json"
```

Expect STARTING / CONNECTION_DECLARATION_REVIEW_ONLY. Leave it running; Ctrl+C
stops this foreground process. It installs no OS service and starts no worker or
model. An occupied port is refused without stopping the existing service. This
mode provides no browser/phone endpoint or goal/Ask/merge/pairing mutations.

In terminal 2, inspect scope and the current policy reference:

```bash
uv run --offline --frozen panestria connections scope \
  --config "$HOME/.panestria-connections/activity.json"
```

Create an absolute private request file, permissions `600`, following the existing
[`ConnectionManifest`/`ConnectionReviewRequest` contracts](../../src/panestria/contracts/connections.py).
Its outer shape is:

```json
{
  "schema_version": 1,
  "task_id": "EXISTING_TASK_UUID",
  "change": {
    "proposal_id": "NEW_UUID_RECORDED_BEFORE_SUBMISSION",
    "policy_ref": "CURRENT_POLICY_REF_FROM_SCOPE",
    "grant_id": null,
    "expected_version": 0,
    "operation": "REPLACE",
    "manifest": {
      "schema_version": 1,
      "owner_id": "EXISTING_OWNER_UUID",
      "project_id": "EXISTING_PROJECT_UUID",
      "connector_ref": "public-web",
      "connector_version": "fetch-v1",
      "configuration_sha256": "64_LOWERCASE_HEX_CONFIGURATION_HASH",
      "account_ref": "OPAQUE_ACCOUNT_REFERENCE_UUID",
      "actions": ["send"],
      "data_classes": ["PUBLIC"],
      "root_refs": [],
      "origins": ["https://example.com"],
      "budget": {
        "max_calls": 2, "max_bytes": 4096,
        "max_cash_microusd": 0, "max_wall_seconds": 30
      },
      "expires_at": "FUTURE_UTC_TIME_WITHIN_30_DAYS",
      "conformance_sha256": null
    }
  }
}
```

Replace placeholders deliberately. Do not put credentials, raw private paths or
account details in this metadata. A synthetically labeled practice declaration
can test the UI on a disposable project; it must not be described as a verified
account/configuration. The example origin is data only and is never contacted.
There is no account/root enrollment in this component. A caller-supplied
conformance hash does not certify anything. Read/write/send/delete/spend are
independent declared actions; approval here executes none of them.

```bash
uv run --offline --frozen panestria connections propose \
  --config "$HOME/.panestria-connections/activity.json" \
  --request-file /absolute/private/request.json
```

Expect PENDING, an exact `effect_digest` and no runtime permission. Preserve the
request/proposal UUID for recovery. Then open its exact review:

```bash
uv run --offline --frozen panestria connections review \
  --config "$HOME/.panestria-connections/activity.json" --proposal-id PROPOSAL_UUID
```

Use PgUp/PgDn or j/k to inspect every field. At END, `a` selects approval or `d`
denial, then a separate `y` sends one exact decision; Esc returns, q exits.
No decision is sent before the end/confirmation. Policy changes or expiry can
refuse it. A successful approval records a declaration; execution stays unavailable.

On DECISION UNCONFIRMED or interruption, inspect that same proposal/grant before
another intent. The terminal never retries a decision, even if its committed reply
was lost. Reopening an already-decided proposal cannot renew its approval.

```bash
uv run --offline --frozen panestria connections show \
  --config "$HOME/.panestria-connections/activity.json" --grant-id GRANT_UUID
```

Expect DECLARED_ACTIVE / DECLARED_REVOKED / EXPIRED, version, CURRENT/STALE policy
and UNVERIFIED/runtime false. To propose revocation, record a fresh proposal UUID
first, then:

```bash
uv run --offline --frozen panestria connections revoke \
  --config "$HOME/.panestria-connections/activity.json" \
  --grant-id GRANT_UUID --task-id EXISTING_TASK_UUID --proposal-id NEW_PROPOSAL_UUID
```

This prepares a REVOKE review against the current policy/version. Review that
proposal separately and confirm as above. This component has no external process
to disconnect; it records the revoked declaration. Historical receipts are
preserved. It performs no data deletion, backup change or paid action.

[Evidence](../../evidence/connection-terminal-2026-10-22/report.json) uses real
disposable PG, loopback HTTP, CLI/PTY and foreground startup, synthetic account/
declaration values and one explicit postcommit503 fixture. It is not live
connector, account, secret-boundary, OS-key or whole-gate qualification.
