# Runtime constraints

`runtime.txt` pins every runtime dependency of the `panestria` wheel, with the
SHA-256 of each published file. It is generated from `uv.lock` and never edited:

```bash
uv export --frozen --no-dev --no-emit-project --no-emit-workspace --format requirements-txt -o constraints/runtime.txt
```

CI's quality job regenerates it and fails when it differs, then runs `pip-audit`
over it. An install uses it with `--require-hashes --no-deps` before installing
the wheel with `--no-deps`, so nothing outside the lock is resolved; see
[install from a wheel](../docs/operations/RUNBOOK-AND-RELEASE.md#install-from-a-wheel).
Regenerate it in the same pull request as any `uv.lock` change.
