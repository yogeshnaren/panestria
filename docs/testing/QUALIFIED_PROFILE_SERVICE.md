# Qualified local personal mode

This explicit foreground service connects the encrypted style editor and pinned
profile Ask terminal to the existing offline Ask runtime. Normal `local serve`
and the activity-only server still leave profiles disabled. This does not enable
Claude, cloud inference, background jobs, phone access or a release gate.

Use a clean source checkout with frozen dependencies, a current migrated
Postgres database, the dedicated **existing** public model cache, and an existing
private `local.json` from [local init](LOCAL_ASK_SETUP.md). Keep an active review
service on its current port. A conflicting listener or any existing local-model
controller makes startup refuse; stop your own earlier foreground Ask with
Ctrl+C before switching modes. Nothing automatically reaps those services.

## 1. Observe this machine and candidate

From the checkout's frozen environment:

```bash
uv run --frozen panestria profile qualify \
  --directory /absolute/private/profile-qualification \
  --model-cache /absolute/existing/model-cache \
  --synthetic-local-smoke
```

This deliberately runs two fixed actual tests on synthetic data: isolated OS
Secret Service checks, then an isolated keyring and the supported server factory's
CPU model lifecycle over physical loopback HTTP with browser pairing, restricted
Ask and suppression. It uses the existing disposable test Postgres port55439.
The model stays network-none, with no keyring/database/home mounts, core dumps
or Docker logs. It checks current model blobs and effective container limits;
it downloads nothing. It preserves preexisting model containers and the owner's
desktop keyring. The test's own model/container/database are cleaned up.

Expect `PASS` with `qualification_directory` and `qualification_sha256`, or a
fixed `UNAVAILABLE` reason. Missing tools/cache, busy resources, skipped cases,
dirty source, timeouts or failed checks cannot produce a pass. Private raw XML,
logs and result journals remain in the selected directory. Do not paste their
contents into public issue reports without review. A failed run does not refresh
any earlier proof; the launcher uses an exact digest, never an implicit latest.

The proof is valid for at most24h and this OS boot, current production and probe
source, frozen dependency manifest/installed versions, Python/keyring/D-Bus/
Docker client/Ollama binary and Ollama library bytes. Initial hashing reads the
existing library files (several GB on some hosts); it does not copy them. The
process caches only public file digests and invalidates them when inode, size,
mtime or ctime changes. Startup rechecks the pinned model blobs independently.
Documentation-only commits can share the same runtime inputs; the observed source
commit in the original XML/proof is never relabeled. Reboot, source/dependency/
binary change or expiry requires an explicit new successful observation.

This is a narrow local operator qualification, not a signature, independent
security audit, complete G1/G3, model style-quality assessment or owner trial.
It does not protect against an already compromised workstation administrator.

## 2. Select existing OS key handles

Retain the opaque handle from your earlier explicit key setup, with
`owner_id`, `project_id`, `profile_id` and `key_id`. The first two must exactly
match `local.json`. `profile key-check --help` describes the existing read-only
check. If you do not have a handle, stop and use the separately documented
[explicit OS key setup](PROFILE_KEY_SETUP.md); this service cannot provision a key,
create/unlock a collection, prompt for a password or choose a fallback store.

Create a private0600 wrapper file, for example `/absolute/private/personal.json`:

```json
{
  "schema_version": 1,
  "local_config": "/absolute/private/local.json",
  "qualification_directory": "/absolute/private/profile-qualification/certificates",
  "qualification_sha256": "COPY_THE_EXACT_SUCCESSFUL_DIGEST",
  "key_handles": [{
    "owner_id": "EXISTING_OWNER_UUID",
    "project_id": "EXISTING_PROJECT_UUID",
    "profile_id": "EXISTING_PROFILE_UUID",
    "key_id": "EXISTING_KEY_UUID"
  }]
}
```

This file contains only opaque references. Never put key bytes, passwords, API
keys, profile plaintext or a database URL in it. List each exact old/new key
handle needed for a reviewed rotation; up to64 unique handles are allowed. A
handle absent from this list is denied before the OS store is accessed. Keep all
configuration, token, qualification and runtime files outside the model cache.
The current profile clients use IPv4 loopback; an IPv6-only local config refuses.

## 3. Launch and use the terminals

Set the existing `PANESTRIA_DATABASE_URL` privately as in the local Ask guide,
then run:

```bash
uv run --frozen panestria profile serve \
  --config /absolute/private/personal.json --restricted-offline
```

This stays in the foreground. `STARTING` is not readiness; the terminal's status
check and actual request can still deny for unavailable resources, locked/missing
keys or changed scope. It uses the same port/token/owner/project/cache/runtime
from `local.json`. No migration, project grant, key, service install, autostart
or default mode is created. Ctrl+C stops only its owned model and listener.

Use [style-tui](PROFILE_STYLE_TERMINAL.md) to create/correct the selected profile
and separately approve communication preferences for local context. Use the
matching client configuration (same owner, project, IPv4 port and existing token)
and [ask-tui](PROFILE_ASK_TERMINAL.md) with the exact reviewed profile row/version.
Changing a profile requires a fresh explicit selection; there is no silent
newest-version upgrade. The ordinary Ask terminal expects a profile-disabled
server; use the explicit profile terminal for this mode.

Private reads/writes recheck the proof before and after existing OS key access.
Ask rechecks it and current profile/policy before model dispatch **and before
publishing the answer**. A late denial withholds the answer and records the
canonical unavailable outcome; it does not repeat inference. Suppression remains
available without a key even after qualification expires. A completed receipt
contains metadata, not a retained private answer or its plaintext fingerprint.

Full private example support, context/model compatibility, readability and owner
preference evaluation, connection onboarding, phone/Mission Control and original
cumulative acceptance remain pending. This command does not complete R3.
