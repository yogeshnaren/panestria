# Profile key adapter qualification

This is an AOS-011-S5 foundation; profile storage is still disabled. The adapter
only provisions or loads 256-bit scoped keys from Linux Secret Service. It
does not unlock or create a collection, execute prompts, replace/delete keys,
fall back to files/environment/session storage, or export a wrapping key.

Local checks:

```sh
uv sync --frozen --group dev
uv run --frozen pytest tests/integration/test_profile_keys.py -q
uv run --frozen pytest tests/integration/test_profile_keys_live.py -m live -q
```

The first suite uses fake transports for negative paths plus a real stalled
Unix-socket authentication test. The second requires `dbus-run-session` and
`gnome-keyring-daemon`. It runs an actual disposable bus and keyring with
synthetic keys/password, private temporary XDG directories, no inherited desktop
bus/auth/display settings, and child process cleanup. It tests creation/read,
idempotence, cross-scope denial, non-plaintext persistent files, locked denial
and a daemon restart. It does not use or modify the owner's desktop keyring.
Missing binaries produce a skip and no OS qualification claim.

[Recorded component evidence](../../evidence/profile-keys-2026-10-15/report.json)
binds the source commit, test inputs and observed local versions. Default CI
excludes the live test; neither result establishes a full vault, encrypted
database restore, worker mount isolation, TC06/TC07 completion or release pass.
The owner keyring has not been qualified or modified by this test.

Production integration must run only in the trusted broker, using a reviewed
persistent default collection and a compatible daemon. Secret Service schema
attributes are routing metadata, not an access control system against arbitrary
same-user host processes. Worker bus/home isolation and the future ciphertext
broker are essential; host administrators can inspect process memory. Python
`SecretBytes` masks representations but does not promise memory zeroization.

Provisioning is an explicit local setup operation outside retryable database
transactions. A missing/locked/ambiguous key or unknown creation result stops
the operation with a fixed code. Do not silently retry ambiguous creation,
delete old keys needed by backups, or turn a failed load into new provisioning.
The vault-facing protocol exposes only `load`; API/worker routes are not wired
to this module in this task. See [the design](../design/07-PROFILE-KEY-BOUNDARY.md).
