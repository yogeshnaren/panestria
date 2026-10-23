# Owner connection declaration setup, review and revoke

Partial revision-3 MVP-X09 / AOS-008-S4 onboarding. Reuse the existing canonical
review/revision ledger; introduce no connection execution, account registry,
conformance certificate, secret injection or second task store.

The owner can initialize private scope files, run a foreground declaration-only
API, inspect current project policy, retain an exact proposal, review every field
in a scrollable terminal and separately confirm one decision. A revoke proposal
uses the current policy reference and current declaration version, so a prior
policy change need not prevent preparing disconnection. A stable caller-chosen
proposal UUID enables inspection after an uncertain reply. No automatic retry,
new intent, policy widening or adoption of historical approval occurs.

`connections init` reuses activity initialization and its private format; it
creates no project, task, policy or service. `connections serve` explicitly mounts
only activity and connection-declaration routes. It does not mount goal creation,
Ask, pairing, profile, job or merge mutations. It binds an unused IPv4 loopback
port; an occupied listener is preserved. Browser/phone/Build/storage modes cannot
be combined with this mode, and a browser-wired declaration-only app refuses its
connection routes. Existing default activity and kernel API behavior is preserved.

The new scoped read returns current owner/project/policy reference only. Existing
propose/read/decision services still own all database writes, exact digest/version,
policy/expiry checks, global event ordering, historical replay and immutable
audit. Requests share one strict duplicate-key/nonfinite-refusing contract parser
across CLI/API. Client responses are closed, scope/identity bound and require
DECLARATION_ONLY / UNVERIFIED / runtime unavailable; they cannot invent a certified
connection from a conformance reference supplied by the caller.

The terminal shows account/configuration, each action independently, classifications,
roots/origins, limits, both expiries, policy and full digest. It requires scroll to
the end, then a/d, then separate y. It checks fresh source and current policy before
one decision request. A settled or uncertain attempt cannot retry from that view;
reopen the exact retained proposal/current grant to inspect. Changed/expired
reviews are not consent. Literal rendering prevents terminal controls in metadata.

Account/root references remain declarations, not actual enrollment or permission
to import chats, credentials, agents or application data. The root primitive is
never called. The actual GrantBroker still needs independently verified account/
capability/configuration, current policy/lease/budget/approval/purpose, revocation,
secret/OS envelope and in-flight reconciliation before any connector can run.
Whole TC05–TC08/S4/S5 and G3 remain open. See the [owner guide](../testing/CONNECTION_DECLARATION_TERMINAL.md)
and [original component observations](../../evidence/connection-terminal-2026-10-22/report.json).
