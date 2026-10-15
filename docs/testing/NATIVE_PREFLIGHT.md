# Native Claude preflight

This AOS-010 task inspects metadata and compatibility. It verifies the attached
skills archive and four `claude-code-worker` member digests, checks the approved
CLI binary digest/version, inventories advertised controls, and queries redacted
login metadata only when the native configuration directory is private. It never
extracts or runs the attached scripts, sends an inference prompt, or grants
native worker/Build authority.

The supported CLI pin is `2.1.273`. Supply the resolved binary path and its
previously approved SHA-256 from the trusted operator/controller. A binary from
the repository or a model-selected pathname is not an approved reference. CLI
upgrades require review of the pin, parser and live conformance cases together.

```bash
uv run --frozen panestria native inspect \
  --binary /absolute/path/to/approved/claude/2.1.273 \
  --expected-sha256 APPROVED_BINARY_SHA256 \
  --config-dir /absolute/path/to/private/native-claude \
  --skills-archive docs/specification/attachments/agentos-skills-v0.1.0.zip
```

Use a user-owned configuration directory with mode `0700`. The command does not
change directory permissions or credential state. For a separate Panestria
login, the owner can create a private directory and sign in through the official
CLI using that directory:

```bash
mkdir -m 700 /absolute/path/to/new/native-claude
CLAUDE_CONFIG_DIR=/absolute/path/to/new/native-claude claude auth login
```

The owner performs the login; do not copy credentials from the everyday profile.
If the directory exists, inspect its ownership/permissions rather than blindly
changing it or retrying `mkdir`. Login metadata does not prove refresh, usable
quota or successful inference.

| Exit | Status | Meaning |
| --- | --- | --- |
| 0 | `INSPECTED` | Pinned metadata matches and subscription login is reported; execution remains unauthorized. |
| 1 | `CONFIG_UNSAFE` | Missing, noncanonical, wrong-owner or nonprivate directory; no auth probe runs. |
| 1 | `AUTH_REQUIRED` | The private directory has no reported login. |
| 1 | `AUTH_MODE_DENIED` | The reported mode/provider is outside the subscription/first-party profile. |
| 2 | bounded error code | Digest/version/flag/transport failure; no automatic retry or provider fallback. |

The Linux runner binds executable and config references to open file descriptors,
uses an empty temporary working/home directory, constructs a fresh environment,
disables updates/nonessential telemetry, and limits both output pipes under one
total deadline. It rechecks binary bytes and config identity after each relevant
operation. Account IDs, email, raw auth JSON and diagnostics are discarded. A
replaced CLI, changed config, missing flag, malformed JSON or output/deadline
violation fails closed.

The installed native `--version`/`--help` probes passed on 2026-10-14. The everyday
config directory failed the private-directory guard; an empty private directory
reported `AUTH_REQUIRED`. These are metadata observations, not successful
inference or hostile-repository conformance evidence.

The [CLI reference](https://code.claude.com/docs/en/cli-reference) documents that
safe mode disables customizations while managed policy hooks still apply;
restricted mode can regain command tools if explicitly selected. `--help` omits
some supported flags. The probe inventories a visible subset and cannot certify
these security behaviors. The [environment reference](https://code.claude.com/docs/en/env-vars)
documents config-directory selection and updater/nonessential-traffic controls.
The attached prototype remains reference material, not a certified adapter.

```bash
uv run --frozen pytest tests/integration/test_native_profile.py tests/integration/test_aos_010.py -q
```

Dedicated auth principal registration, controlled prompt-file startup, native
tool gateway, OS/credential separation, hostile hooks/MCP fixtures, successful
inference and full workflow/API integration are subsequent tasks. R1 remains
IN_PROGRESS and G1 NOT_RUN; no preflight report completes a release gate.
