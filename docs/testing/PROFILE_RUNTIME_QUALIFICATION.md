# Actual profile runtime qualification

This synthetic component test uses the actual OS Secret Service, PostgreSQL,
profile API, paired-session/CSRF handlers, restricted Ask selector and pinned
Qwen2.5 1.5B local model. It uses no mock key store or inference transport.
HTTP handlers run through ASGI TestClient; this is not a real-browser/phone or
14-day owner trial. No personal profile or provider credential is used.

Prerequisites: Linux, Docker with the pinned existing runtime image, installed
Ollama, `dbus-run-session`, `gnome-keyring-daemon` and an explicitly selected
existing pinned public model cache. There must be no existing local model
container/controller. The test preserves existing services, including stale
ones; orphan recovery is outside this qualification.

```sh
PANESTRIA_PROFILE_TEST_MODEL_CACHE=/home/yogesh/Personal/panestria/.panestria-runtime/models \
  uv run --frozen pytest tests/integration/test_profile_runtime_live.py -m live -q
```

The cache is mounted read-only and never downloaded/modified. The newly owned
model uses two CPUs, a 2.5 GiB memory limit, a private Unix socket, nonroot/read-only
root, no network/ports, no capabilities, no persistent container logs and disabled
core dumps. Effective mounts exclude the keyring, desktop bus, owner home and
database credentials. These are observed configuration limits, not peak-resource
or throughput measurements.

The child has a disposable D-Bus/keyring session, private XDG directories and
synthetic key/password. It explicitly saves an approved synthetic profile,
pairs a scoped session and completes one real local-model Ask. It verifies
restricted labeling and omitted input/output profile fingerprints, then
suppresses the profile and proves the next request stops before inference.
Owned model/container/bus/keyring/fixture-database resources are cleaned afterward;
the owner's keyring, database, running demo and accounts remain unchanged.

[Source-bound component evidence](../../evidence/profile-runtime-2026-10-15/report.json)
records the actual passing case and fixture identities. Default CI excludes this
live test. Missing prerequisites or preserved busy resources cannot establish a
pass. This does not complete TC06–TC08, native harness isolation, key-backup/purge,
setup usability, hardware budgets, owner keyring conformance or release acceptance.
Keep default profile use off until its remaining setup/boundary obligations pass.
