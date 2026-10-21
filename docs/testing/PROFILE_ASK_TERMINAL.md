# Ask with one explicitly selected encrypted profile

`profile ask-tui` connects the existing restricted-profile Ask API to the keyboard
Ask application. It pins one profile ID, exact row version, approved field list
and purpose from a private selection file. It never picks the newest profile,
uses ordinary Ask as fallback or sends these values to a remote worker/provider.

Prerequisites remain a separately qualified, explicitly enabled local owner
profile/Ask server and its existing owner authentication. The ordinary local
Ask/activity launchers still leave profiles disabled/unmounted. This client does
not enable that service, provision keys, migrate a database or qualify a runtime.
Use the [private client configuration](PROFILE_STYLE_TERMINAL.md), existing
[restricted profile Ask boundary](PROFILE_ASK.md) and, for communication
preferences, the [structured style editor](PROFILE_STYLE_TERMINAL.md).
Supported personal-mode service/onboarding remains a required next integration.

Save this metadata in a private mode0600 file outside Git, with the actual
approved profile ID and current row version:

```json
{
  "profile_id": "<existing profile UUID>",
  "expected_row_version": 0,
  "purpose": "STRUCTURED_RESPONSE_STYLE",
  "fields": ["communication"],
  "destination": "OFFLINE_LOCAL_MODEL",
  "max_bytes": 2048
}
```

The selection contains identifiers/field metadata, not clear profile statements,
examples or keys. Other supported purposes/fields retain their existing explicit
approval restrictions; do not widen them just to make a request succeed. The
selection is read once for this terminal session. A correction requires a new
explicit selection/relaunch; it does not silently update an active request.

```bash
panestria profile ask-tui --config /absolute/private/profile-client.json \
  --selection /absolute/private/selection.json --restricted-offline
```

Expect a PROFILE ASK header and the selected profile ID/row version. Connection
means the scoped profile service is configured; key, source, policy, resource and
model checks still run on each question. F2/n starts a question, Enter submits it,
F6/c requests cancellation, F5/r refreshes status/receipt, F4/t shows the same
read-only project activity and F10/q quits. There is no automatic resubmission.

The request is fixed to RESTRICTED/offline,4096 context tokens,128 output tokens
and the existing30-second generation deadline. Its HTTP envelope is65 seconds;
control/metadata calls remain bounded to5 seconds. The server remains the sole
admission/verification authority. Status does not load a key/profile/model or
claim runtime qualification.

A returned answer appears only in this terminal. Its receipt must match the
selected profile/version/fields/purpose and carry ciphertext/source references,
`OMITTED_RESTRICTED_PROFILE` and a null response hash. Receipts cannot recover the
unretained answer. Auth/scope loss clears sensitive views. A lost answer reply
or transient receipt error keeps the original request identity and blocks a new
question until its canonical terminal state is confirmed. Cancellation cannot
undo a completed answer. A confirmed UNAVAILABLE resource outcome is displayed
honestly and grants no retry by itself. No alternate model/provider/ordinary Ask
route is selected. The owner must decide on any new request.

[Connected evidence](../../evidence/profile-ask-terminal-2026-10-21/report.json)
uses real PostgreSQL/crypto/loopback HTTP/PTY, explicit synthetic keys/model and
capacity. It observes selected encrypted style reaching the existing local-model
boundary, omitted private output fingerprints, receipt-only recovery,
cancellation, resource denial, disabled/stale selection refusal and no repeat
inference after lost reply/receipt outage. No actual model/keyring/owner profile
was used. Real style faithfulness, supported sensitive-mode onboarding and the
remaining personal-platform/release gates remain unqualified.
