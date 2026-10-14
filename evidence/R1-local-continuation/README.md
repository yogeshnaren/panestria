# R1 local continuation evidence

These are development checks, not a G1 promotion manifest. Both reports were
produced on the clean code candidate recorded in `summary.json`. The default
suite excludes 21 live cases; the separate OS report runs four provider-free
Docker verifier cases. Machine hostnames were removed from retained XML; the
original report digests remain in the summary. No paid SDK call or native Claude
inference was made in this continuation.

Run from the repository root:

```bash
make test
uv run --frozen pytest tests/integration/test_aos_027a.py -m live
```

The test fixtures use separate databases/containers and preserve the accepted
R0 review database. This evidence does not certify the unimplemented/native
worker path, its auth/tool profile, the complete R1 demo or phase completion.
