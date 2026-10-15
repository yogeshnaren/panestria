# Explicit owner profile admission

This task exposes the ciphertext vault's owner operations through separately
mounted local routes. It starts from verified PR #55/main; context integration
in PR #56 and actual Ask dispatch are separate. No default launcher enables
profiles or accesses the owner's keyring in this task.

Reuse GoalApi actor scope, exact loopback Host and CLI bearer checks or paired
same-origin browser session/CSRF. Recheck session authority in the actual database
transaction, including reads. Reject extra authority flags, malformed/oversized
documents and unknown versions with fixed errors that never echo profile values.
Responses, including explicit owner views, use no-store/no-referrer headers.
Remote/read-only device admission must not inherit this owner-only route scope.

Create/correct requests explicitly state the intent to save a RESTRICTED profile,
carry bounded encrypted-document inputs and scoped opaque key identifiers, and
bind expected versions for edits. Derive owner/project/consent actor from trusted
authentication; generate a new consent-action reference on the server. Never
accept plaintext keys, provider credentials, key-store configuration or owner/
project overrides from the request. A missing existing key denies; HTTP cannot
provision/unlock/replace/delete keys. Rotation is an explicit expected-version
owner save under an already provisioned new handle; old keys remain retained.

Viewing clear owner statements is an explicit CSRF-protected POST with exact
version and OWNER_REVIEW purpose, not a cacheable GET or notification payload.
Suppress is scoped, versioned and works even if a wrapping key is unavailable.
No profile values are copied into memory/FTS, telemetry or task events. Requests
do not infer a profile from conversation history or trigger model calls.

Tests cover actual PostgreSQL ciphertext storage through HTTP, paired sessions,
CSRF, Host/Origin/auth, transaction-time revocation, scope, extra fields, bounds,
fixed-error redaction, key denial, suppression/expiry, stale versions and cache
headers. Test-only keys are injected in the trusted application fixture, never
selected by client input. A passing component API test is not an OS/runtime
qualification or permission to enable personal profiles before that boundary
passes. Default production mounting/CLI setup and model dispatch follow later.
