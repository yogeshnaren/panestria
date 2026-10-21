# Use structured preferences in local profile Ask

This is an opt-in local profile Ask path. The separate [style terminal](PROFILE_STYLE_TERMINAL.md) now edits the bounded preferences through the existing owner API; it does not enable that API or select a profile for Ask.
First read [restricted Ask setup](PROFILE_ASK.md), [profile owner API](PROFILE_OWNER_API.md)
and [runtime qualification](PROFILE_RUNTIME_QUALIFICATION.md). Keep personal mode
disabled until its existing explicit local key/runtime prerequisites pass. This
change does not create credentials or configure your owner database/services.
After normal backup/review, the selected database must be migrated to
`0032_structured_style` before starting the updated local application.

In a new or corrected encrypted profile, set `communication` to the JSON string
for these preferences and independently approve that field for local context:

```json
{
  "schema_version": 1,
  "language": "en",
  "audience": "beginner",
  "detail": "concise",
  "formatting": "auto",
  "tables": "when-useful"
}
```

The outer profile document still uses `fields.communication` as a string and
`approved_for_local_context: ["communication"]`. It is encrypted by the existing
profile API. Do not place private profile documents or examples in Git or terminal
history. This component accepts no private examples or arbitrary action rules.

For an enabled local `POST /v2/ask`, use the same authenticated owner/profile
request as the restricted Ask guide, with this selection (actual IDs/version):

```json
{
  "profile_id": "<existing profile UUID>",
  "expected_row_version": 1,
  "purpose": "STRUCTURED_RESPONSE_STYLE",
  "fields": ["communication"],
  "destination": "OFFLINE_LOCAL_MODEL",
  "max_bytes": 2048
}
```

Expect a RESTRICTED offline-local response with a ciphertext/source-bound
renderer2 receipt. Clear profile/output text and unkeyed input/output hashes are
not retained. Preferences guide wording; they do not prove that a model preserves
every fact or that the owner prefers the result. Facts/numbers/citations and
uncertainty still require evaluation. Corrections, lost/suppressed keys, changed
policy, wrong scope/version, malformed preferences and forged output labels deny.

Plain `RESPONSE_STYLE` remains the legacy freeform mode; it does not auto-parse a
JSON-looking field. No default setting changes and no cloud/native worker
inherits these preferences. The new renderer cannot be downgraded away after its
audit exists; preserve the database and use reviewed restore/forward repair.
