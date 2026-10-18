# Submit and inspect a new PUBLIC question locally

This command stages a question for inspection. It starts no network or model
work; the task remains CREATED. The existing website is a separate fixed demo.
See [the design](../design/54-OWNER-RESEARCH-SUBMISSION.md) for transaction and
replay behavior. Full Delegate execution is still being implemented.

Use the current branch/main containing this task, frozen dependencies, a private
CAS directory and an existing project with a current policy. Supply the existing
database URL through `PANESTRIA_DATABASE_URL`. Do not use the owner review DB for
integration tests or print credentials. No provider login or search setup is
needed for this local-only operation.

Prepare three owner-only files in a private directory:

- `contract.json`: a valid current GoalContract with a fresh UUIDv4 goal ID,
  existing owner/project IDs, PUBLIC class and the exact current
  `project-policy:VERSION:SHA256` reference. Retain current trust profile and all
  required canonical checks; this command cannot admit citation/rubric runners.
  A local staging exercise may use a required `human-review` check asking the
  owner to inspect the question and bounds. That check is stored, never passed
  automatically, and is not semantic support.
- `question.txt`: the selected PUBLIC UTF-8 question, at most 65,536 bytes.
- `limits.json`: for example
  `{"max_sources":2,"max_source_bytes":65536,"max_total_bytes":131074,"max_redirects":2,"deadline_seconds":60.0}`.

Keep input files mode0600 and the pre-existing CAS root mode0700. Substitute your
actual scope and absolute paths:

```bash
umask 077
uv run --frozen panestria research stage OWNER_UUID PROJECT_UUID \
  --contract /absolute/private-review/contract.json \
  --question /absolute/private-review/question.txt \
  --limits /absolute/private-review/limits.json \
  --store /absolute/private-research-cas \
  --key selected-question-1 --public-question
```

Expect `STAGED_NO_EXECUTION` and goal/task/request IDs plus a request hash.
This describes the submission operation, not any later execution history;
inspect the canonical goal/task for their current state when replaying a receipt.
Retain these IDs. The same command/key/input safely returns `replayed:true`.
Changing the question, contract or bounds with that key fails; it cannot create
another task or silently alter retained intent. A late local failure can leave
an unreferenced private CAS blob, while all uncommitted DB rows/events roll back.

Use the returned request/task IDs with the existing private inspector:

```bash
uv run --frozen panestria research inspect OWNER_UUID PROJECT_UUID \
  REQUEST_UUID TASK_UUID --store /absolute/private-research-cas \
  --output /absolute/private-review/new-question.html
```

Expect your exact question, zero claims, CREATED goal/task state and
NOT_ASSESSED semantics in a new private HTML file. Existing output files are
never overwritten. This command does not begin background work or complete a
goal. Later collection will require a separately qualified runtime, appropriate
current web policy/capabilities and explicit execution. Policy changes do not
upgrade an already pinned contract.

The focused check uses disposable Postgres and private CAS:

```bash
umask 077
UV_CACHE_DIR="$HOME/.cache/uv" UV_OFFLINE=1 .venv/bin/pytest \
  tests/integration/test_research_submission.py -q
```

It checks owner CLI → canonical records → private inspection, concurrent replay,
changed-input denial, actual DB commit then lost acknowledgement, actual rollback
after late failure, scope/policy/public-intent denial and refusal to lease the
CREATED task. Search, fetch and reader calls fail the staging test if attempted.
No live provider/model qualification or G1/G2/G3 pass is claimed.
