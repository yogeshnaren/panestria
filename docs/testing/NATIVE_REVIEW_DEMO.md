# Native Claude review demo

Branch: `task/r1-native-review-demo`, stacked on the proposal adapter and durable
controller PRs. Use this branch for the complete preview; the earlier
`task/r1-native-tool-gateway` branch tests only a component.

This demo implements one fixed public exercise:

1. Claude Code proposes a JSON replacement for `calculator.py` (no native tools).
2. Panestria commits a one-use invocation claim before requesting inference.
3. A reviewed writer applies the candidate in a secret-free Docker container.
4. A different, read-only container runs six controller-owned arithmetic cases.
5. Path and policy checks must also pass. The UI shows the exact diff and evidence.
6. The goal waits for the authenticated owner to approve that exact merge.
7. The protected Git target compares the expected base and candidate, records its
   receipt, and only then permits the task and goal to become `COMPLETED`.

The repository used for this exercise is an isolated demo repository. It never
edits or merges the Panestria development checkout or your other projects.
Claude chat and Cursor remain independent development clients; their chats,
logins, agent lists and context are not automatically imported or shared.
This is a single-worker preview and does not complete R1/G1 or the R3 MVP.

## Start the review server

Use a separate checkout so your existing review branch stays intact:

```sh
git fetch origin
git worktree add ../panestria-native-review task/r1-native-review-demo
cd ../panestria-native-review
uv sync --frozen --group dev
uv run python -m panestria.cli.review_demo init
uv run python -m panestria.cli.review_demo serve
```

If the branch is available only on the remote, use
`git worktree add -b task/r1-native-review-demo ../panestria-native-review origin/task/r1-native-review-demo`.
If the branch is already checked out elsewhere, use that checkout instead of
creating another checkout of it.

