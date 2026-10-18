# Admitted native Build controller

`AdmittedNativeBuild` connects the bounded Bash backend to current project
authority. It accepts a controller-bound task and explicit source paths. Context
is compiled from the verified protected snapshot and task intent, with at most
16 files / 16 KiB. The contract must be PUBLIC and permit cloud egress. Paths
outside the contract scope, absent paths, duplicate selections, invalid UTF-8 and
an altered compiled context are refused. Owner profile or memory data is not
automatically added.

Before inference the service requires the general source-bound runtime certificate
for the exact Bash profile, binary, image and source manifest. It rejects the
separate fixed-demo certificate store. Current local read/edit permission and
explicit Claude subscription export permission must all permit the action; a
pending approval is not permission. This controller does not issue certificates.

The native invocation claim commits before provider launch. A trusted callback
revalidates policy and lease immediately before the pinned CLI starts. Its event
records the context hash, authorized and accessible context, and unknown observed
transmission. It never claims to inspect encrypted payloads. Only the selected
PUBLIC context is passed to the existing native prompt-file profile.

Cancellation, changed policy/lease, runtime changes and the task's remaining wall
budget stop the native call. A quota/auth failure ends the current attempt with
no automatic retry. Reconstructing a controller cannot replay a claimed or
uncertain native call. A successful native response still requires the separate
frozen verifier; only passing independent checks create an exact merge approval
request. Cancellation/deadline before publication cannot publish PASS. Approval
and protected Git CAS remain separate owner actions.

## Validate the implementation

```bash
uv run --frozen pytest tests/unit/test_native_mcp_profile.py \
  tests/unit/test_native_command_protocol.py tests/unit/test_bash_protocol.py \
  tests/integration/test_admitted_native_build.py \
  tests/integration/test_scoped_bash.py -m 'not live' -q
```

This uses real disposable PostgreSQL/Docker/Git and explicitly labeled native
transport and certificate fixtures. The source checkout and trusted runtime
scripts must not be group-writable; use a private checkout/install. Do not weaken
the gateway checks if an unsafe checkout is refused. The R1 test DB uses port
55439 and is removed by its fixture; preserve owner services and databases.

The changed-path integration check uses one actual subscription call:

```bash
uv run --frozen pytest \
  tests/integration/test_admitted_native_build.py::test_actual_native_uses_admitted_context_and_durable_launch \
  -m live -q
```

It sends only a fixed PUBLIC synthetic task and selected source. Expect two
confirmed invocations (native launch and Bash job), separate frozen checks and
`WAITING_APPROVAL`. This check deliberately uses a disposable certificate fixture.
It does **not** issue, install or prove a production runtime certificate. No SDK
key, OpenAI call, paid overflow, fallback or owner repository export is involved.

The [source-bound report](../../evidence/r1-native-admission-2026-10-18/report.json)
records 131 affected default passes at clean `51bafec` and one actual changed-path
native pass at clean `f4742d7`. They remain pinned separately; the subsequent
context-digest guard is covered by the default run.

## Remaining owner-facing integration

The admission backend and [real runtime qualification command](BUILD_RUNTIME_QUALIFICATION.md)
are implemented. A supported owner task CLI entry point still needs completion.
Keep the generic path disabled until qualification and explicit project policy
review exist. The existing website remains its separately qualified fixed public
proposal demo. Full G1 clause evaluation and owner review remain separate;
AOS-016-TC04 is deferred by the subscription/local-only decision, not passed.
