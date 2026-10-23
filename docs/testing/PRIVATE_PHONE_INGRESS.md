# Private read-only phone observer

This optional mode shows existing project/task/worker metadata and the
attention inbox in a browser. It cannot start work, approve/merge changes, change
grants or read raw/private artifacts. The workstation runs the work and must stay
online. Desktop modes remain loopback-only. Nothing is enabled by installation.

Use an existing migrated owner/project database and existing private
`activity.token` from [project activity setup](PROJECT_ACTIVITY_TERMINAL.md).
This source requires migration `0040_phone_devices`. Review your normal backup
procedure before explicitly migrating the selected database:

```bash
uv run --frozen alembic -c migrations/alembic.ini upgrade head
```

The implementation tests used disposable databases. Your running database and
services were preserved. A downgrade refuses to erase phone-device or scoped
pairing history. No cleanup or backup settings are changed by these commands.

Use an existing private network/interface and an existing TLS certificate/key
trusted by the selected phone/browser. The certificate must match the literal
workstation IP. No network, certificate, provider credential or public tunnel is
created automatically. IPv4 RFC1918, CGNAT and loopback preview addresses are the
initial supported address types; DNS/public/wildcard/IPv6 ingress is not supported.

Save a separate private `phone.json` next to the existing `activity.token`:

```json
{
  "schema_version": 1,
  "owner_id": "EXISTING_OWNER_UUID",
  "project_id": "EXISTING_PROJECT_UUID",
  "bind_port": 8771,
  "token_file": "/absolute/private/activity.token",
  "enabled": false,
  "bind_address": "192.168.1.10",
  "allowed_clients": ["192.168.1.20"],
  "certificate_file": "/absolute/private/existing-phone.crt",
  "key_file": "/absolute/private/existing-phone.key"
}
```

Replace the example IDs, paths and IPs with your selected existing values. Config,
certificate/key/token files must be private owner files, without symlink paths;
the configuration's parent directory must be private. Set `enabled` to true only
for the selected deployment. Up to eight exact private client IPs are supported;
private-network membership still requires application pairing.

With the existing database environment and a production Mission Control build:

```bash
uv run --frozen panestria phone serve --config /absolute/private/phone.json --assets /absolute/panestria/apps/mission-control/dist
```

This is a foreground server. Keep that terminal running; Ctrl-C stops the
listener. It reserves the selected port and refuses a conflict. It does not kill
an existing service, trust forwarding headers, start models or enable paid calls.
Open the printed **https** origin on the allowed device. In another local terminal:

```bash
uv run --frozen panestria phone pair-code --config /absolute/private/phone.json
```

Enter its 32-character one-use code in the browser within120 seconds. It establishes
a separate HttpOnly/Secure/SameSite cookie, with a maximum one-hour session.
The local code issuer is not exposed over the private listener. Pairing does not
consume a desktop challenge. Expected results are metadata and observer
capabilities; submissions/approvals/profile exports return403 even with a valid
device session. A bearer token cannot authenticate this ingress.

To inspect or retire a phone session from this project's current or older profile:

```bash
uv run --frozen panestria phone devices --config /absolute/private/phone.json
uv run --frozen panestria phone revoke SESSION_UUID --confirm-revocation --config /absolute/private/phone.json
```

Expect device ID, original times, current-profile flag and ACTIVE/EXPIRED/REVOKED
state. Revocation is canonical and takes effect on subsequent reads. Device logout
also revokes its session. A new/different profile needs separate pairing. Restoring
the identical profile can use an original unexpired, unrevoked session; it does
not extend that session. Explicit revocation remains effective after restoring
configuration. History is retained, capped at256 phone sessions per project,
and never automatically deleted.

[Source-bound component checks](../../evidence/private-phone-ingress-2026-10-23/report.json)
use real CLI/PG/TLS/cookies and a temporary synthetic test CA on loopback. They do
not establish compatibility with your phone, certificate trust store or private
network. The peer/clock/configuration failure checks include explicit fixtures.
The separate [observer view guide](PHONE_OBSERVER_VIEWS.md) covers an optional
existing PUBLIC Build evidence store and mobile last-seen/stale/offline/reconnect
behavior. Actual target-device/private-network qualification and TC05–TC08/G3
acceptance remain separate. No browser background-push delivery is claimed.