Open [the local demo](http://127.0.0.1:8871). The `serve` command is a foreground
server: leave its terminal running while reviewing, and stop it with Ctrl+C.
Use another terminal in the same checkout for these commands:

```sh
uv run python -m panestria.cli.review_demo pair
uv run python -m panestria.cli.review_demo status
```

Enter the one-use pairing code on the page within five minutes. Codes, session
cookies and CSRF tokens never appear in URLs. A page reload requires another
pairing code because the page keeps its CSRF token only in memory.

Setup uses its own container `panestria-native-review-demo-db`, port **55438**,
volume `panestria_native_review_demo_pgdata`, and database `panestria_native_demo`.
It preserves the R0 container and volume on 55432. State defaults to
`~/.local/share/panestria/native-review-demo` (private, owner-only). The included
Postgres credential is a placeholder for this synthetic loopback-only database.
Do not put real project data or credentials in it.
The CLI refuses a database URL outside that dedicated host/port/database.

`--root /absolute/private/path` selects a separate demo identity and repository.
Pass the same root to init, serve, pair, qualify, status and reconcile. A server
lock prevents two controllers from recovering the same root concurrently.
`--port 8872` selects another free port if necessary; it does not kill an existing
service. Keep the same selected port for the server and browser URL.

## While Claude usage is unavailable

You can inspect the exercise, connect a session and review readiness. Start stays
disabled until this exact profile has passed its live compatibility check.
Authentication alone does not qualify it. There is no inference retry loop,
credential substitution, provider fallback or fabricated success certificate.

On 2026-10-14 the dedicated profile was authenticated, but actual inference
reported rejected quota. No successful live candidate or demo attestation had
been produced at that point. Default integration tests use a labeled provider
fixture and cannot establish live Claude success.

## After a small Claude prompt works

The default dedicated profile is `~/.panestria-native-claude` and must be private
(mode 0700). The adapter pins the inspected Claude Code 2.1.273 executable by
hash. `--claude-binary` selects the installed file with that exact hash on another
machine; a newer version requires a reviewed compatibility update. No credentials
are copied to the repo, browser or tool containers.

Run **one explicit compatibility check**, only when usage is available:

```sh
uv run python -m panestria.cli.review_demo qualify
```

It sends only the fixed public synthetic prompt through the dedicated Claude
Code subscription profile, with tools disabled and fresh cwd/home. It then runs
the actual writer and verifier containers. It has a 90-second native deadline,
two-turn limit and a native estimated budget of $0.25; that estimate is not a
billing guarantee. API keys are scrubbed and reported overage is rejected.
A rejected rate limit returns `UNAVAILABLE` and stops. Nothing auto-retries.

A successful check issues a purpose-specific, hash-addressed attestation valid
for 24 hours, tied to the binary, prompt, Docker image and Python source hashes.
The general runtime certificate validator rejects this demo attestation. It
cannot certify arbitrary repositories, native shell/MCP access, private exports,
or either complete AOS-008/010 conformance group. The authenticated CLI is a
trusted host process; the OS security boundary contains candidate application
and execution, not the authentication process itself.

Refresh the page after qualification:

1. Expand **Review the policy before starting**. The only cloud destination is
   `claude-subscription`; read, edit and that fixed public send are permitted.
   Merge requires approval. Other actions are denied. No API credentials are used.
2. Click **Enable this policy and start the public goal**. The request binds both
   the reviewed policy hash and attestation hash. The owner policy review is
   recorded before goal admission. A new native call generates the task candidate.
3. Expect invocation events, independently generated check reports and a diff
   replacing subtraction with addition. Claude may still return an invalid or
   incorrect candidate; such a run must fail without offering a merge.
4. For a good candidate, expect `WAITING_APPROVAL`, three passing checks and an
   exact merge preview containing base, candidate and evidence identities.
5. Approve only after inspecting that preview. Expect `COMPLETED` only after the
   protected Git effect is confirmed. Reject leaves the original subtraction
   implementation on the protected main branch. Cancel stops current work and
   prevents later publication or approval from reviving it.

The successful merge completes this one exercise. Start a **new root** for another
exercise so the original demo history remains available; the controller refuses
to reuse an already repaired base. Failed or cancelled runs can be explicitly
started again with a new goal, with no automatic retry of the old invocation.

## Recovery and exact evidence

State and events live in the same Postgres database. Native calls and writes have
one-use invocation records committed before I/O. A restarted controller marks
interrupted generation as failed and never replays it. Unknown calls remain
fenced. Existing owner review survives a restart; stale approvals cannot execute.

An interruption during merge may leave an unknown effect. Query and reconcile
that **existing** effect, without starting another worker:

```sh
uv run python -m panestria.cli.review_demo reconcile --goal GOAL_UUID
```

A definitive Git receipt is required for completion. An absent or uncertain effect
is not silently re-dispatched. If a diagnostic itself is interrupted with a
`STARTED` journal, qualification refuses an automatic replay. Preserve that root
and use a new explicit root after reviewing the uncertain invocation.

Private evidence is under the root's `evidence/` directory; scoped destination
Git is under `protected/<owner>/<project>/destination.git`. Candidate generation,
application, verification, owner approval and confirmed effect are distinct
records. No public API accepts a worker-supplied PASS report or approval flag.

## Test the implementation without provider usage

```sh
uv run ruff check .
uv run mypy src
uv run lint-imports
uv run pytest tests/integration/test_proposal_demo.py -q
uv run pytest -m 'not live'
```

The demo tests use disposable PostgreSQL on **55439**, actual writer/verifier
containers and actual protected Git, with an explicitly labeled response fixture
at the provider seam. They exercise success, wrong diffs/checks, exact approval,
rejection, quota, cancellation, restart, ambiguous calls, lost merge receipts,
origin/CSRF/session rejection and denial after session revocation. They do not
establish successful live Claude inference. The production CLI has no fixture
provider option. Existing live native tests remain opt-in; see
[the proposal adapter instructions](CLAUDE_PROPOSAL.md).
