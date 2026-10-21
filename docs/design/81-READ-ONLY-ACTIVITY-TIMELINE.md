# Read-only goal timeline integration

This bounded AOS-028 integration reuses EventReplay and the existing SSE handler;
it adds no event store, authority state, sequence scheme or worker state machine.
A fixed metadata-only mode requires a read-only repeatable-read transaction,
omits goal/task locking and selects only five event metadata columns. Payloads,
trace IDs and payload hashes are not fetched into the observer. The original
full-event mode remains the default with unchanged behavior.

The activity router attaches a scoped metadata endpoint to existing activity/
local Ask applications. JSON returns an authoritative same-snapshot goal/task
view, bounded events, exact decimal continuation and explicit retention/future
cursor resync. SSE uses the existing framing/reconnect/auth/bounded connection
logic with the same fixed server-selected metadata mode. A caller cannot switch
that endpoint to full events. Goal owner/project identity is checked canonically.
The read-only app must not mount the whole goal API to gain event transport.

Cookie authentication may acquire a session share lock, so it runs outside the
read-only observation transaction. Authority is checked before the observation
and immediately before delivery; the SSE handler repeats it between cached
frames and before resync. It never holds a database transaction while waiting
for network delivery. This preserves the existing revocation observation boundary;
it does not claim linearizability against a revocation racing a delivered byte.

The keyboard project pane selects GOAL rows and shows a bounded page plus current
snapshot. It keeps Ask state/action controls separate, labels stale/unconfirmed
reads, preserves decimal strings and drops unverifiable history on resync. It
does not interpret event names as completion or approval. No payload rendering,
Markdown, model/provider work, policy grant or public/phone ingress is introduced.

Actual PG/HTTP/SSE/PTY checks exercise scoped denial, no content/fingerprint,
held goal locks, no mounted mutations/event writes, canonical resync, reconnect,
large decimal IDs and revocation between cached frames. One new PTY wait first
missed a line already received in the previous redraw; the correction checks the
existing buffer and confirmed snapshot message with unchanged timeout/assertions.
Full Mission Control/client reducer/phone and release cases remain incomplete.
