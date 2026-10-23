# Using the private phone observer

First follow [private TLS/device setup](PRIVATE_PHONE_INGRESS.md). This is an
optional read-only companion to the workstation, which still runs every task.
Use the existing production build and deliberately selected migrated database;
nothing in this guide enables a network or migrates a database automatically.

After entering the 32-character terminal pairing code, expect **PRIVATE PHONE
OBSERVER**, a last-confirmed workstation timestamp, project activity, and pending
plan/action review metadata. Attention records are prompts to inspect work on the
workstation. They grant no decision or execution permission. Open a goal to see
its task states, lease epochs and canonical event timeline. An ACTIVE goal or
passed check remains separate from owner merge and release acceptance.

To inspect protected PUBLIC Build check/milestone metadata, optionally add the
existing private evidence directory to your selected `phone.json`:

```json
"build_evidence_store": "/absolute/existing/build/reports"
```

Select the `reports` directory under your Build configuration root, not the whole
repository or a raw-artifact directory. It must already exist with private owner
permissions and no symlink path. The reader creates nothing and cannot publish
reports. Omit the field to leave Build evidence explicitly unconfigured. Changing
this selection changes the profile identity: stop/restart the foreground server
and issue a new one-use code. It does not widen an existing device grant.

Test these behaviors with synthetic PUBLIC work before using the deployment:

1. Open a known goal and **Inspect Build evidence**. Compare its required checks,
   milestones, held claims and owner-merge state with the workstation. No diff,
   raw source or private profile should be displayed. Release acceptance remains
   NOT_ASSESSED.
2. Stop the phone server with Ctrl-C. Within roughly15 seconds after the last
   successful read, activity/timeline become STALE / UNCONFIRMED and current
   evidence/inbox rows disappear. The last-confirmed timestamp describes a past
   read. A disconnected view cannot advance a task to completion.
3. Restart the same server/profile while the original grant is unexpired and
   unrevoked. Reads recover without re-running work or extending the session.
4. Disconnect the phone's network, then reconnect. The offline hint clears views;
   returning online requires canonical reads. Background the page and return:
   cached task/evidence views clear and revalidate. Browser suspension may delay
   JavaScript; this is not background notification delivery.
5. Revoke that device from the local owner CLI. Its next denied read clears
   authenticated content and last-seen labels; new access needs a new pairing.

Polling occurs approximately every10 seconds and successful-read freshness lasts
less than15 seconds. These are UI thresholds, not an availability guarantee.
Actual outage/authentication detection requires a foreground browser read.
Requests and responses use `no-store`; no service worker, localStorage or
sessionStorage is used for project data. The browser still retains its HttpOnly
Secure session cookie until expiry/revocation and may keep an OS tab preview.
Reload retains read access while its original grant is valid, but the memory-only
CSRF token is lost; local revocation remains available if logout needs re-pairing.

The connected browser test uses a 390px touch viewport, actual disposable TLS/PG/
CLI/Git/protected checks, explicit native/auth/capacity fixtures and a temporary
self-signed test certificate. Its browser bypass is solely for UX emulation;
the same server's TLS is separately checked with the fixture CA. This is not a
real-phone trust/private-network test. AOS-028-TC08, remaining adversarial/device
qualification and cumulative G3/owner trial remain open.

Rapid restart permits a stopped socket's TIME_WAIT state to retire without
waiting for its natural timeout, using [Python's documented SO_REUSEADDR behavior](https://docs.python.org/3/library/socket.html#example).
A competing live listener is still refused; no port sharing or service termination
is enabled.
