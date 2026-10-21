# Edit encrypted communication preferences in the terminal

`profile style-tui` adds an explicit keyboard editor for the existing encrypted
owner-profile API. It changes language, audience, detail, formatting and table
preferences, plus a separate choice approving communication for offline local
context. Saving does not select the profile for Ask, start inference, provision
keys or enable a server. The fixed honesty/uncertainty charter is not editable.

This is partial AOS-017-S4 delivery. The ordinary local Ask/activity launchers
still leave profile routes disabled/unmounted. Use this client only with a
separately configured, qualified, explicitly enabled owner-profile API, including
the canonical activity scope route. It does not certify or bypass the remaining
[profile setup/runtime boundary](PROFILE_RUNTIME_QUALIFICATION.md). Supported
owner personal-mode service onboarding, private examples and full S4/S5/S6
qualification remain pending. No owner server/database/key store was configured
by the implementation checks.

Prepare a private mode0600 JSON client file with the already selected
owner/project UUIDs, loopback port and an **existing** private owner bearer file.
This file contains routing metadata; never put token/key values in it or Git:

```json
{
  "schema_version": 1,
  "owner_id": "<existing owner UUID>",
  "project_id": "<existing project UUID>",
  "bind_host": "127.0.0.1",
  "bind_port": 8766,
  "token_file": "/absolute/private/existing-owner.token"
}
```

The origin is fixed to IPv4 loopback; redirects, proxy environment settings,
remote hosts and extra enablement flags are denied. The client checks canonical
owner/project metadata before any profile disclosure or write. It needs no model
cache, database credential or OS-key access. The server performs the existing
owner authorization, key, ciphertext and exact-version checks.

To create a communication-only profile using an already provisioned scoped
profile/key handle from [explicit key setup](PROFILE_KEY_SETUP.md):

```bash
panestria profile style-tui --config /absolute/private/profile-client.json \
  --profile-id PROFILE_UUID --key-id EXISTING_KEY_UUID --owner-review
```

To explicitly view and correct an existing profile at its exact row version:

```bash
panestria profile style-tui --config /absolute/private/profile-client.json \
  --profile-id PROFILE_UUID --expected-version 0 --owner-review
```

The terminal must be at least80 columns by22 rows. Arrows or j/k select a field;
left/right or space cycle values. Common language choices are en/es/fr/de/hi/zh;
an existing other valid language is preserved and remains selectable. New
profiles default to no local-context approval. Press s for the review, then y
to save once. Esc/q cancels the review; q on the form exits without saving.
Other existing profile values and approvals/expiry are preserved without being
displayed. Legacy freeform communication abstains rather than being silently
converted or overwritten. Concurrent changes require a fresh exact-version view.

A confirmed save shows its new row version. A lost/error reply shows
SAVE UNCONFIRMED and disables further writes in that form. Do not assume the
save failed: reopen the exact profile/version to inspect, then decide on another
explicit correction. No retry, overwrite, key creation, grant, cloud export,
model call, local-context selection or task/goal PASS follows a save. Plaintext
stays in process memory; the client writes no profile file, prompt/response hash
or transcript. The terminal restores its settings on exit. Host/terminal capture
and previously delivered text are outside erasure guarantees.

For the subsequent separately selected local Ask request, use
[structured profile style](STRUCTURED_PROFILE_STYLE.md) and its exact approved
profile/row-version/purpose. This editor does not qualify style faithfulness,
readability or owner preference.

[Source-bound checks](../../evidence/profile-style-terminal-2026-10-21/report.json)
use actual PostgreSQL/crypto/loopback HTTP/PTY with synthetic in-memory keys and
no inference or actual keyring access. They cover encrypted create/correction,
no-save cancellation, preserved other fields, separate local-context approval,
wrong-scope/stale/disabled/freeform refusal and a committed save whose reply is
lost without repeating the write. Original failed PTY redraw expectations are
preserved separately from the corrected observations. This is not a release gate
or completed personal-platform integration.

For the supported explicit service setup, use the [qualified profile service](QUALIFIED_PROFILE_SERVICE.md).
Normal Ask/activity launchers remain profile-disabled.
