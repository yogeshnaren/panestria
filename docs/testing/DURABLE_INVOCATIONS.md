# Durable native invocation claims

Migration `0017_worker_invocation` stores scoped invocation intents beside the
existing task/attempt/event records in PostgreSQL. It adds no second task store.
The trusted controller must authorize admission before preparing a call; an
invocation record itself grants no policy, provider or filesystem permission.

The binding fixes owner/project/task/attempt/epoch, contract and policy, request
digest and reviewed configuration digest. Prepare and claim recheck the current
lease, policy and contract. A unique attempt/key returns the existing record
only for identical bindings. Claim commits before external I/O. Concurrent or
restarted callers cannot dispatch a claimed, returned, expired or unknown call.
No database transaction launches processes or performs provider/Git I/O.

`DurableToolAuthority` connects this record to the existing gateway, checking
the workspace, registry and profile fingerprint as well as request scope.
Authority checks have a 300 ms statement timeout; the connection factory must
also supply a connection timeout. Revocation/expiry denies new work. Historical
receipts may still be recorded afterward, without restoring execution authority.
A lost response stays UNKNOWN and requires reconciliation rather than a retry.
Build evidence cannot publish while any current-attempt invocation is unfinished.

```bash
uv run --frozen pytest tests/integration/test_invocations.py tests/integration/test_build_invocation_fence.py -m 'not live' -q
uv run --frozen pytest tests/integration/test_invocations.py -m live -q
```

The default cases use disposable real PostgreSQL for competing claims,
transaction rollback with events, changed scope/contract/configuration, expiry,
immutable history and candidate-publication fencing. The live case uses actual
Docker plus the durable authority to write a candidate and refuse replay. These
checks make no inference request and do not complete the native demo or G1.
