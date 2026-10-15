# Fixed public Claude proposal adapter

This is a narrow compatibility profile, not a general Claude Code worker. The
pinned CLI receives one fixed public calculator exercise, in a fresh directory,
with built-in tools, project configuration and MCP unavailable. It returns
bounded JSON candidate data. It cannot approve, verify or merge that candidate.
The authenticated CLI is a trusted host process; candidate application and
execution must happen through separate secret-free containers.

The profile pins Claude Code 2.1.273 by executable and help hashes. An unfamiliar
stream, managed configuration, tool activation, overage or changed binary fails
closed. A rejected quota event terminates the process and returns `UNAVAILABLE`;
the adapter never retries with a different login, provider or billing route.
The native budget flag is an estimate, not a billing guarantee.

Run the hermetic tests with:

```sh
uv run pytest tests/integration/test_claude_proposal.py -m 'not live' -q
```

The opt-in installed-CLI test uses only the dedicated private profile and the
fixed synthetic prompt. It plants hostile project customization in the disposable
working directory and checks that it never executes. Run it only after confirming
that the account has inference available:

```sh
PANESTRIA_ALLOW_NATIVE_LIVE=1 uv run pytest tests/integration/test_claude_proposal.py -m live -q
```

On 2026-10-14 the installed profile passed redacted login inspection, but actual
inference reported `rate_limit_info.status: rejected`. Successful candidate
generation remains unverified. No runtime security certificate or R1/G1 PASS was
issued. Hermetic parser and transport tests are not evidence of live inference.

Official CLI semantics: [CLI reference](https://code.claude.com/docs/en/cli-reference)
and [security](https://code.claude.com/docs/en/security). Managed policy hooks can
still run under safe mode; this profile refuses detected managed configuration.
