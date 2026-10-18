# Worker inspection and attachment exit ordering

PR99's documentation-only CI at `d5b8fd7` failed the existing real-small-pipe
duplex test: `attachment_failed` instead of `completed`. It passed1831 other
checks, excluded51 live cases and retained one upstream warning. The original
full [CI run](https://github.com/yogeshnaren/panestria/actions/runs/39093996729)
and log hash are recorded in the component evidence; it was not relabeled or
retried to manufacture a passing result.

The runner checked worker state, then polled the attachment client. A worker can
exit between those observations. A stale running observation and a newly exited
client therefore do not establish attachment failure. Source inspection inferred
that interleaving; the original CI did not log its intermediate observations.

A deterministic regression uses a real child,4096-byte pipes and a private gate:
capture its running state, release it, wait for its actual exit, then return the
captured observation. Both exit0 and exit7 reproduce the original failure at
clean `1a79a09`. The explicit container-state seam is not a Docker conformance
claim; existing regression cases separately use actual Docker resources.

After observing client exit, inspect the same worker again. If it is still
running, retain attachment failure and scoped termination. If stopped with
pending input, retain input-incomplete refusal. Otherwise finish the existing
verification: actual worker status must be exited, worker exit0, successful
attachment status and completed input for success. Worker exit7 stays
process_failed. An unstarted created container with initial exit0 still cannot
pass. Failed attachment diagnostics remain suppressed. No client exit alone,
stale state, replay, new deadline, broader resource or permission can grant
success or execution authority.

At clean `c31d4577a563880d9957436e30e35cfc27505ad8`,55 focused checks pass24.91s;
8 selected live cases are excluded. They include both new deterministic real
child cases, the original small-pipe pressure/deadline/cancel/cleanup matrix,
actual Docker flag/resource/OOM/client-death/unstarted guards, real PostgreSQL
widening refusal, native parser and sandbox regressions. Ruff, mypy199 files,
11 import contracts, secret scan and source diff checks pass. Exact source/raw
pins and the original2-case failure are in
[the evidence report](../../evidence/attachment-exit-race-2026-10-18/report.json).
An earlier command selected a nonexistent test path and ran zero tests (exit4);
its retained XML is explicitly not a test pass.

This adds one state inspection after a newly observed client exit. Existing
inspection/cleanup timeout limitations remain; no hard elapsed-time SLA, vendor
auth conformance, exactly-once external action, full G1/G2/G3 or owner trial pass
is claimed. No provider/model/SDK/auth, image download, owner service/database,
original archive or schema changes. Preserve the separate pending planning PR
and API candidate; integrate current verified main before publishing or merging.
