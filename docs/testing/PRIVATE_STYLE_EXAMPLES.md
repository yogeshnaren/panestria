# Review private presentation examples for offline Ask

Use the existing [qualified profile service](QUALIFIED_PROFILE_SERVICE.md) and
[style client](PROFILE_STYLE_TERMINAL.md). Normal Ask/activity remain
profile-disabled. This feature does not provision keys or enable a service.

Prepare your own private mode0600 JSON file outside Git/model caches. The file
contains plaintext you intentionally supply; Panestria reads it once and keeps
it unchanged. Do not include third-party private content without authorization.
For example:

```json
{
  "examples": [
    {
      "reference": "concise-explanation",
      "input": "Explain a measurement with uncertainty.",
      "response": "The measured value is 42. Its uncertainty remains unassessed."
    }
  ]
}
```

At most two examples are allowed. References are unique within this profile and
use lowercase letters/digits/underscore/hyphen, starting with a letter, up to48
characters. Input is at most256 UTF-8 bytes and response384. Empty text,
control/bidi/format characters, extra authority fields and duplicate refs are
refused. These are owner-supplied presentation examples, not verified facts.

For an existing profile at its exact version:

```bash
panestria profile style-tui --config /absolute/private/profile-client.json \
  --profile-id PROFILE_UUID --expected-version ROW_VERSION --owner-review \
  --examples-file /absolute/private/examples.json
```

For a new profile, use the existing scoped `--key-id` instead of
`--expected-version`. Import replaces the whole example set; omit the option to
preserve current examples. An explicit `{"examples":[]}` replaces it with none
only after the normal save confirmation.

The form shows the example count. Press v to inspect the private wrapped text;
j/k scroll. At the end press a to acknowledge review. Esc/q returns without
acknowledging. Press s and then y to save exactly once. A premature save sends no
write. Local-context approval is a separate field, off by default for a new
profile. Saving does not submit an Ask request or grant training rights.

A confirmed save reports the new row version. For SAVE UNCONFIRMED, inspect the
canonical profile/version before another explicit correction. Reopening a
profile with examples requires a new review before saving. Other fields,
approvals and expiry are retained.

To use the examples, separately select this exact approved profile/version,
communication field and STRUCTURED_RESPONSE_STYLE purpose in the existing
[profile Ask terminal](PROFILE_ASK_TERMINAL.md). The same private context-byte
limit applies; an oversized selection is denied rather than silently truncated.
The original ciphertext/version/purpose binds the examples. Correction,
suppression, expiry or revocation fences an old request. Only the eligible
restricted offline model receives the ephemeral overlay. No examples are sent
to Claude/Cursor/cloud clients, exported as training data or stored in ordinary
context/learning tables by this feature.

Terminal recording and the owner-supplied input file remain outside erasure
guarantees. Readability/preference/factual fidelity and full original gates still
need their own evidence. No historical runtime certificate is refreshed by this
component. See [design97](../design/97-PRIVATE-STYLE-EXAMPLES.md).
