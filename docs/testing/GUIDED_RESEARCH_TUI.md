# Run the guided research terminal

Panestria can now walk an already staged **PUBLIC** research question through
query proposals, public collection, a local draft and source review in one
keyboard interface. The draft remains unverified. Search setup, qualified
semantic support and the original live acceptance cases are still required for
complete Delegate/G2; this terminal does not bypass them.

Use current `main` with the existing installed dependencies. Start from
[owner question staging](OWNER_RESEARCH_SUBMISSION.md) to obtain a request ID.
Use the private local-model configuration from
[local query planning](LOCAL_RESEARCH_QUERY_PLAN.md) / [draft synthesis](LOCAL_RESEARCH_SYNTHESIS.md).
It must reference an existing cached model; nothing is downloaded. Select the
existing disposable/test database deliberately with `PANESTRIA_DATABASE_URL`.
The guide neither initializes nor migrates it. Preserve your existing review DB.

From the checkout, in a real terminal:

```bash
uv run --frozen panestria research guide REQUEST_ID \
  --synthesis-config /absolute/private/synthesis.json
```

This permits local question/proposal review. When you deliberately configure and
qualify the search/fetch runtime following
[owner collection](OWNER_RESEARCH_COLLECTION.md), add its private configuration:

```bash
uv run --frozen panestria research guide REQUEST_ID \
  --synthesis-config /absolute/private/synthesis.json \
  --collection-config /absolute/private/research.json
```

Both configurations must select the same owner, project and retained-blob root.
`--config` is an alias for `--synthesis-config`. A redirected pipe is refused.
No server, account login, policy grant or network service is created by the guide.
Actual search setup is owner-deferred; leave collection unselected until ready.

1. Read the stage using PgUp/PgDn or `j`/`k`. Question/query/passage data is shown
   as escaped JSON; `\u...` sequences describe exact data, not commands.
2. Press `v` after reaching the end. Review the named action and full SHA256.
   Press `y` to attempt **only that stage**, or Escape to cancel.
3. After PLAN returns, read the proposed queries and possible upstream disclosure.
   No query was sent by planning. COLLECT still needs current qualified runtime,
   exact policy/connection grants and its original budget. Without selected
   collection setup the terminal stops with instructions.
4. After collection returns, read the exact bounded PUBLIC question/passages
   before separately confirming DRAFT. It uses the existing local CPU path and
   neither searches nor fetches. Citation presence does not establish support.
5. REVIEW opens the existing [claim/source review TUI](RESEARCH_CLAIM_REVIEW_TUI.md).
   Your judgments have a further exact confirmation and remain owner reported;
   they do not qualify a model or complete the research task.

`q` exits. Reopening the same command reads retained canonical state; it does not
repeat completed work. STOP/UNCONFIRMED/RECONCILING means inspect the original
intent/receipt and errors using the existing inspection commands. Do not create a
new request, reset a task, change keys or rerun collection to bypass uncertainty.
Use `research query-plan`, `inspect`, `inspect-draft` and `inspect-draft-review`
from the linked guides to export retained evidence to a new private file.

The interface shows original stage limits. It is not an autonomous end-to-end
Delegate controller or an assertion that the aggregate release budget/semantic
quality has been qualified. Actual public web, model quality, billing and release
evidence must retain their real source and status.

For developers, `tests/integration/test_research_guide_terminal.py` exercises
disposable real PG/HTTP/reader/CAS and a real PTY. Its model, HTTPS and certificates
are explicit fixtures. It is not a substitute for required live tests.
