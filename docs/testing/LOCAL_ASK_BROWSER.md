# Test the local Ask browser

Use current main after the browser task is merged. Follow the
[local server setup](LOCAL_ASK_SERVER.md) with your explicit offline Ask project,
private configuration/local token and existing read-only public model cache.
The old R0 server and native review demo are separate applications.

1. Keep `panestria local serve --config /absolute/private/local.json` running in
   one terminal. Open its configured origin (default `http://127.0.0.1:8766/`).
2. In another terminal, run:

   ```sh
   uv run --frozen panestria local pair-code --config /absolute/private/local.json
   ```

   Copy only the returned eight-character code into **Connect this browser**.
   It expires after two minutes and works once. Never paste the bearer token or
   provider credentials into this page. Pairing uses the same owner/project
   session and CSRF rules as the canonical API.
3. Ask “Reply with only READY.” Expect an actual local answer, COMPLETED state,
   RESTRICTED/offline label and response-not-retained receipt. The first request
   can be cold. Sources appear only when actual scoped context was included.
   A missing resource/model or denied request reports a reason and starts no
   automatic retry/cloud fallback. The CPU launcher measures real CPU/RAM/disk/AC
   capacity without depending on unused GPU tools; GPU capacity stays unprobed.
4. Start a longer question and press **Cancel**. The page shows the actual durable
   receipt state. A response that already completed stays completed; a failed
   cancellation is shown as unconfirmed rather than asserted successful.
5. Press **Disconnect and clear**. Expect revoked-session confirmation, cleared
   text and disabled Ask controls. Reload also clears text and requires a fresh
   terminal code; it does not claim to revoke every prior server session.
6. While paired, the page checks session access every five seconds plus request
   time. Browser timer throttling or connection loss can delay detection. A
   detected 401/403 clears the question, answer, sources and scope and stops new
   Ask input; a fresh pairing is required. This is UI suppression, not physical
   erasure or a claim that an in-flight model request was cancelled on the server.
   Disconnect clears the view immediately while revocation is pending. An
   unconfirmed revocation retains only the in-memory retry handle and enables
   **Disconnect** again. Reload/page exit discards that handle. Late Ask/pairing
   responses cannot restore a departed session's text or scope.

The page keeps only its current text and an in-memory CSRF value. No localStorage,
sessionStorage, IndexedDB, analytics, external assets or conversation store. Model
HTML appears as literal text. Browser memory/model RAM and existing metadata
receipts are not a claim of physical erasure. The app is loopback-only; narrow
layout testing is not remote phone access. Do not publicly forward its port.

Personal profiles, Build/tools and cloud routes remain disabled/unmounted here.
This thin AOS-017 surface is separate from R3 React Mission Control, connection
grants and phone obligations. R1/G1 and R3 acceptance remain pending.

The [current session correction](../../evidence/r1-session-revocation-2026-10-18/report.json)
records a real in-app-browser/HTTP/PostgreSQL/local-CPU-model answer followed by
injected revocation in its disposable database. The page cleared the answer and
question, hid the result and disabled Ask; browser console errors/warnings were
empty. Seventeen related checks also pass, including seven executable JavaScript
seam scenarios and actual PostgreSQL cached-snapshot/event revocation. CPU browser
evidence does not pass the unresolved GPU latency/pressure cases or complete G1.

[Actual browser/model observations](../../evidence/local-browser-2026-10-15/report.json)
include synthetic local-model HTML completion, literal DOM rendering, durable
cancellation, reload/re-pair, logout, empty browser error logs and responsive
layout checks. Earlier full-probe failure is retained in that report; separate
PR #64 fixes CPU admission without claiming GPU driver recovery. Owned disposable
databases/model sockets/containers were stopped afterward. The owner's demo on
8871 and databases stayed unchanged.

Default CI tests actual PostgreSQL and HTTP handlers with labeled model fixtures:

```sh
uv run --frozen pytest tests/integration/test_local_web.py \
  tests/integration/test_local_server.py -q
```
