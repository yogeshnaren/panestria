# Thin local Ask browser surface

Explicit prerequisite: server PR #63. AOS-017 permits a lightweight web input
when an interface exists. This surface composes its supported local launcher;
it does not replace the R3 React Mission Control/phone/grants obligations.

Serve fixed packaged HTML/JS/CSS at `/` and `/ui/ask.*`, with the existing exact
Host/Origin, CSP and no-store middleware. No external fonts/scripts, analytics,
service workers or persistent browser conversation store. All API calls remain
same-origin and redirect-denied. Use textContent for every model/error/source
value. Scope comes only from authenticated local status, never a URL/query.

`panestria local pair-code --config PRIVATE_JSON` uses the private loopback token
in process memory to issue the existing one-use 120-second challenge. It prints
that short challenge, never the bearer token. The browser exchanges only the
challenge for HttpOnly/SameSiteStrict session cookie and in-memory CSRF token.
Reload requires pairing again; no CSRF/answers/questions in localStorage,
sessionStorage or IndexedDB. Logout revokes the actual session and clears text.

The page sends canonical RESTRICTED, local-only/non-retained v1 Ask with a fresh
request ID and server scope. It shows actual state/answer/provenance without
claiming a release pass, complete profile support or integrated Claude/Cursor.
Cancellation posts the actual request ID and aborts the active fetch; a completed
request remains completed. A bounded deadline/disconnect stops inference. No
silent retry or cloud fallback. Only the current response appears; no chat log.

Test static packaging/CSP, terminal pairing-code redaction, actual cookie/CSRF/
Ask/logout, error/cancel states and browser DOM rendering of synthetic model
markup as literal text. Actual browser/model testing stays distinct from labeled
CI transport fixtures and full A-1/owner-trial acceptance.
