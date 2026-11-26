# The owner app: `panestria serve`

`panestria serve` runs Ask, Mission Control and, optionally, Build in one
foreground process on one loopback port. It replaces running `local serve` and
one `mission-control serve` per mode in separate processes. Those single-mode
commands still work unchanged. This is Release 1 plan item 1.9.

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
The command never prints the bearer token. A new code for a scope replaces that
scope's earlier unused code.

## The dashboard

Open the origin from the `STARTING` line. The page lists one session per
mounted scope (Build only with `--build-config`), each with its own pairing
form and **Log out** button:

1. Run `panestria pair-code --scope ask` and enter the code under **Ask
   session**. The project activity and Offline Ask appear.
2. To review, accept or run a Build, pair **Build session** the same way. It
   shows when it expires, one hour later.
3. Pair **Activity session** only for a tab that should observe without Ask or
   Build authority.

Each scope keeps its own CSRF token in the page's memory, and each logout
revokes only that scope's session. If an Ask or Build view is refused, only that
scope is marked unpaired, with the reason: `Build session required` when the
browser holds no Build session (for example, after the hour), or `Build session
ended or was refused` otherwise. The other sessions stay paired.

CSRF tokens are never stored, so after a reload every scope shows **Not paired
in this tab**. A session cookie that is still valid keeps reading activity and
receipts; pair the scope again to submit, decide or log out. A page that names
different scopes from the server's capabilities shows nothing and asks to be
reloaded.

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
