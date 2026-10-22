# Exact PUBLIC Build review in Mission Control

This optional local mode adds the exact protected diff, independent check reports
and frozen merge preview, with explicit **consent recording**. It records approval
or denial; it does **not** execute a merge, start a worker or accept a release.
Default Mission Control remains the read-only metadata observer.

Use current main after this task merges. Build the production frontend as in
[the observer guide](MISSION_CONTROL_OBSERVER.md). You need an existing private
PUBLIC Build root and a migrated database with its existing owner/project.
This mode does not create work, native credentials, certificates or a report store.
The historical observer copy prepared on port8770 has no such Build evidence;
keep it running unchanged. Select a separate unused port/config for this mode.

Load the existing private database environment in the server terminal. Initialize
separate ActivitySettings for the existing owner/project and unused port (example
8772), then explicitly choose the existing Build root:

```bash
uv run --frozen panestria activity init \
  --directory "$HOME/.panestria-build-review" \
  --owner-id OWNER_UUID --project-id PROJECT_UUID --port 8772

uv run --frozen panestria mission-control serve \
  --config "$HOME/.panestria-build-review/activity.json" \
  --assets "$PWD/apps/mission-control/dist" \
  --build-review-root /ABSOLUTE/EXISTING/PRIVATE/BUILD_ROOT
```

Use the root from your existing private Build settings, not its reports child.
It must already contain `reports` and the derived protected owner/project Git
repository. Do not give this service your native login/certificate directory.
Do not combine --build-review-root with --build-evidence-store. Missing, unsafe,
symlinked or nonprivate roots refuse startup. No data is deleted or initialized.

In a second terminal:

```bash
uv run --frozen panestria mission-control pair-code \
  --config "$HOME/.panestria-build-review/activity.json"
```

Open http://127.0.0.1:8772/, enter the one-use code within120seconds and pair.
Observer/default-app sessions cannot substitute for a review-mode session.
Switching modes requires new pairing. No token belongs in a URL or localStorage.

## Review and decide

1. Open an existing PUBLIC Build goal that reached WAITING_APPROVAL. Select
   **Review exact merge request**. Expect canonical task/approval state, version,
   full effect digest, frozen preview/destination, base/candidate/tree, protected
   diff and independent check reports. Expand the check rows to read the actual
   verifier JSON. These records include reasons/output hashes, not complete test
   stdout. Oversized/invalid/unavailable data is UNCONFIRMED rather than truncated
   into an apparently complete preview.
2. Read the diff and required checks. Source/report text is untrusted; it is
   displayed inertly. A complete PASS check set is separate from owner consent,
   merge execution and release acceptance. Older request ordering uses the
   canonical approval.requested event sequence, not expiry as a creation clock.
3. Type the displayed **exact effect digest**, acknowledge reviewing the contents,
   then choose **Record approval** or **Record denial**. A mismatched digest,
   missing fresh snapshot or missing memory-only CSRF value keeps controls disabled.
   After page reload, pair again to restore consent controls.
4. Expect **Consent APPROVED/DENIED. No merge dispatched.** The canonical goal can
   remain ACTIVE and task WAITING_APPROVAL. Approval state and task completion are
   different facts. Denial does not start another worker or silently cancel work.
5. For approved work, inspect through the existing owner Build terminal/CLI and
   perform its separately verified exact merge using the same canonical request.
   [Owner Build instructions](OWNER_BUILD_CLI.md) and [keyboard review](BUILD_REVIEW_TUI.md)
   describe that step. Execution still requires its real current qualification;
   this new UI neither grants one nor renews historical certificates.
6. Refresh/open the goal to observe the confirmed effect and eventual canonical
   completion. No UI event/receipt optimistically marks the goal complete.

The view rechecks while open. Changed request/content/version/state resets the
confirmation. Failed reads remove protected content; observations older than
15seconds disable decisions. A failed decision response is **UNCONFIRMED** and
submits no automatic retry. Inspect the current canonical approval state first:
the server may have committed a decision even if its response was lost. Exact
idempotency receipts remain in the existing kernel store.

While a consent request is in progress, the preview is hidden and the section
reports busy/UNCONFIRMED. Close/refresh/decision controls remain disabled until
that attempt settles. An UNCONFIRMED read or stale label alone does not establish
that the decision finished. After a failed response, reopen the canonical review
and inspect its actual approval state before any new explicit decision. There is
no automatic decision retry or optimistic approval.

## Checks and limits

```bash
uv run --frozen pytest tests/integration/test_mission_build_review.py -q
```

Uses disposable PostgreSQL55439, owned ephemeral HTTP ports, actual Chromium,
protected Git, Docker Bash and independent verification. Native transport/auth/
OS/capacity are explicit TEST_FIXTURE_NOT_LIVE identities. The browser checks an
actual malicious HTML line removed from the baseline diff, offline submission
failure, exact consent and later existing-CLI merge. The required candidate
content assertions are unchanged; the original attempt to replace required
output correctly failed independent checks and is preserved in evidence.

No provider/model calls, new credentials, owner-data migrations or source
certificate relabeling occur in these checks. Prepare frontend/browser artifacts
as in the observer guide, reuse installed runtimes/caches, and do not run suites
sharing55439 concurrently. Original source-bound observations are indexed at
`evidence/mission-build-review-2026-10-22/report.json`.

The [pending/recovery correction](../../evidence/build-review-recovery-2026-10-22/report.json)
retains the original failed CI source and an actual browser/PG/Git regression.
The browser's offline request still fails normally; a test fault delays only its
failure notification to exercise the pending UI deterministically. Canonical
PENDING, one later explicit approval, no browser merge and the separate exact
owner merge remain required. No sleep, timeout increase, force click or decision
retry substitutes for those assertions.

This is partial AOS-028-S2/S3. Full intake, approval inbox/dispatch integration,
Firefox, phone/TLS/device qualification and cumulative G3/trial remain pending.
To disable this mode, stop its process and restart without --build-review-root.
Retain canonical consent/evidence history; default observation rights do not widen.
