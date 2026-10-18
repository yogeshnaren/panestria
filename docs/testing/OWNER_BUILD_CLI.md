# Review a real PUBLIC Claude Build from the owner CLI

The owner CLI submits an explicit PUBLIC goal through canonical PostgreSQL state,
the admitted Claude subscription runtime, a separate Docker Bash worker, frozen
independent checks and exact owner review. It supports arbitrary task intent
within its documented bounds; it is no longer limited to the website's fixed
proposal. The website remains that separate demo.

Use a private checkout with frozen dependencies, Docker/the pinned worker image,
the existing private Claude profile and a PostgreSQL database migrated to current
head. Supply its existing credentials through `PANESTRIA_DATABASE_URL`; never
put database or provider credentials in the Build configuration. Do not run
tests against your review database. The integration suite uses its own disposable
database on 55439 and preserves owner databases/services.

## Prepare a fresh PUBLIC exercise

First [qualify the runtime](BUILD_RUNTIME_QUALIFICATION.md). This explicitly opts
into one PUBLIC synthetic subscription call and produces a private expiring
certificate. Requalify after package source, pinned CLI, worker image or profile
changes. A certificate alone grants no project permission.

```bash
umask 077
uv run --frozen panestria native qualify-build \
  --evidence-directory "$PWD/.panestria-runtime/native-qualification" \
  --public-subscription-smoke

uv run --frozen python tools/create_public_build_example.py \
  --directory "$HOME/panestria-public-build-review" \
  --qualification-directory "$PWD/.panestria-runtime/native-qualification"
```

Choose a fresh example directory; the helper refuses to replace one. It creates
a tiny PUBLIC source repo, a separate protected bare copy, reviewed checks,
private `build.json` and `contract.json`. It prints the expected base and goal ID.
It makes no database or provider call. Only this synthetic local source uses the
example Git identity; your configured author and existing repositories are
untouched. Keep the printed values for the commands below.

The generated owner/project scope is separate from the strict offline Ask scope.
Existing Ask services continue using their original policy. This CLI is a local
owner operation; it is not exposed as a model-callable/public API endpoint.

## Review the project grant

```bash
uv run --frozen panestria build prepare-policy \
  --config "$HOME/panestria-public-build-review/build.json" \
  --allow-public-native-build
```

Expect `PENDING`, a review ID, an effect digest and the full proposed policy.
Review it: only read/edit/Claude PUBLIC export may act; merge needs approval;
private cloud, spend, installation and deletion are not enabled. This command
creates a retained administrative policy-review record and makes no model call.
It does not approve its own proposal.

Replace `REVIEW_UUID` and `EFFECT_SHA` with that exact review's values, then
confirm it as the local owner:

```bash
uv run --frozen panestria build confirm-policy \
  --config "$HOME/panestria-public-build-review/build.json" \
  REVIEW_UUID EFFECT_SHA
```

Copy the returned `policy_ref` into `contract.json`'s `autonomy_profile_ref`.
Review that contract's intent, PUBLIC label, selected paths, zero API budget,
one attempt and required tests/path/approval checks. Keep the file private.
An incorrect digest, expired certificate or stale policy is refused. The same
prepare/confirm flow supports explicit certificate renewal; it never silently
widens another policy axis. Existing pending approvals are invalidated by a
policy change as usual.

## Submit, inspect and approve

Replace `BASE_SHA` with the helper's `expected_base`, and `GOAL_UUID` with the
contract's goal ID. Choose a stable submission key for this contract.

```bash
uv run --frozen panestria build submit \
  --config "$HOME/panestria-public-build-review/build.json" \
  --contract "$HOME/panestria-public-build-review/contract.json" \
  --select calculator.py --expected-base BASE_SHA \
  --idempotency-key public-build-review-1 --public-subscription-run

uv run --frozen panestria build status \
  --config "$HOME/panestria-public-build-review/build.json" GOAL_UUID --diff
```

The first command runs in the foreground, usually for seconds, with a hard
bounded deadline. Expect `WAITING_APPROVAL`, independent `PASS` checks, the exact
base/candidate commits, evidence hash and approval preview. Read the diff:
`calculator.py` changes from 42 to 43 and `notes/build.txt` contains
`bounded Bash build`. The protected main ref has not advanced. A worker claiming
success with incorrect code fails the independent check and creates no approval.
Failed check evidence remains inspectable through `status`.

Replace `APPROVAL_UUID`, `EFFECT_SHA` and `TASK_VERSION` with the values from
that approval. After reviewing the diff and checks:

```bash
uv run --frozen panestria build approve \
  --config "$HOME/panestria-public-build-review/build.json" \
  APPROVAL_UUID EFFECT_SHA TASK_VERSION public-build-approval-1
```

Expect `task_state: COMPLETED` only after the protected Git CAS is confirmed.
A wrong digest/version, moved base, changed verifier, revoked policy or expired
certificate cannot authorize a different merge. Approval advances only the
protected copy at `runtime/protected/OWNER_UUID/PROJECT_UUID/destination.git`.
The original `source` working checkout stays at 42. Inspect/import an approved
result into a working checkout separately; the CLI does not reset it.

Repeating `submit` with its original key returns canonical state with
`replayed: true`; it does not spend another subscription turn. An unavailable,
cancelled or uncertain invocation is not automatically retried. Inspect state
before deciding on fresh work. To cancel during execution, use another terminal
and the current task `row_version` from `status`:

```bash
uv run --frozen panestria build cancel \
  --config "$HOME/panestria-public-build-review/build.json" \
  GOAL_UUID TASK_VERSION
```

Revocation does not wait for the submission lock. It stops new actions; already
started effects retain their normal reconciliation semantics.

## Bounds and observed validation

V1 permits PUBLIC-only context, at most 16 selected UTF-8 files / 16 KiB prompt,
one Bash job and one attempt, zero SDK money and a 30–120 second contract wall
budget (native inference at most 90 seconds). Bash output is metadata-only to
Claude. The source snapshot has the existing 2,000-file / 32 MiB limits and
rejects secret/config/link/special paths. Reviewed Python check scripts reside
alone in private `root/reviewed`, outside worker writes, with hashes pinned in
the private config. Every configured check must be required in the contract,
alongside a required path check and exact merge-policy check. Unsupported checks
are not silently treated as passing.

For a different PUBLIC source, prepare a fresh private config and separate
protected bare copy using the same layout, a reviewed independent check bundle
and an owner-authored contract. Do not classify private repositories as PUBLIC to
make this pilot accept them. The implementation does not add interactive shell
debugging, private repository cloud support or other provider agents.

At clean `966b694`, the [source-bound report](../../evidence/r1-owner-build-cli-2026-10-18/report.json)
records 9 default checks with labeled transport/certificate fixtures, including
remaining verifier wall-budget enforcement, 11 actual runtime conformance passes
and one actual owner CLI journey using the real operator-issued certificate and
Claude subscription. Earlier `7c4aef5` evidence is preserved separately. The live journey is a scripted
synthetic owner decision, not human acceptance. To repeat only the changed-path
live check after deliberate opt-in:

```bash
PANESTRIA_NATIVE_QUALIFICATION_DIRECTORY="$PWD/.panestria-runtime/native-qualification" \
  uv run --frozen pytest \
  tests/integration/test_owner_build_cli.py::test_actual_owner_cli_uses_real_operator_certificate_and_native_subscription \
  -m live -q
```

No Anthropic SDK key, OpenAI call, new credential, download, paid overflow or
fallback is used. SDK TC04 remains deferred, not passed. Full cumulative G1 and
the R3 owner trial/acceptance remain separate requirements.
