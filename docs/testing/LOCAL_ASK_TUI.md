# Use Panestria from the terminal

This is the keyboard **offline Ask** application. It displays real local-server
readiness, lets you ask a question and shows its answer/receipt. It does not yet
include Claude Build, research, a setup wizard or the complete MVP dashboard.

First complete the existing [one-time local Ask setup](LOCAL_ASK_SETUP.md) and
[private configuration/server instructions](LOCAL_ASK_SERVER.md). Keep the same
owner/project IDs and local.json. No provider API key is needed. No model is
downloaded or cloud provider selected by this interface.

In **terminal A**, start the server using your existing database environment:

```bash
uv run --frozen panestria local serve --config /absolute/private/local.json
```

Leave it running. In **terminal B**, open the terminal application:

```bash
uv run --frozen panestria tui --config /absolute/private/local.json
```

Expect a full terminal screen headed **Panestria | OFFLINE ASK**. Once the scoped
server answers, it shows CONNECTED. An unavailable server/setup shows a reason;
CONNECTED is readiness, not a successful inference or release-gate pass.

1. Press **n** or **F2**, type “Explain what a database is in three simple
   sentences.”, then **Enter**. Up to4096 UTF-8 bytes are accepted.
2. Wait for the actual answer and **COMPLETED** receipt. The screen remains
   responsive. First inference can be cold; there is no cloud fallback. Each
   question is a separate request, not an automatically retained conversation.
3. **PgUp/PgDn** scroll the answer. Context source IDs appear only when sources
   were actually included; this is provenance, not factual support verification.
4. **c/F6** requests cancellation. Wait for CANCELLED or another actual terminal
   state. Already completed work remains COMPLETED.
5. **r/F5** checks the server and refreshes the receipt. After a lost response,
   use the existing request ID; the client will not automatically resubmit.
   A receipt cannot recover answer text that was deliberately not retained.
6. **q/F10** closes the terminal app. During submission, a second quit confirms
   leaving an unconfirmed request; use cancellation first if you want it stopped.
   F10 also leaves question-editing mode. Escape discards an unsent question.

Use a terminal at least64 columns wide and18 rows high. Smaller windows show a
resize message. Closing this view does not stop terminal A or its database.
Stop terminal A with Ctrl+C when done. Both services retain their existing scoped
shutdown rules; unrelated services/controllers are preserved.

No question/answer history or terminal recording is created by the app. Access
loss clears its view and fences late responses. Your terminal software may have
its own recording/memory; physical erasure is not promised. Never paste provider
keys or database credentials into a question.

Focused component checks use actual PTY/HTTP/Postgres with labeled model fixtures:

```bash
uv run --frozen pytest tests/integration/test_ask_tui.py -q
```

They do not establish actual model quality, full A-1/G1 or R3 acceptance.
