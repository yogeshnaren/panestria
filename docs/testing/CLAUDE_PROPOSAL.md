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
inference reported `rate_limit_info.status: rejected`. Candidate generation was
unverified at that source. No runtime security certificate or R1/G1 PASS was
issued. Hermetic parser and transport tests are not evidence of live inference.

On 2026-10-15 the unchanged pinned CLI emitted additional closed metadata and an
exact JSON presentation fence. [The scoped compatibility correction](../design/16-NATIVE-THINKING-ESTIMATES.md)
validates those shapes without treating token estimates/correlation/timing as
authority, refuses queued/background/subagent work, and preserves unknown-field,
overage, session, schema and AST denial. The fixed-public actual native test
passed at source f67e0c5 (5.32s); 116 related hermetic checks also passed.
[Source-bound failed and passing observations](../../evidence/native-compatibility-2026-10-15/report.json)
are preserved. The model still only proposes candidate data with `accepted=false`.
No arbitrary repository/native tool, Cursor orchestration or complete G1 pass is
claimed. This changes code on main after its task merges; the preserved demo on
8871 continues running its historical source until explicitly upgraded.

Official CLI semantics: [CLI reference](https://code.claude.com/docs/en/cli-reference)
and [security](https://code.claude.com/docs/en/security). Managed policy hooks can
still run under safe mode; this profile refuses detected managed configuration.


The full fixed-public controller qualification now also has an actual native
lane. It uses disposable PostgreSQL, an already cached pinned worker image,
separate Docker application/verification, and a protected temporary Git ref:

```sh
PANESTRIA_ALLOW_NATIVE_LIVE=1 uv run --frozen pytest tests/integration/test_native_build_live.py -m live -q
```

Two actual fixed-public calls are expected. The test denies a wrong approval
fingerprint, verifies the protected ref stays unchanged before approval, then
supplies an exact **scripted synthetic test-owner** decision and checks one
successful effect and no replay after restart. This is not a human release
acceptance. The observed source-bound pass took 16.13s at b104e4f;
[the report and JUnit](../../evidence/native-build-2026-10-15/report.json) retain
its scope and limits. No image download, direct SDK/API-key call, provider fallback
or change to the owner's running demo is part of this lane.
