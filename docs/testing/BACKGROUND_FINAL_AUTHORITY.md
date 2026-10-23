# Check final background integration authority

Use the existing [finite run commands and prerequisites](BACKGROUND_RUN.md).
This change enables no service or background inference and does not refresh the
owner's stale Disabled billing observation. Current independent native/runtime
qualification and exact owner plan/queue/account review remain mandatory.

If a queue item is withdrawn after its final node is claimed, final assembly,
subsequent independent checks and publication must check current eligibility.
Expect WAIT/withdrawal, no new final PASS/merge review and an unchanged protected
main. Existing verified editing handoffs and physical return records remain.
An executed final invocation can show RETURNED while its claim remains held:
that is historical physical evidence, not approval or claim-release authority.
If no integration invocation occurred, canonical cancellation can instead
release it with an immutable NO_DISPATCH proof. Do not free claims manually.

```bash
panestria background runs --config /absolute/private/build.json ITEM_UUID
panestria plan claims --config /absolute/private/build.json PLAN_UUID
panestria build status --config /absolute/private/build.json GOAL_UUID
```

The [editing guard instructions](BACKGROUND_WORKER_AUTHORITY.md) show exact
withdrawal. Avoid manipulating a real owner task merely to reproduce a race.
The focused developer tests use owned disposable projects and synthetic native/
auth metadata while preserving actual PG/Git/Docker checks:

```bash
uv run --frozen pytest tests/integration/test_background_integration_authority.py \
  tests/integration/test_background_run.py \
  --junitxml=/tmp/background-final-authority.xml
```

The callback fences future check admission and publication; an already running
bounded local check may finish. No instantaneous cancellation, cloud principal
lock, full connection conformance or release/trial pass is claimed.
