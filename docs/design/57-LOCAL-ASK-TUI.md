# Keyboard terminal application for local Ask

This owner-requested usability slice extends the existing AOS-017-S2 local Ask
surface. It does not replace AOS-028 React Mission Control, phone requirements,
the original gates or the later owner trial. The first terminal application is
Ask-only; Build/research screens and automated first-run setup remain separate.

## Supported journey

With the existing private local.json and separately running local Ask server,
`panestria tui --config /absolute/private/local.json` opens a keyboard screen:
actual server/scope readiness, question input, response, canonical receipt state
and context source IDs. New question, receipt refresh, cancellation, answer
scrolling, resize and quit are available. No model/service/database is installed,
started or stopped by this client. The model remains the existing explicit CPU
launcher, not an implicit subscription/cloud provider.

Use stdlib curses plus existing frozen HTTP/config contracts. No new dependency,
external borrowed code or credentials. The UI requires a real terminal; missing
private configuration gives a closed setup error rather than reading env secrets.
An unconfigured workstation still needs the existing local Ask setup procedure.

## Authority, concurrency and privacy

The client reads the same protected local config/token, uses only its literal
loopback origin, disables proxies/redirects and validates owner/project scope
and disabled cloud/profile routes before question disclosure. Submission is an
explicit RESTRICTED/offline/non-retaining AskSubmission with a fresh known UUID.
The client writes no database or history. API state is the only completion/
cancellation authority; no model text or local spinner can complete a request.

Control HTTP calls have an absolute five-second deadline; Ask has65 seconds.
The deadline includes headers/body, and response bytes are bounded to1MiB.
Bounded daemon workers keep keyboard input responsive. There is no automatic
POST retry. A missing/ambiguous response keeps the known ID for receipt refresh
and refuses another submission until the previous request's terminal state is
confirmed. A proven pre-dispatch failure can return to not-submitted state.
Unretained answer text cannot be recovered from receipt refresh.

View generations fence late responses after a new question, auth/scope loss or
close. Older pending receipts cannot regress a confirmed terminal state. Cancel
is only confirmed from the API; completed work remains completed. Quit during a
submission requires a second quit acknowledgement or cancellation. Exiting the
client does not assert server shutdown or successful cancellation.

Five-second status checks detect access/scope changes while connected. Detected
401/403 or scope mismatch clears question/answer/source/request views, invalidates
pending callbacks and stops new submissions. Network loss marks the connection
unconfirmed while retaining the clearly historical receipt; it does not invent
revocation or erase an in-flight server request. Explicit refresh may reconnect.

Question/answer remain transient process data, without app history/log/export.
No physical memory erasure or control over terminal recording is claimed.
Model/source text is literal: terminal controls, ESC/OSC activators and bidi
format controls are removed before drawing. Wide text wraps for terminal cells.
Curses restores terminal modes and clears its alternate view on normal exit.

## Relevant validation

Use actual PTY/keyboard/resize/terminal restoration and actual loopback HTTP /
disposable PostgreSQL against the canonical Ask API, with explicitly labeled
model fixtures for default CI. Check cancellation/reuse, auth-loss clearing,
actual commit/lost-response receipt recovery, cross-scope pre-disclosure refusal,
absolute body-read deadlines and stale callbacks/unsafe terminal text. Fixture
answers are not actual model qualification or owner acceptance. An actual local
synthetic TUI/model observation, when prerequisites permit, stays separately
source-bound. Do not rerun unchanged provider/GPU checks or stop owner controllers.
