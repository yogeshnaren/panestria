# The owner app: `panestria serve`

`panestria serve` runs Ask, Mission Control and, optionally, Build in one
foreground process on one loopback port. It replaces running `local serve` and
one `mission-control serve` per mode in separate processes. Those single-mode
commands still work unchanged. This is Release 1 plan item 1.9; the dashboard's
per-scope pairing is part c3 and not done yet (see below).

## Start it

First complete the [local Ask setup](LOCAL_ASK_SETUP.md). Its `local.json`
names the owner, the project, the one bearer token and the one port. Then,
with the same private `PANESTRIA_DATABASE_URL`:

```sh
panestria serve --config "$HOME/panestria-local-ask/local.json"
```

Add `--build-config /absolute/build.json` to mount Build review, plan acceptance
and runs; the Build configuration must name the same owner and project.
Mission Control is served from the build packaged with panestria; `--assets DIR`
serves another production build instead.

The process prints one line, for example
`{"schema_version": 1, "status": "STARTING", "origin": "http://127.0.0.1:8768", "session_scopes": ["activity", "ask", "build"]}`,
then starts the model, as `local serve` does. Ctrl+C stops the server and its
model. A startup failure prints one fixed code, such as
`local_setup_policy_conflict` or `mission_build_required`, and exits 2.

`panestria ask` and `panestria tui` work against it with the same `--config`;
they use the bearer token.

## Browser sessions

Browser authority is split into three session scopes, each paired separately:

| Scope | Reaches | Lasts |
|---|---|---|
| `activity` | activity, Build progress, capabilities | 8 hours |
| `ask` | Ask, memory, corrections, local status | 8 hours |
| `build` | Build review and decisions, plans, runs | 1 hour |

A session for any scope may observe activity. An Ask session cannot read a Build
diff, approve a Build or start a run. Print a one-use code for one scope with:

```sh
panestria pair-code --config "$HOME/panestria-local-ask/local.json" --scope ask
```

The code expires after 120 seconds and is paired at `/v1/session/{scope}/pair`.
The command never prints the bearer token.

**Not yet:** the Mission Control dashboard still pairs one session at
`/v1/session/pair`, which the owner app does not mount. Until part c3 updates
the dashboard, use the CLI against the owner app, or the single-mode
`mission-control serve` commands for the browser.

## Ask after Build setup

Build setup (`panestria build policy-propose` and `policy-confirm`) applies a
broader policy to the project that `local init` set up for offline Ask.
Single-mode `local serve` then refuses to start (`local_setup_policy_conflict`).
The owner app still starts Ask under the new policy, but only if:

- the project has its offline-Ask setup receipt;
- the current policy revision was applied through an approved policy review;
- the new policy still lets `read` act and report.

Ask itself is unchanged under the new policy: it reads and has no cloud route.
`/v1/local/status` reports the policy actually in force, for example
`trust_profile: PERSONAL_SANDBOX`.

## Not in the owner app

The R0 goal, approval and artifact routes (`/v1/goals`, `/v1/approvals`,
`/v1/artifacts`) are not mounted. Nothing outside the dev-only devkit executes
a submitted goal; Build approval goes through the `build` scope and
`panestria build approve`. They return when the worker of plan item 2.3 can
execute goals.
