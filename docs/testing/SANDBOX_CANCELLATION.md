# Sandbox cancellation

Trusted controllers can pass `cancel=threading.Event()` to `DockerSandbox.run`.
An already-set event refuses allocation; cancellation after inspected creation
returns a cancelled receipt and removes the unstarted container. During
execution the attachment loop checks cancellation and wall time, stops the
identified container, confirms its stopped state, and cleans up that exact ID.

Attachment EOF is not a worker-completion signal. The controller continues
checking the container state and deadline when output closes. A successful
attachment exit never replaces an observed stopped-container state. Cancellation
does not accept an artifact or complete a task; native/kernel wiring must retain
current actor/project/attempt/epoch authorization and handle effects separately.

Existing callers can omit the optional event. Runtime/cleanup failures remain
errors rather than confirmed cancellation. The Docker daemon is part of the
trusted runtime; an unavailable daemon can prevent immediate termination proof.

```bash
uv run --frozen pytest tests/integration/test_sandbox_cancellation.py -m 'not live' -q
uv run --frozen pytest tests/integration/test_sandbox_cancellation.py -m live -q
```

The four live cases use actual pinned Docker workers with no provider calls:
running-worker cancellation, cancellation with closed output, closed-output
deadline, and cancellation between inspected creation and start. They verify
container removal and preservation of unrelated files. A separate hermetic
attachment test forces EOF while container state stays running.

This is a lifecycle prerequisite for the native tool gateway, not completed
native integration or G1 conformance. Lease/policy revocation must supply the
trusted cancellation signal through the final controller workflow.
