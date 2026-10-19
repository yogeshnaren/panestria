# Canonical Build terminal review

This owner-requested usability slice adds an R1 single-worker review interface
over the existing owner CLI. It preserves AOS-027a's approval protocol, original
React/phone requirements and release gates. It does not add another state store,
an autonomous approver, a new Build intake, a provider route or a project grant.

The interface uses the same private Build config and database environment as
the existing owner CLI. Only status/diff, approve and cancel CLI operations are
available; argument vectors never use a shell. Each child owns a separate
session/process group. Read calls have30 seconds, decisions65 seconds, response
bytes are capped at1MiB and failures never echo raw stderr/config/credentials.
Exit/deadline cleanup targets only the exact owned child group. A killed process
may already have committed; termination is never reported as task cancellation.

One bounded background operation keeps keyboard input responsive. Status is an
explicitly refreshed canonical snapshot. Opening an approval freezes the exact
snapshot, digest, approval ID and expected version. The user separately types
MERGE/Enter; cancellation likewise requires CANCEL/Enter with the frozen task
version. Refresh/Escape discards an unsent confirmation. No async update can
silently change the effect that the user is confirming. Existing kernel checks
deny stale or revoked approvals, changed candidates/bases/checks and expiry.

The UI never optimistically completes a task. Successful decisions trigger a
new scoped canonical read. Lost responses or access failures clear transient
content and require explicit refresh; no mutation is automatically replayed.
Late callbacks after close cannot restore the view. Review data is excluded from
object repr, no history is written, and terminal controls/bidi are rendered
inert using the existing original terminal text handling. No new dependency or
external source borrowing is involved. Native runtime qualification and genuine
owner acceptance remain separate from fixture-only terminal integration checks.

Validate actual keyboard diff→frozen review→explicit exact CAS, stale review
after concurrent cancellation, explicit cancellation, actual CAS/lost response
without redispatch, private-config loss/view clearing and terminal restoration.
The [operator guide](../testing/BUILD_REVIEW_TUI.md) states prerequisites and limits.
