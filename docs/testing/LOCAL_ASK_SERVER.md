# Run the local Ask application

Use current main after the local-server task is merged. This is the supported
offline Ask process; the R0 synthetic server and the native proposal demo are
separate. Do not start it in the owner's historical review checkout or reuse
the review database without explicitly selecting that scope.

Prerequisites: Linux/nonroot user, Docker with the existing pinned runtime image,
installed Ollama, a dedicated existing pinned public Qwen2.5 1.5B model cache,
adequate foreground headroom/AC power, and a dedicated current PostgreSQL database.
Nothing downloads models/images, creates provider credentials or uses paid APIs.
Missing or busy prerequisites return an error; there is no fallback.

1. Set your existing database connection in `PANESTRIA_DATABASE_URL` outside Git.
   Apply migrations and run [explicit owner setup](LOCAL_ASK_SETUP.md). Retain
   the same owner/project UUIDs. Setup is an uncertified local-read-only scope.
2. Create a private local configuration directory (mode 700). Create a local
   loopback token with `uv run --frozen panestria local token-create --token-file
   /ABSOLUTE/PRIVATE/DIRECTORY/local.token`. It refuses overwrite and never prints
   the value. This token is unrelated to Claude/Cursor/provider credentials.
3. Save the following as a private mode-600 JSON file. Replace all placeholders
   with absolute paths and your retained UUIDs. The model cache must contain only
   its `blobs` and `manifests` directories; no personal/project files. Use a new
   private runtime directory separate from that cache and configuration.

```json
{
  "schema_version": 1,
  "owner_id": "YOUR_OWNER_UUID",
  "project_id": "YOUR_PROJECT_UUID",
  "bind_host": "127.0.0.1",
  "bind_port": 8766,
  "token_file": "/ABSOLUTE/PRIVATE/DIRECTORY/local.token",
  "model_cache": "/ABSOLUTE/PUBLIC/OLLAMA/CACHE",
  "runtime_directory": "/ABSOLUTE/PRIVATE/RUNTIME/local-ask"
}
```

4. Run the server in one terminal:

```sh
uv run --frozen panestria local serve --config /ABSOLUTE/PRIVATE/DIRECTORY/local.json
```

`STARTING` means startup began. The command stays in the foreground while you
use Ask from another terminal. Ctrl+C gracefully stops its owned model/container
and socket. Other listeners, models, DBs and the preserved demo are not stopped.
Port conflicts fail as `local_bind_unavailable` before a model starts. An existing
primary controller/model is preserved and admission fails rather than reaping it.
Do not use reload/multiple workers or expose/forward this loopback port publicly.

5. Ask from a second terminal using the same project UUID and token file:

```sh
uv run --frozen panestria ask 'Reply with only READY.' \
  --project YOUR_PROJECT_UUID --base-url http://127.0.0.1:8766 \
  --token-file /ABSOLUTE/PRIVATE/DIRECTORY/local.token --json
```

Expect a COMPLETED offline receipt plus the answer and actual usage/provenance.
The text appears only in this response and is not retained automatically. A
repeat of the same request ID returns its receipt without rerunning the model.
Ordinary CLI invocations generate a new request ID. First inference can be cold;
the configured model/request deadline remains enforced. Missing model or resource
pressure produces an unavailable/wait reason, never a cloud answer.

Authenticated `GET /v1/local/status` reports DB/policy/socket/admission facts.
Pairing uses the existing one-use code/session/CSRF API; stable token-derived
signing preserves sessions across restart. Rotate the local token to invalidate
them. `/healthz` is liveness; historical `/readyz` remains DB-only with executor
not configured. Neither establishes release acceptance or completed inference.
Profiles are **disabled**, and no goal/Build/merge/tool routes are mounted by this
entrypoint. Owner memory/learning routes still require explicit scoped requests.

The default tests use actual PostgreSQL/TCP HTTP with explicitly labeled model
fixtures. The separate [actual CLI/runtime evidence](../../evidence/local-server-2026-10-15/report.json)
proves one synthetic real local-model Ask, CSRF, restart/session/receipt continuity,
port-conflict preservation, output redaction and owned-resource shutdown. It is
not a full A-1, browser/phone trial, measured resource peak or R1/G1/R3 pass.

```sh
uv run --frozen pytest tests/integration/test_local_server.py -q
PANESTRIA_PROFILE_TEST_MODEL_CACHE=/ABSOLUTE/PUBLIC/OLLAMA/CACHE \
  uv run --frozen pytest tests/integration/test_local_server_live.py -m live -q
```
