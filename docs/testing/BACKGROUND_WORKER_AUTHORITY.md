# Check current background worker authority

Use current main after the focused task PR is merged. Existing
[finite background setup](BACKGROUND_RUN.md), exact accepted plan, reviewed
same-account link and independently current runtime qualification are required.
This change does not enable background work or renew billing/quota evidence.
If the Disabled billing observation is stale, expect WAIT and no worker launch.

```bash
panestria background run --config /absolute/private/build.json \
  ITEM_UUID --allow-background-subscription-run
panestria background runs --config /absolute/private/build.json ITEM_UUID
panestria background show --config /absolute/private/build.json ITEM_UUID
```

To withdraw a selected item, copy its exact `binding_sha256` from `show`, then
use the existing owner command:

```bash
panestria background withdraw --config /absolute/private/build.json \
  ITEM_UUID BINDING_SHA256
```

Before disclosure, a withdrawn item, changed principal/profile or expired/
ineligible original run must stop without a new context disclosure. During an
editing call, withdrawal or DB eligibility failure requests transport/tool stop.
An unconfirmed outcome retains capacity rather than automatically retrying.
After return, a changed principal cannot publish a verified result or handoff.
Inspect original invocation/claim history; withdrawal does not erase prior
disclosure or edits and is not proof of instantaneous physical cancellation.

This is an editing-worker guard. Final trusted integration, general connection
grants and full host/provider/resource qualification remain separate work.
Do not change the active review service, use a private task for these checks or
run live calls merely to reproduce synthetic evidence. The focused developer
suite uses disposable synthetic PostgreSQL/Git/MCP/Docker and explicit fake
native/auth metadata, with no provider inference:

```bash
uv run --frozen pytest tests/integration/test_background_worker_authority.py \
  tests/integration/test_background_run.py \
  --junitxml=/tmp/background-worker-authority.xml
```

Expected: successful eligible serial work still reaches exact final owner review;
post-claim withdrawal/account changes prevent disclosure; running withdrawal
stops without releasing uncertainty; a confirmed tool return followed by changed
account cannot publish acceptance. These are component checks, not a G3 pass.
